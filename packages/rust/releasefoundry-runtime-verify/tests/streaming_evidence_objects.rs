use std::cell::Cell;
use std::fs;
use std::io::{self, Cursor, Read};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::rc::Rc;

use releasefoundry_runtime_verify::{
    sha256_hex, AuthenticatedEvidenceBundle, EvidenceArtifact, EvidenceObjectVerificationPolicy,
    HmacSha256Verifier, LocalEvidenceObjectRoot, VerificationPolicy, VerifiedEvidenceBundle,
    VerifyError, AUTHENTICATED_EVIDENCE_BUNDLE_SCHEMA_VERSION, HMAC_SHA256_ALGORITHM,
};

const KEY_ID: &str = "round53:streaming:key:v2";
const KEY: &[u8] = b"round53-streaming-test-key-material-000000001";
const KEY_ENV: &str = "RELEASEFOUNDRY_TEST_STREAMING_BUNDLE_HMAC_KEY";
const NOW_UNIX_MS: u64 = 1_750_000_000_000;

fn digest(label: &str) -> String {
    sha256_hex(label.as_bytes())
}

fn artifact(path: &str, bytes: &[u8]) -> EvidenceArtifact {
    EvidenceArtifact {
        artifact_path: path.to_string(),
        sha256: sha256_hex(bytes),
        size_bytes: bytes.len() as u64,
        media_type: "application/octet-stream".to_string(),
    }
}

fn authenticate(evidence: Vec<EvidenceArtifact>) -> VerifiedEvidenceBundle {
    let mut bundle = AuthenticatedEvidenceBundle {
        schema_version: AUTHENTICATED_EVIDENCE_BUNDLE_SCHEMA_VERSION.to_string(),
        algorithm: HMAC_SHA256_ALGORITHM.to_string(),
        key_id: KEY_ID.to_string(),
        bundle_id_digest: digest("round53-bundle"),
        tenant_digest: digest("round53-tenant"),
        project_digest: digest("round53-project"),
        evidence,
        evidence_digest: String::new(),
        issued_at_unix_ms: NOW_UNIX_MS - 1_000,
        expires_at_unix_ms: NOW_UNIX_MS + 60_000,
        signature: String::new(),
    };
    bundle.sign_hmac_sha256(KEY).unwrap();
    bundle
        .verify(
            &HmacSha256Verifier::new(KEY_ID, KEY).unwrap(),
            &VerificationPolicy::at(NOW_UNIX_MS),
        )
        .unwrap()
}

fn fixture_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/evidence-objects")
}

fn fixture_evidence() -> Vec<EvidenceArtifact> {
    ["reports/run-001.json", "traces/run-001.ndjson"]
        .into_iter()
        .map(|path| artifact(path, &fs::read(fixture_root().join(path)).unwrap()))
        .collect()
}

struct ChunkedReader {
    bytes: Cursor<Vec<u8>>,
    max_chunk: usize,
    observed: Rc<Cell<usize>>,
    interrupt_once: bool,
    fail_after: Option<usize>,
}

impl ChunkedReader {
    fn new(
        bytes: Vec<u8>,
        max_chunk: usize,
        observed: Rc<Cell<usize>>,
        interrupt_once: bool,
        fail_after: Option<usize>,
    ) -> Self {
        Self {
            bytes: Cursor::new(bytes),
            max_chunk,
            observed,
            interrupt_once,
            fail_after,
        }
    }
}

impl Read for ChunkedReader {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        if self.interrupt_once {
            self.interrupt_once = false;
            return Err(io::Error::from(io::ErrorKind::Interrupted));
        }
        if self
            .fail_after
            .is_some_and(|limit| self.observed.get() >= limit)
        {
            return Err(io::Error::other("injected failure"));
        }
        let remaining_before_failure = self
            .fail_after
            .map(|limit| limit.saturating_sub(self.observed.get()))
            .unwrap_or(usize::MAX);
        let allowed = buffer
            .len()
            .min(self.max_chunk)
            .min(remaining_before_failure);
        if allowed == 0 {
            return Err(io::Error::other("injected failure"));
        }
        let read = self.bytes.read(&mut buffer[..allowed])?;
        self.observed.set(self.observed.get() + read);
        Ok(read)
    }
}

