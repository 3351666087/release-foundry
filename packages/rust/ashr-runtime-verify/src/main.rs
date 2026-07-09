use std::env;
use std::fs;
use std::path::Path;

use serde_json::Value;
use sha2::{Digest, Sha256};

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
    if args.next().is_some() {
        return Err(usage());
    }

    let input = read_bounded(Path::new(&path))?;
    match command.as_str() {
        "verify" => {
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
            let report = verify_input(&input)?;
            println!(
                "{{\"schema_version\":\"ashr.runtime.replay_plan.v1\",\"source_bytes\":{},\"candidate_statuses\":[\"queued\",\"running\"],\"candidate_count\":{},\"action\":\"replay-queued\"}}",
                input.len(),
                report.queued_or_running
            );
            Ok(())
        }
        "verify-bundle" => {
            let report = verify_bundle(&input)?;
            println!(
                "{{\"status\":\"ok\",\"schema_version\":\"{}\",\"evidence_sha256\":\"{}\",\"evidence_items\":{}}}",
                json_escape(&report.schema_version),
                report.evidence_sha256,
                report.evidence_items
            );
            Ok(())
        }
        _ => Err(usage()),
    }
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

    let canonical_evidence = serde_json::to_vec(evidence)
        .map_err(|error| format!("failed to canonicalize evidence JSON: {error}"))?;
    let actual_sha256 = hex_sha256(&canonical_evidence);
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

fn hex_sha256(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut output = String::with_capacity(digest.len() * 2);
    for byte in digest {
        output.push_str(&format!("{byte:02x}"));
    }
    output
}

fn is_lower_hex_sha256(candidate: &str) -> bool {
    candidate.len() == 64
        && candidate
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
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
            ']' => {
                if stack.pop() != Some('[') {
                    return false;
                }
            }
            _ => {}
        }
    }

    !in_string && stack.is_empty()
}

fn usage() -> String {
    "usage: ashr-runtime-verify <verify|replay-plan|verify-bundle> <runtime-json-path>".to_string()
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
    fn verifies_tamper_proof_evidence_bundle() {
        let evidence =
            r#"[{"artifact":"docs/a1/evidence/commands.md","sha256":"abc123","status":"passed"}]"#;
        let digest = hex_sha256(evidence.as_bytes());
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
        let digest = hex_sha256(original.as_bytes());
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
        let digest = hex_sha256(evidence.as_bytes());
        let bundle = format!(
            r#"{{"schema_version":"ashr.a1.evidence_bundle.v1","evidence_sha256":"{digest}","evidence":{evidence}}}"#
        );

        let error = verify_bundle(&bundle).unwrap_err();

        assert!(error.contains("secret-like marker"));
    }
}
