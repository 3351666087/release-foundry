use std::env;
use std::fs;
use std::path::Path;

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
    let report = verify_input(&input)?;

    match command.as_str() {
        "verify" => {
            println!(
                "{{\"status\":\"ok\",\"bytes\":{},\"runtime_markers\":{},\"queued_or_running\":{}}}",
                input.len(),
                report.runtime_markers,
                report.queued_or_running
            );
            Ok(())
        }
        "replay-plan" => {
            println!(
                "{{\"schema_version\":\"ashr.runtime.replay_plan.v1\",\"source_bytes\":{},\"candidate_statuses\":[\"queued\",\"running\"],\"candidate_count\":{},\"action\":\"replay-queued\"}}",
                input.len(),
                report.queued_or_running
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
    fs::read_to_string(path)
        .map_err(|error| format!("failed to read {} as UTF-8 text: {error}", path.display()))
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
    "usage: ashr-runtime-verify <verify|replay-plan> <runtime-json-path>".to_string()
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
}