#[test]
fn streams_partial_reads_retries_interrupts_and_hashes_exact_bytes() {
    let bytes = b"partial reads still form one authenticated object".to_vec();
    let verified = authenticate(vec![artifact("reports/partial.bin", &bytes)]);
    let observed = Rc::new(Cell::new(0));

    let result = verified
        .verify_objects(&EvidenceObjectVerificationPolicy::default(), |_| {
            Ok(ChunkedReader::new(
                bytes.clone(),
                3,
                Rc::clone(&observed),
                true,
                None,
            ))
        })
        .unwrap();

    assert_eq!(observed.get(), bytes.len());
    assert_eq!(result.total_size_bytes, bytes.len() as u64);
    assert_eq!(result.objects[0].sha256, sha256_hex(&bytes));

    let empty = authenticate(vec![artifact("reports/empty.bin", b"")]);
    let empty_result = empty
        .verify_objects(&EvidenceObjectVerificationPolicy::default(), |_| {
            Ok(Cursor::new(Vec::new()))
        })
        .unwrap();
    assert_eq!(empty_result.objects[0].size_bytes, 0);
    assert_eq!(empty_result.objects[0].sha256, sha256_hex(b""));
}

#[test]
fn distinguishes_undersize_oversize_digest_mismatch_and_io_failure() {
    let short = authenticate(vec![EvidenceArtifact {
        size_bytes: 8,
        ..artifact("objects/short.bin", b"abc")
    }]);
    assert_eq!(
        short
            .verify_objects(&EvidenceObjectVerificationPolicy::default(), |_| {
                Ok(Cursor::new(b"abc".to_vec()))
            })
            .unwrap_err(),
        VerifyError::ArtifactUndersize
    );

    let declared = b"12345";
    let oversized = authenticate(vec![artifact("objects/oversized.bin", declared)]);
    let observed = Rc::new(Cell::new(0));
    assert_eq!(
        oversized
            .verify_objects(&EvidenceObjectVerificationPolicy::default(), |_| {
                Ok(ChunkedReader::new(
                    vec![b'x'; 100],
                    100,
                    Rc::clone(&observed),
                    false,
                    None,
                ))
            })
            .unwrap_err(),
        VerifyError::ArtifactOversize
    );
    assert_eq!(observed.get(), declared.len() + 1);

    let digest_mismatch = authenticate(vec![artifact("objects/digest.bin", b"expected")]);
    assert_eq!(
        digest_mismatch
            .verify_objects(&EvidenceObjectVerificationPolicy::default(), |_| {
                Ok(Cursor::new(b"tampered".to_vec()))
            })
            .unwrap_err(),
        VerifyError::ArtifactDigestMismatch
    );

    let read_failure = authenticate(vec![artifact("objects/io.bin", b"abcdefgh")]);
    assert_eq!(
        read_failure
            .verify_objects(&EvidenceObjectVerificationPolicy::default(), |_| {
                Ok(ChunkedReader::new(
                    b"abcdefgh".to_vec(),
                    2,
                    Rc::new(Cell::new(0)),
                    false,
                    Some(4),
                ))
            })
            .unwrap_err(),
        VerifyError::ArtifactReadFailed
    );
}

