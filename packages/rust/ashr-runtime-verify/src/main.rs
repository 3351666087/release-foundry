use std::env;
use std::fs;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use ashr_runtime_verify::{
    canonical_json, sha256_hex, AllowFreshReplayGuard, AuthenticatedEnvelope,
    AuthenticatedEvidenceBundle, HmacSha256Verifier, VerificationPolicy,
};
use serde_json::Value;

const MAX_INPUT_BYTES: usize = 10 * 1024 * 1024;
const SECRET_MARKERS: [&str; 5] = [
    "sk-",
    concat!("Bearer", " "),
    concat!("ASHR_API_KEY", "="),
    concat!("ASHR_LABS_API_KEY", "="),
    "tp_",
];
const RUNTIME_MARKERS: [&str; 5] = [
    "local_cloud_state",
    "run_results",
    "status_history",
    "ashr.clone",
    "a2.regression_replay",
];

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(usage)?;
    let path = args.next().ok_or_else(usage)?;

    let input = read_bounded(Path::new(&path))?;
    match command.as_str() {
        "verify" => {
            ensure_no_more_args(args)?;
            let report = verify_input(&input)?;
            println!(
                "{{\"status\":\"ok\",\"bytes\":{},\"runtime_markers\":{},\"queued_or_running\":{}}}",
                input.len(),
                report.runtime_markers,
                report.queued_or_running
            );
            Ok(())
        }
        "replay-plan" => {
            ensure_no_more_args(args)?;
            let report = verify_input(&input)?;
            println!(
                "{{\"schema_version\":\"ashr.runtime.replay_plan.v1\",\"source_bytes\":{},\"candidate_statuses\":[\"queued\",\"running\"],\"candidate_count\":{},\"action\":\"replay-queued\"}}",
                input.len(),
                report.queued_or_running
            );
            Ok(())
        }
        "verify-bundle" => {
            ensure_no_more_args(args)?;
            let report = verify_bundle(&input)?;
            println!(
                "{{\"status\":\"ok\",\"schema_version\":\"{}\",\"evidence_sha256\":\"{}\",\"evidence_items\":{}}}",
                json_escape(&report.schema_version),
                report.evidence_sha256,
                report.evidence_items
            );
            Ok(())
        }
        "canonicalize" => {
            ensure_no_more_args(args)?;
            println!(
                "{}",
                canonical_json(&input).map_err(|error| error.to_string())?
            );
            Ok(())
        }
        "verify-envelope" => verify_authenticated_envelope(&input, args),
        "verify-signed-bundle" => verify_authenticated_bundle(&input, args),
        _ => Err(usage()),
    }
}

fn verify_authenticated_bundle(
    input: &str,
    args: impl Iterator<Item = String>,
) -> Result<(), String> {
    let VerificationArguments {
        key_env,
        now_unix_ms,
    } = parse_verification_arguments(args, "verify-signed-bundle")?;
    let key = read_verification_key(&key_env)?;
    let bundle =
        AuthenticatedEvidenceBundle::parse_strict(input).map_err(|error| error.to_string())?;
    let verifier = HmacSha256Verifier::new(&bundle.key_id, key.as_bytes())
        .map_err(|error| error.to_string())?;
    let verified = bundle
        .verify(
            &verifier,
            &VerificationPolicy::at(now_unix_ms.unwrap_or_else(current_unix_ms)),
        )
        .map_err(|error| error.to_string())?;
    println!(
        "{{\"status\":\"ok\",\"schema_version\":\"{}\",\"algorithm\":\"{}\",\"key_id\":\"{}\",\"authenticated_bundle_digest\":\"{}\",\"evidence_digest\":\"{}\",\"evidence_items\":{},\"expires_at_unix_ms\":{}}}",
        json_escape(&verified.bundle.schema_version),
        json_escape(&verified.bundle.algorithm),
        json_escape(&verified.bundle.key_id),
        verified.authenticated_bundle_digest,
        verified.bundle.evidence_digest,
        verified.bundle.evidence.len(),
        verified.bundle.expires_at_unix_ms,
    );
    Ok(())
}

