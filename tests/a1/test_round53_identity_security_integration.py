from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
GO_PACKAGE = ROOT / "packages" / "go" / "ashrclone"
RUST_CRATE = ROOT / "packages" / "rust" / "ashr-runtime-verify"
TS_PACKAGE = ROOT / "packages" / "ts" / "ashr-clone"
MIGRATIONS = ROOT / "services" / "api" / "migrations"
SESSION_MIGRATIONS = (
    MIGRATIONS / "013_a1_identity_session_lifecycle.sql",
    MIGRATIONS / "014_a1_identity_delivery_outbox.sql",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _assert_ok(result: subprocess.CompletedProcess[str], label: str) -> None:
    assert result.returncode == 0, (
        f"{label} failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _go_function(source: str, name: str) -> str:
    match = re.search(rf"^func (?:\([^\n]+\) )?{re.escape(name)}\(", source, re.MULTILINE)
    assert match is not None, f"Go function {name} is missing"
    next_function = re.search(r"^func ", source[match.end() :], re.MULTILINE)
    end = len(source) if next_function is None else match.end() + next_function.start()
    return source[match.start() : end]


def _sql_regex_patterns() -> list[tuple[Path, str]]:
    patterns: list[tuple[Path, str]] = []
    operand = re.compile(r"(?:!~|(?<![!])~)\s*'((?:''|[^'])*)'", re.DOTALL)
    for migration in SESSION_MIGRATIONS:
        for match in operand.finditer(_read(migration)):
            patterns.append((migration, match.group(1).replace("''", "'")))
    return patterns


def test_production_verification_start_is_transactional_outbox_only() -> None:
    service_source = _read(GO_PACKAGE / "identity_verification.go")
    postgres_source = _read(GO_PACKAGE / "identity_verification_postgres.go")
    constructor = _go_function(service_source, "NewIdentityVerificationService")
    start = _go_function(service_source, "Start")

    assert "production identity verification must use transactional outbox delivery" in constructor
    assert "transactional outbox delivery requires a production identity verification store" in constructor
    assert "if productionStore" in constructor
    assert "deliveryMode = IdentityVerificationDeliveryTransactionalOutbox" in constructor
    assert re.search(
        r"sender := options\.Sender\s+if deliveryMode == "
        r"IdentityVerificationDeliveryTransactionalOutbox \{\s+sender = nil\s+\}",
        constructor,
    )

    outbox_return = start.index(
        "if service.deliveryMode == IdentityVerificationDeliveryTransactionalOutbox"
    )
    delivery_material = start.index("delivery := IdentityVerificationDelivery{")
    sender_call = start.index("service.sender.SendIdentityVerification")
    assert outbox_return < start.index("return result, nil", outbox_return) < delivery_material
    assert delivery_material < sender_call

    assert "func (*PostgresIdentityVerificationStore) IsProductionIdentityVerificationStore()" in postgres_source
    assert "func (*PostgresIdentityVerificationStore) UsesTransactionalIdentityVerificationOutbox()" in postgres_source


def test_session_issuance_and_resolution_share_one_hmac_codec() -> None:
    production_source = _read(GO_PACKAGE / "production_identity_store.go")
    verification_source = _read(GO_PACKAGE / "identity_verification_postgres.go")
    issue = _go_function(production_source, "issue")
    issue_refresh = _go_function(production_source, "issueRefresh")
    issue_with_prefix = _go_function(production_source, "issueWithPrefix")
    digest = _go_function(production_source, "digest")
    digest_refresh = _go_function(production_source, "digestRefresh")
    access_parser = _go_function(production_source, "keyVersionForBearer")
    resolver = _go_function(production_source, "resolveSession")
    verification_factory = _go_function(
        production_source,
        "NewIdentityVerificationStore",
    )
    completion = _go_function(verification_source, "completeIdentityVerification")

    assert "return codec.issueWithPrefix(identitySessionBearerPrefix)" in issue
    assert "return codec.issueWithPrefix(identityRefreshBearerPrefix)" in issue_refresh
    assert "digest:     identitySessionHMAC(key, bearer)" in issue_with_prefix
    assert "return identitySessionHMAC(key, bearer), version, nil" in digest
    assert "return identitySessionHMAC(key, bearer), version, nil" in digest_refresh
    assert "identityRefreshBearerPrefix" in digest_refresh
    assert "strings.HasPrefix(bearer, identityRefreshBearerPrefix" in access_parser
    assert "options.sessionTokens = store.sessionTokens" in verification_factory
    assert "digest, _, err := store.sessionTokens.digest(token)" in resolver
    assert "a1_authenticate_identity_session_digest($1)" in resolver
    assert re.search(r"`,\s*digest\)\.Scan\(", resolver)

    issue_index = completion.index("sessionToken, err = store.sessionTokens.issue()")
    refresh_issue_index = completion.index(
        "refreshToken, err = store.sessionTokens.issueRefresh()"
    )
    mutation_call_start = completion.index(
        "mutationResult, err := coordinator.applyIdentityMutationTx("
    )
    mutation_index = completion.index(
        "sessionToken.digest, refreshToken.digest,",
        mutation_call_start,
    )
    commit_index = completion.index("if err := tx.Commit(); err != nil")
    receipt_index = completion.index("newIdentitySessionIssuanceReceiptWithRefresh(")
    assert (
        issue_index
        < refresh_issue_index
        < mutation_call_start
        < mutation_index
        < commit_index
        < receipt_index
    )
    mutation_call = completion[mutation_call_start:commit_index]
    assert "sessionToken.digest, refreshToken.digest," in mutation_call
    assert "sessionToken.bearer" not in mutation_call
    assert "refreshToken.bearer" not in mutation_call
    assert "sessionToken.bearer" in completion[commit_index:]
    assert "refreshToken.bearer" in completion[commit_index:]

    go = shutil.which("go")
    assert go is not None, "Go is required for the Round 53 identity contract"
    result = _run(
        [
            go,
            "test",
            "-count=1",
            "-run",
            "^(TestIdentityVerificationProductionStartUsesOnlyTransactionalOutbox|"
            "TestPostgresIdentityVerificationIssuesOneTimeBearerWithResolverDigestLineage|"
            "TestProductionIdentityStoreSessionKeyRotationResolvesVersionedAndLegacyBearers)$",
            ".",
        ],
        cwd=GO_PACKAGE,
    )
    _assert_ok(result, "Go outbox and session HMAC executable contracts")


def test_postgres_are_regex_bounds_never_exceed_255() -> None:
    patterns = _sql_regex_patterns()
    assert patterns, "session/outbox migrations must expose regex constraints"

    violations: list[str] = []
    quantifier = re.compile(r"(?<!\\)\{(\d+)(?:,(\d*))?\}")
    for migration, pattern in patterns:
        for match in quantifier.finditer(pattern):
            lower = int(match.group(1))
            upper_text = match.group(2)
            upper = lower if upper_text is None else (
                int(upper_text) if upper_text else None
            )
            if lower > 255 or (upper is not None and upper > 255):
                violations.append(
                    f"{migration.name}: {match.group(0)} in {pattern!r}"
                )

    assert not violations, (
        "PostgreSQL ARE repetition bounds must be <= 255; use a length "
        "constraint plus an unbounded quantifier instead:\n" + "\n".join(violations)
    )


def test_postgres_16_compiles_every_session_and_outbox_regex() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker is unavailable for the PostgreSQL ARE compile check")

    container = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "ashr-oauth-pg-test")
    running = _run(
        [docker, "inspect", "-f", "{{.State.Running}}", container],
    )
    if running.returncode != 0 or running.stdout.strip() != "true":
        pytest.skip(f"PostgreSQL container {container!r} is not running")

    version = _run(
        [
            docker,
            "exec",
            container,
            "psql",
            "-X",
            "-A",
            "-t",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-c",
            "SHOW server_version_num;",
        ]
    )
    _assert_ok(version, "PostgreSQL version probe")
    assert int(version.stdout.strip()) >= 160000

    failures: list[str] = []
    for migration, pattern in _sql_regex_patterns():
        encoded = base64.b64encode(pattern.encode("utf-8")).decode("ascii")
        query = (
            "SELECT '' ~ convert_from(decode('"
            + encoded
            + "', 'base64'), 'UTF8');"
        )
        compiled = _run(
            [
                docker,
                "exec",
                container,
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-A",
                "-t",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-c",
                query,
            ]
        )
        if compiled.returncode != 0:
            failures.append(
                f"{migration.name}: {pattern!r}\n{compiled.stderr.strip()}"
            )
    assert not failures, "PostgreSQL rejected migration regexes:\n" + "\n".join(failures)


def test_rust_manifest_and_object_verification_cli_are_distinct(tmp_path: Path) -> None:
    main_source = _read(RUST_CRATE / "src" / "main.rs")
    assert '"verify-signed-bundle" => verify_authenticated_bundle(&input, args, false)' in main_source
    assert '"verify-signed-bundle-objects" => verify_authenticated_bundle(&input, args, true)' in main_source
    assert r'\"verification_level\":\"manifest_authenticated\"' in main_source
    assert r'\"object_verification_performed\":false' in main_source
    assert r'\"verification_level\":\"objects_verified\"' in main_source
    assert r'\"object_verification_performed\":true' in main_source
    assert '"--object-root" if allow_object_root' in main_source
    assert "verify-signed-bundle-objects requires --object-root <PATH>" in main_source

    cargo = shutil.which("cargo")
    assert cargo is not None, "Cargo is required for the Round 53 verifier contract"
    build = _run(
        [cargo, "build", "--quiet", "--bin", "ashr-runtime-verify"],
        cwd=RUST_CRATE,
    )
    _assert_ok(build, "Rust verifier build")

    binary = RUST_CRATE / "target" / "debug" / (
        "ashr-runtime-verify.exe" if os.name == "nt" else "ashr-runtime-verify"
    )
    invalid_bundle = tmp_path / "bundle.json"
    invalid_bundle.write_text("{}\n", encoding="utf-8")
    env = os.environ.copy()
    env["ASHR_ROUND53_TEST_HMAC_KEY"] = "round53-test-only-key-material-00000001"

    manifest_with_root = _run(
        [
            str(binary),
            "verify-signed-bundle",
            str(invalid_bundle),
            "--key-env",
            "ASHR_ROUND53_TEST_HMAC_KEY",
            "--object-root",
            str(tmp_path),
        ],
        cwd=RUST_CRATE,
        env=env,
    )
    assert manifest_with_root.returncode != 0
    assert "usage:" in manifest_with_root.stderr

    objects_without_root = _run(
        [
            str(binary),
            "verify-signed-bundle-objects",
            str(invalid_bundle),
            "--key-env",
            "ASHR_ROUND53_TEST_HMAC_KEY",
        ],
        cwd=RUST_CRATE,
        env=env,
    )
    assert objects_without_root.returncode != 0
    assert (
        "verify-signed-bundle-objects requires --object-root <PATH>"
        in objects_without_root.stderr
    )


def test_typescript_clean_build_and_typed_subpath_parity(tmp_path: Path) -> None:
    npm = shutil.which("npm")
    node = shutil.which("node")
    assert npm is not None and node is not None, (
        "Node.js and npm are required for the TypeScript package contract"
    )

    package_copy = tmp_path / "ashr-clone-ts"
    shutil.copytree(
        TS_PACKAGE,
        package_copy,
        ignore=shutil.ignore_patterns("dist", "node_modules"),
    )
    shutil.copytree(
        TS_PACKAGE / "node_modules",
        package_copy / "node_modules",
        ignore=shutil.ignore_patterns(".bin"),
    )
    stale = package_copy / "dist" / "stale-round53-sentinel.js"
    stale.parent.mkdir(parents=True)
    stale.write_text("throw new Error('stale output loaded');\n", encoding="utf-8")

    build_env = os.environ.copy()
    compiler_bin = TS_PACKAGE / "node_modules" / ".bin"
    build_env["PATH"] = str(compiler_bin) + os.pathsep + build_env.get("PATH", "")
    build = _run([npm, "run", "build"], cwd=package_copy, env=build_env)
    _assert_ok(build, "TypeScript clean build")
    assert not stale.exists(), "prebuild must remove stale dist artifacts"

    metadata = json.loads(_read(package_copy / "package.json"))
    exports = metadata["exports"]
    required_round53_subpaths = {
        ".",
        "./capability-matrix",
        "./evidence",
        "./session-lifecycle",
        "./unified-identity",
    }
    assert required_round53_subpaths <= exports.keys()

    for subpath, targets in exports.items():
        assert set(targets) == {"types", "import"}, subpath
        for target_kind, target in targets.items():
            artifact = package_copy / target.removeprefix("./")
            assert artifact.is_file(), f"{subpath} {target_kind} target is missing: {target}"

    consumer = tmp_path / "consumer"
    installed = consumer / "node_modules" / "@ashr-clone" / "sdk"
    installed.parent.mkdir(parents=True)
    shutil.copytree(package_copy, installed)
    specifiers = [
        metadata["name"] if subpath == "." else metadata["name"] + subpath[1:]
        for subpath in exports
    ]
    probe = consumer / "probe.mjs"
    probe.write_text(
        "const specs = JSON.parse(process.env.ASHR_ROUND53_SUBPATHS);\n"
        "for (const spec of specs) {\n"
        "  const loaded = await import(spec);\n"
        "  if (Object.keys(loaded).length === 0) throw new Error(`${spec} is empty`);\n"
        "}\n"
        "process.stdout.write(JSON.stringify({ loaded: specs.length }));\n",
        encoding="utf-8",
    )
    probe_env = os.environ.copy()
    probe_env["ASHR_ROUND53_SUBPATHS"] = json.dumps(specifiers)
    imported = _run([node, str(probe)], cwd=consumer, env=probe_env)
    _assert_ok(imported, "TypeScript exported-subpath import probe")
    assert json.loads(imported.stdout) == {"loaded": len(specifiers)}

    parity = _run(
        [
            shutil.which("python") or "python",
            str(ROOT / "tests" / "a1" / "ts_python_parity_matrix.py"),
            "--check",
        ]
    )
    _assert_ok(parity, "Python/TypeScript generated parity contract")