#[test]
fn rejects_limits_and_post_authentication_manifest_mutation_before_opening() {
    let first = artifact("objects/first.bin", b"12345");
    let second = artifact("objects/second.bin", b"67890");
    let verified = authenticate(vec![first, second]);
    let opens = Cell::new(0);
    let result = verified.verify_objects(
        &EvidenceObjectVerificationPolicy {
            max_object_bytes: 4,
            max_total_bytes: 100,
        },
        |_| {
            opens.set(opens.get() + 1);
            Ok(Cursor::new(Vec::new()))
        },
    );
    assert_eq!(result.unwrap_err(), VerifyError::ArtifactSizeLimitExceeded);
    assert_eq!(opens.get(), 0);

    let result = verified.verify_objects(
        &EvidenceObjectVerificationPolicy {
            max_object_bytes: 5,
            max_total_bytes: 9,
        },
        |_| {
            opens.set(opens.get() + 1);
            Ok(Cursor::new(Vec::new()))
        },
    );
    assert_eq!(
        result.unwrap_err(),
        VerifyError::ArtifactTotalSizeLimitExceeded
    );
    assert_eq!(opens.get(), 0);

    let overflow = authenticate(vec![
        EvidenceArtifact {
            size_bytes: u64::MAX,
            ..artifact("objects/huge.bin", b"")
        },
        EvidenceArtifact {
            size_bytes: 1,
            ..artifact("objects/one-more.bin", b"")
        },
    ]);
    assert_eq!(
        overflow
            .verify_objects(
                &EvidenceObjectVerificationPolicy {
                    max_object_bytes: u64::MAX,
                    max_total_bytes: u64::MAX,
                },
                |_| {
                    opens.set(opens.get() + 1);
                    Ok(Cursor::new(Vec::new()))
                },
            )
            .unwrap_err(),
        VerifyError::ArtifactTotalSizeLimitExceeded
    );
    assert_eq!(opens.get(), 0);

    let mut mutated = verified;
    mutated.bundle.evidence[0].size_bytes += 1;
    assert_eq!(
        mutated
            .verify_objects(&EvidenceObjectVerificationPolicy::default(), |_| {
                opens.set(opens.get() + 1);
                Ok(Cursor::new(Vec::new()))
            })
            .unwrap_err(),
        VerifyError::EvidenceDigestMismatch
    );
    assert_eq!(opens.get(), 0);
}

#[test]
fn rejects_coherently_rehashed_metadata_substitution_before_opening() {
    let mut verified = authenticate(vec![artifact("objects/authenticated.bin", b"trusted")]);
    let substituted_bytes = b"not authenticated";
    verified.bundle.evidence = vec![artifact("objects/substituted.bin", substituted_bytes)];
    verified.bundle.refresh_evidence_digest().unwrap();
    verified.canonical_signing_bytes = verified.bundle.canonical_signing_bytes().unwrap();
    verified.authenticated_bundle_digest = sha256_hex(&verified.canonical_signing_bytes);

    let opens = Cell::new(0);
    let result = verified.verify_objects(
        &EvidenceObjectVerificationPolicy::default(),
        |_| -> Result<Cursor<Vec<u8>>, VerifyError> {
            opens.set(opens.get() + 1);
            Ok(Cursor::new(substituted_bytes.to_vec()))
        },
    );

    assert_eq!(result.unwrap_err(), VerifyError::EvidenceDigestMismatch);
    assert_eq!(opens.get(), 0);
}

#[test]
fn verifies_fixture_tree_from_a_canonical_local_root() {
    let verified = authenticate(fixture_evidence());
    let root = LocalEvidenceObjectRoot::new(fixture_root()).unwrap();
    assert_eq!(
        root.canonical_path(),
        fs::canonicalize(fixture_root()).unwrap()
    );

    let result = root
        .verify(&verified, &EvidenceObjectVerificationPolicy::default())
        .unwrap();

    assert_eq!(result.objects.len(), 2);
    assert_eq!(
        result.total_size_bytes,
        result
            .objects
            .iter()
            .map(|object| object.size_bytes)
            .sum::<u64>()
    );
}