fn verify_authenticated_envelope(
    input: &str,
    args: impl Iterator<Item = String>,
) -> Result<(), String> {
    let VerificationArguments {
        key_env,
        now_unix_ms,
    } = parse_verification_arguments(args, "verify-envelope")?;
    let key = read_verification_key(&key_env)?;
    let envelope = AuthenticatedEnvelope::parse_strict(input).map_err(|error| error.to_string())?;
    let verifier = HmacSha256Verifier::new(&envelope.key_id, key.as_bytes())
        .map_err(|error| error.to_string())?;
    let now_unix_ms = now_unix_ms.unwrap_or_else(current_unix_ms);
    let verified = envelope
        .verify(
            &verifier,
            &AllowFreshReplayGuard,
            &VerificationPolicy::at(now_unix_ms),
        )
        .map_err(|error| error.to_string())?;
    println!(
        "{{\"status\":\"ok\",\"schema_version\":\"{}\",\"algorithm\":\"{}\",\"key_id\":\"{}\",\"envelope_digest\":\"{}\",\"event_id_digest\":\"{}\",\"idempotency_key_digest\":\"{}\",\"request_digest\":\"{}\",\"nonce_digest\":\"{}\",\"expires_at_unix_ms\":{}}}",
        json_escape(&verified.envelope.schema_version),
        json_escape(&verified.envelope.algorithm),
        json_escape(&verified.envelope.key_id),
        verified.envelope_digest,
        verified.replay_guard.event_id_digest,
        verified.replay_guard.idempotency_key_digest,
        verified.replay_guard.request_digest,
        verified.replay_guard.nonce_digest,
        verified.replay_guard.expires_at_unix_ms,
    );
    Ok(())
}

struct VerificationArguments {
    key_env: String,
    now_unix_ms: Option<u64>,
}

fn parse_verification_arguments(
    mut args: impl Iterator<Item = String>,
    command: &str,
) -> Result<VerificationArguments, String> {
    let mut key_env = None;
    let mut now_unix_ms = None;
    while let Some(flag) = args.next() {
        match flag.as_str() {
            "--key-env" => key_env = Some(args.next().ok_or_else(usage)?),
            "--now-ms" => {
                now_unix_ms = Some(
                    args.next()
                        .ok_or_else(usage)?
                        .parse::<u64>()
                        .map_err(|_| "--now-ms must be an unsigned integer".to_string())?,
                )
            }
            _ => return Err(usage()),
        }
    }
    let key_env = key_env.ok_or_else(|| format!("{command} requires --key-env <NAME>"))?;
    validate_environment_name(&key_env)?;
    Ok(VerificationArguments {
        key_env,
        now_unix_ms,
    })
}

fn read_verification_key(key_env: &str) -> Result<String, String> {
    let key = env::var_os(key_env)
        .ok_or_else(|| format!("verification key environment variable {key_env} is not set"))?;
    key.into_string()
        .map_err(|_| "verification key environment value must be UTF-8".to_string())
}

fn current_unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .try_into()
        .unwrap_or(u64::MAX)
}

fn validate_environment_name(name: &str) -> Result<(), String> {
    if name.is_empty()
        || name.len() > 128
        || !name
            .bytes()
            .all(|byte| byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'_')
    {
        return Err("--key-env must name an uppercase environment variable".to_string());
    }
    Ok(())
}

fn ensure_no_more_args(mut args: impl Iterator<Item = String>) -> Result<(), String> {
    if args.next().is_some() {
        return Err(usage());
    }
    Ok(())
}

#[derive(Debug, Clone, Copy)]
struct VerifyReport {
    runtime_markers: usize,
    queued_or_running: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct BundleReport {
    schema_version: String,
    evidence_sha256: String,
    evidence_items: usize,
}

fn read_bounded(path: &Path) -> Result<String, String> {
    let metadata = fs::metadata(path)
        .map_err(|error| format!("failed to read metadata for {}: {error}", path.display()))?;
    if metadata.len() as usize > MAX_INPUT_BYTES {
        return Err(format!(
            "input {} exceeds {} bytes",
            path.display(),
            MAX_INPUT_BYTES
        ));
    }
    let input = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {} as UTF-8 text: {error}", path.display()))?;
    Ok(input.trim_start_matches('\u{feff}').to_string())
}

fn verify_input(input: &str) -> Result<VerifyReport, String> {
    let trimmed = input.trim_start();
    if !trimmed.starts_with('{') && !trimmed.starts_with('[') {
        return Err("input does not look like a JSON object or array".to_string());
    }
    if !brackets_are_balanced(input) {
        return Err("input JSON delimiters are not balanced".to_string());
    }
    if let Some(marker) = SECRET_MARKERS
        .iter()
        .find(|marker| input.contains(**marker))
    {
        return Err(format!("input contains secret-like marker: {marker}"));
    }
    let runtime_markers = RUNTIME_MARKERS
        .iter()
        .filter(|marker| input.contains(**marker))
        .count();
    if runtime_markers == 0 {
        return Err("input does not contain a recognized Ashr runtime marker".to_string());
    }
    Ok(VerifyReport {
        runtime_markers,
        queued_or_running: count_status(input, "queued") + count_status(input, "running"),
    })
}

fn verify_bundle(input: &str) -> Result<BundleReport, String> {
    reject_secret_markers(input)?;

    let root: Value =
        serde_json::from_str(input).map_err(|error| format!("input is not valid JSON: {error}"))?;
    let object = root
        .as_object()
        .ok_or_else(|| "bundle must be a JSON object".to_string())?;
    let schema_version = string_field(object, "schema_version")?;
    if schema_version != "ashr.a1.evidence_bundle.v1" {
        return Err(format!(
            "unsupported bundle schema_version: {schema_version}"
        ));
    }

    let evidence = object
        .get("evidence")
        .ok_or_else(|| "bundle missing evidence".to_string())?;
    let evidence_items = match evidence {
        Value::Array(items) => items.len(),
        Value::Object(items) => items.len(),
        _ => return Err("bundle evidence must be an array or object".to_string()),
    };
    if evidence_items == 0 {
        return Err("bundle evidence must not be empty".to_string());
    }

    let expected_sha256 = string_field(object, "evidence_sha256")?;
    if !is_lower_hex_sha256(&expected_sha256) {
        return Err("bundle evidence_sha256 must be 64 lowercase hex characters".to_string());
    }

    let canonical_evidence = ashr_runtime_verify::canonical_json_bytes(evidence)
        .map_err(|error| format!("failed to canonicalize evidence JSON: {error}"))?;
    let actual_sha256 = sha256_hex(&canonical_evidence);
    if expected_sha256 != actual_sha256 {
        return Err(format!(
            "bundle evidence_sha256 mismatch: expected {expected_sha256}, computed {actual_sha256}"
        ));
    }

    Ok(BundleReport {
        schema_version,
        evidence_sha256: expected_sha256,
        evidence_items,
    })
}

fn reject_secret_markers(input: &str) -> Result<(), String> {
    if let Some(marker) = SECRET_MARKERS
        .iter()
        .find(|marker| input.contains(**marker))
    {
        return Err(format!("input contains secret-like marker: {marker}"));
    }
    Ok(())
}

fn string_field(
    object: &serde_json::Map<String, Value>,
    field_name: &str,
) -> Result<String, String> {
    object
        .get(field_name)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| format!("bundle missing string field {field_name}"))
}

fn is_lower_hex_sha256(candidate: &str) -> bool {
    ashr_runtime_verify::is_lower_hex_sha256(candidate)
}

fn json_escape(input: &str) -> String {
    input.replace('\\', "\\\\").replace('"', "\\\"")
}