#[test]
fn local_verifier_rejects_size_digest_non_file_and_duplicate_hard_link_refs() {
    let temp = tempfile::tempdir().unwrap();
    fs::write(temp.path().join("object.bin"), b"abcdef").unwrap();

    let oversized = authenticate(vec![artifact("object.bin", b"abcde")]);
    assert_eq!(
        oversized
            .verify_local_objects(temp.path(), &EvidenceObjectVerificationPolicy::default())
            .unwrap_err(),
        VerifyError::ArtifactOversize
    );

    let undersized = authenticate(vec![EvidenceArtifact {
        size_bytes: 7,
        ..artifact("object.bin", b"abcdef")
    }]);
    assert_eq!(
        undersized
            .verify_local_objects(temp.path(), &EvidenceObjectVerificationPolicy::default())
            .unwrap_err(),
        VerifyError::ArtifactUndersize
    );

    let digest_mismatch = authenticate(vec![artifact("object.bin", b"xxxxxx")]);
    assert_eq!(
        digest_mismatch
            .verify_local_objects(temp.path(), &EvidenceObjectVerificationPolicy::default())
            .unwrap_err(),
        VerifyError::ArtifactDigestMismatch
    );

    fs::create_dir(temp.path().join("directory.bin")).unwrap();
    let directory = authenticate(vec![artifact("directory.bin", b"")]);
    assert_eq!(
        directory
            .verify_local_objects(temp.path(), &EvidenceObjectVerificationPolicy::default())
            .unwrap_err(),
        VerifyError::ArtifactNotRegularFile
    );

    fs::hard_link(
        temp.path().join("object.bin"),
        temp.path().join("same-object.bin"),
    )
    .unwrap();
    let duplicate = authenticate(vec![
        artifact("object.bin", b"abcdef"),
        artifact("same-object.bin", b"abcdef"),
    ]);
    assert_eq!(
        duplicate
            .verify_local_objects(temp.path(), &EvidenceObjectVerificationPolicy::default())
            .unwrap_err(),
        VerifyError::DuplicateArtifactReference
    );
}

#[test]
fn local_verifier_rejects_symlinked_leaf_and_intermediate_components() {
    let temp = tempfile::tempdir().unwrap();
    let real_directory = temp.path().join("real");
    fs::create_dir(&real_directory).unwrap();
    fs::write(real_directory.join("object.bin"), b"linked bytes").unwrap();

    if create_file_symlink(
        &real_directory.join("object.bin"),
        &temp.path().join("leaf.bin"),
    )
    .is_err()
    {
        return;
    }
    create_directory_symlink(&real_directory, &temp.path().join("linked-directory")).unwrap();

    for path in ["leaf.bin", "linked-directory/object.bin"] {
        let verified = authenticate(vec![artifact(path, b"linked bytes")]);
        assert_eq!(
            verified
                .verify_local_objects(temp.path(), &EvidenceObjectVerificationPolicy::default())
                .unwrap_err(),
            VerifyError::ArtifactSymlinkRejected,
            "{path}"
        );
    }
}

#[test]
fn local_root_rejects_files_symlinks_and_path_rebinding() {
    let temp = tempfile::tempdir().unwrap();
    let not_directory = tempfile::NamedTempFile::new_in(temp.path()).unwrap();
    assert_eq!(
        LocalEvidenceObjectRoot::new(not_directory.path()).unwrap_err(),
        VerifyError::ArtifactRootNotDirectory
    );

    let root = temp.path().join("root");
    fs::create_dir(&root).unwrap();
    fs::write(root.join("object.bin"), b"stable").unwrap();
    let anchored = LocalEvidenceObjectRoot::new(&root).unwrap();
    let moved = temp.path().join("moved-root");
    if fs::rename(&root, &moved).is_ok() {
        fs::create_dir(&root).unwrap();
        fs::write(root.join("object.bin"), b"stable").unwrap();
        let verified = authenticate(vec![artifact("object.bin", b"stable")]);
        assert_eq!(
            anchored
                .verify(&verified, &EvidenceObjectVerificationPolicy::default())
                .unwrap_err(),
            VerifyError::ArtifactChangedDuringVerification
        );
    }

    let linked_root = temp.path().join("linked-root");
    if create_directory_symlink(&moved, &linked_root).is_ok() {
        assert_eq!(
            LocalEvidenceObjectRoot::new(linked_root).unwrap_err(),
            VerifyError::ArtifactSymlinkRejected
        );
    }
}