fn count_status(input: &str, status: &str) -> usize {
    let needle = format!("\"status\":\"{status}\"");
    let spaced = format!("\"status\": \"{status}\"");
    input.matches(&needle).count() + input.matches(&spaced).count()
}

fn brackets_are_balanced(input: &str) -> bool {
    let mut stack = Vec::new();
    let mut in_string = false;
    let mut escaped = false;

    for character in input.chars() {
        if in_string {
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '"' {
                in_string = false;
            }
            continue;
        }

        match character {
            '"' => in_string = true,
            '{' | '[' => stack.push(character),
            '}' => {
                if stack.pop() != Some('{') {
                    return false;
                }
            }
            ']' if stack.pop() != Some('[') => return false,
            ']' => {}
            _ => {}
        }
    }

    !in_string && stack.is_empty()
}

fn usage() -> String {
    "usage: ashr-runtime-verify <verify|replay-plan|verify-bundle|canonicalize> <json-path>\n       ashr-runtime-verify <verify-envelope|verify-signed-bundle> <json-path> --key-env <NAME> [--now-ms <MILLISECONDS>]".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn verifies_local_cloud_state() {
        let report = verify_input(
            r#"{"kind":"local_cloud_state","runs":[{"status":"queued"},{"status": "running"}]}"#,
        )
        .unwrap();
        assert_eq!(report.runtime_markers, 1);
        assert_eq!(report.queued_or_running, 2);
    }

    #[test]
    fn rejects_secret_markers() {
        let payload = format!(
            r#"{{"kind":"local_cloud_state","token":"{}abc"}}"#,
            concat!("Bearer", " ")
        );
        let error = verify_input(&payload).unwrap_err();
        assert!(error.contains("secret-like marker"));
    }

    #[test]
    fn detects_unbalanced_json_delimiters() {
        assert!(!brackets_are_balanced(r#"{"kind":"local_cloud_state""#));
        assert!(brackets_are_balanced(
            r#"{"kind":"local_cloud_state","text":"}"}"#
        ));
    }

    #[test]
    fn verifies_legacy_integrity_evidence_bundle() {
        let evidence =
            r#"[{"artifact":"docs/a1/evidence/commands.md","sha256":"abc123","status":"passed"}]"#;
        let digest = sha256_hex(evidence.as_bytes());
        let bundle = format!(
            r#"{{"schema_version":"ashr.a1.evidence_bundle.v1","evidence_sha256":"{digest}","evidence":{evidence}}}"#
        );

        let report = verify_bundle(&bundle).unwrap();

        assert_eq!(report.schema_version, "ashr.a1.evidence_bundle.v1");
        assert_eq!(report.evidence_sha256, digest);
        assert_eq!(report.evidence_items, 1);
    }

    #[test]
    fn rejects_tampered_evidence_bundle() {
        let original = r#"[{"artifact":"docs/a1/evidence/commands.md","status":"passed"}]"#;
        let tampered = r#"[{"artifact":"docs/a1/evidence/commands.md","status":"failed"}]"#;
        let digest = sha256_hex(original.as_bytes());
        let bundle = format!(
            r#"{{"schema_version":"ashr.a1.evidence_bundle.v1","evidence_sha256":"{digest}","evidence":{tampered}}}"#
        );

        let error = verify_bundle(&bundle).unwrap_err();

        assert!(error.contains("evidence_sha256 mismatch"));
    }

    #[test]
    fn rejects_secret_marker_in_evidence_bundle() {
        let evidence = format!(
            r#"{{"artifact":"docs/a1/evidence/commands.md","token":"{}abc"}}"#,
            concat!("ASHR_API_KEY", "=")
        );
        let digest = sha256_hex(evidence.as_bytes());
        let bundle = format!(
            r#"{{"schema_version":"ashr.a1.evidence_bundle.v1","evidence_sha256":"{digest}","evidence":{evidence}}}"#
        );

        let error = verify_bundle(&bundle).unwrap_err();

        assert!(error.contains("secret-like marker"));
    }
}