#[test]
fn cli_authenticates_scope_then_streams_the_local_fixture_tree() {
    let verified = authenticate(fixture_evidence());
    let bundle_file = tempfile::NamedTempFile::new().unwrap();
    fs::write(
        bundle_file.path(),
        serde_json::to_vec(&verified.bundle).unwrap(),
    )
    .unwrap();
    let total_size: u64 = verified
        .bundle
        .evidence
        .iter()
        .map(|item| item.size_bytes)
        .sum();
    let max_size = verified
        .bundle
        .evidence
        .iter()
        .map(|item| item.size_bytes)
        .max()
        .unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_releasefoundry-runtime-verify"))
        .args([
            "verify-signed-bundle-objects",
            bundle_file.path().to_str().unwrap(),
            "--key-env",
            KEY_ENV,
            "--now-ms",
            &NOW_UNIX_MS.to_string(),
            "--expected-tenant-digest",
            &verified.bundle.tenant_digest,
            "--expected-project-digest",
            &verified.bundle.project_digest,
            "--object-root",
            fixture_root().to_str().unwrap(),
            "--max-object-bytes",
            &max_size.to_string(),
            "--max-total-bytes",
            &total_size.to_string(),
        ])
        .env(KEY_ENV, std::str::from_utf8(KEY).unwrap())
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let result: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["objects_verified"], 2);
    assert_eq!(result["verification_level"], "objects_verified");
    assert_eq!(result["manifest_authenticated"], true);
    assert_eq!(result["object_verification_performed"], true);
    assert_eq!(result["total_size_bytes"], total_size);
    assert!(!String::from_utf8_lossy(&output.stdout).contains(std::str::from_utf8(KEY).unwrap()));

    let missing_root = temp_missing_root();
    let wrong_scope = Command::new(env!("CARGO_BIN_EXE_releasefoundry-runtime-verify"))
        .args([
            "verify-signed-bundle-objects",
            bundle_file.path().to_str().unwrap(),
            "--key-env",
            KEY_ENV,
            "--now-ms",
            &NOW_UNIX_MS.to_string(),
            "--expected-tenant-digest",
            &digest("wrong-tenant"),
            "--object-root",
            missing_root.to_str().unwrap(),
        ])
        .env(KEY_ENV, std::str::from_utf8(KEY).unwrap())
        .output()
        .unwrap();
    assert!(!wrong_scope.status.success());
    assert!(String::from_utf8_lossy(&wrong_scope.stderr).contains("tenant_digest mismatch"));
}

fn temp_missing_root() -> PathBuf {
    let parent = tempfile::tempdir().unwrap();
    parent.path().join("missing-object-root")
}

#[cfg(unix)]
fn create_file_symlink(source: &Path, destination: &Path) -> io::Result<()> {
    std::os::unix::fs::symlink(source, destination)
}

#[cfg(windows)]
fn create_file_symlink(source: &Path, destination: &Path) -> io::Result<()> {
    std::os::windows::fs::symlink_file(source, destination)
}

#[cfg(unix)]
fn create_directory_symlink(source: &Path, destination: &Path) -> io::Result<()> {
    std::os::unix::fs::symlink(source, destination)
}

#[cfg(windows)]
fn create_directory_symlink(source: &Path, destination: &Path) -> io::Result<()> {
    std::os::windows::fs::symlink_dir(source, destination)
}
