from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "tests" / "a1" / "docs" / "a1" / "ts_python_gap_matrix.json"
MEDIA_MODALITIES = ["text", "image", "audio", "file", "video"]
PUBLIC_INPUT_SOURCES = [
    "packages/sdk/ashr_clone public module source",
    "packages/ts/ashr-clone public package metadata and src source",
    "tests/a1 generated public parity generator",
]
REQUIRED_HOSTED_ROUTE_LITERALS = [
    "/v1/bootstrap",
    "/v1/projects/{project_id}/audit-log",
    "/v1/projects/{project_id}/audit-chain/verify",
    "/v1/projects/{project_id}/runs/{run_id}/release-evidence",
    "/v1/projects/{project_id}/runs/{run_id}/release-evidence/verify",
]
PYTHON_ROUTE_EXAMPLES = {
    "bootstrap_project": {"project_id": "project_contract", "run_id": "run_contract", "key_id": "key_contract", "job_id": "job_contract"},
    "create_api_key": {"project_id": "project_contract"},
    "list_api_keys": {"project_id": "project_contract"},
    "verify_api_key_secret": {"project_id": "project_contract", "key_id": "key_contract"},
    "configure_api_key_rate_limit": {"project_id": "project_contract", "key_id": "key_contract"},
    "api_key_rate_limit_snapshot": {"project_id": "project_contract"},
    "revoke_api_key": {"project_id": "project_contract", "key_id": "key_contract"},
    "sdk_submit": {"project_id": "project_contract"},
    "upload_run": {"project_id": "project_contract", "run_id": "run_contract"},
    "ingest_trace": {"project_id": "project_contract", "run_id": "run_contract"},
    "lifecycle_snapshot": {"project_id": "project_contract", "run_id": "run_contract"},
    "quota_snapshot": {"project_id": "project_contract"},
    "usage_snapshot": {"project_id": "project_contract"},
    "audit_log": {"project_id": "project_contract"},
    "create_artifact_manifest": {"project_id": "project_contract", "run_id": "run_contract"},
    "list_artifact_manifests": {"project_id": "project_contract", "run_id": "run_contract"},
    "enqueue_worker_job": {"project_id": "project_contract"},
    "lease_worker_job": {"project_id": "project_contract"},
    "list_worker_jobs": {"project_id": "project_contract"},
    "heartbeat_worker_job": {"project_id": "project_contract", "job_id": "job_contract"},
    "complete_worker_job": {"project_id": "project_contract", "job_id": "job_contract"},
    "fail_worker_job": {"project_id": "project_contract", "job_id": "job_contract"},
    "release_evidence": {"project_id": "project_contract", "run_id": "run_contract"},
    "release_evidence_verify": {"project_id": "project_contract", "run_id": "run_contract"},
    "verify_audit_chain": {"project_id": "project_contract"},
}
UNIFIED_IDENTITY_ROUTE_OPERATIONS = [
    ("account_get", "GET", "identity_account_route", ("account_contract",)),
    ("credential_list", "GET", "identity_credentials_route", ("account_contract",)),
    ("membership_list", "GET", "identity_memberships_route", ("account_contract",)),
    ("credential_link", "POST", "identity_link_route", ("account_contract", "github")),
    (
        "credential_unlink",
        "POST",
        "identity_unlink_route",
        ("account_contract", "credential_contract"),
    ),
    ("account_merge", "POST", "identity_merge_route", ("account_contract",)),
    ("recovery_start", "POST", "identity_recovery_start_route", ("account_contract",)),
    (
        "recovery_complete",
        "POST",
        "identity_recovery_complete_route",
        ("account_contract", "recovery_contract"),
    ),
    (
        "verification_challenge_create",
        "POST",
        "identity_verification_challenges_route",
        (),
    ),
    (
        "verification_challenge_get",
        "GET",
        "identity_verification_challenge_route",
        ("challenge_contract",),
    ),
    (
        "verification_challenge_resend",
        "POST",
        "identity_verification_resend_route",
        ("challenge_contract",),
    ),
    (
        "verification_challenge_verify",
        "POST",
        "identity_verification_verify_route",
        ("challenge_contract",),
    ),
]


def repo_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sorted_unique(values: list[str] | set[str]) -> list[str]:
    return sorted(set(values))


def python_all_exports(path: Path) -> list[str]:
    module = ast.parse(read_text(path), filename=repo_path(path))
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                value = ast.literal_eval(node.value)
                return sorted(str(item) for item in value)
    raise AssertionError(f"missing __all__ in {repo_path(path)}")


def python_set_literal(path: Path, name: str) -> list[str]:
    module = ast.parse(read_text(path), filename=repo_path(path))
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                value = ast.literal_eval(node.value)
                values = {str(item) for item in value}
                if values == set(MEDIA_MODALITIES):
                    return list(MEDIA_MODALITIES)
                return sorted(values)
    raise AssertionError(f"missing {name} in {repo_path(path)}")


def python_scalar_literal(path: Path, name: str) -> Any:
    module = ast.parse(read_text(path), filename=repo_path(path))
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"missing {name} in {repo_path(path)}")


def python_subparser_commands(path: Path) -> list[str]:
    text = read_text(path)
    return sorted_unique(re.findall(r"\.add_parser\(\s*[\"']([^\"']+)[\"']", text))


def python_cli_flags(path: Path) -> list[str]:
    text = read_text(path)
    return sorted_unique(re.findall(r"\.add_argument\(\s*[\"'](--[a-zA-Z0-9][a-zA-Z0-9_-]*)[\"']", text))


def ts_barrel_modules(index_path: Path) -> list[str]:
    text = read_text(index_path)
    return sorted_unique(re.findall(r"export \* from \[?['\"]\./([^'\"]+)\.js['\"]", text))


def ts_exported_symbols(src_dir: Path, modules: list[str]) -> dict[str, list[str]]:
    symbols: dict[str, list[str]] = {}
    export_decl = re.compile(r"^export\s+(?:declare\s+)?(?:async\s+)?(?:abstract\s+)?(?:class|function|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)", re.MULTILINE)
    export_list = re.compile(r"^export\s*\{([^}]+)\}", re.MULTILINE)
    for module in modules + ["index"]:
        path = src_dir / f"{module}.ts"
        if not path.exists():
            continue
        text = read_text(path)
        found = set(export_decl.findall(text))
        for block in export_list.findall(text):
            for item in block.split(","):
                name = item.strip().split(" as ")[-1].strip()
                if name:
                    found.add(name)
        symbols[module] = sorted(found)
    return dict(sorted(symbols.items()))


def package_bins(package_json_path: Path) -> list[str]:
    payload = json.loads(read_text(package_json_path))
    return sorted(payload.get("bin", {}).keys())


def ts_command_surfaces(src_dir: Path) -> dict[str, list[str]]:
    surfaces: dict[str, list[str]] = {}
    cloud_text = read_text(src_dir / "cloud-cli.ts")
    surfaces["cloud-cli"] = sorted_unique(re.findall(r"command === [\"']([^\"']+)[\"']", cloud_text))

    dataset_text = read_text(src_dir / "dataset-adapter-cli.ts")
    surfaces["dataset-adapter-cli"] = sorted_unique(re.findall(r"command === [\"']([^\"']+)[\"']", dataset_text))

    saas_text = read_text(src_dir / "saas.ts")
    match = re.search(r"SAAS_CLI_COMMANDS\s*=\s*new Set\(\[([^\]]+)\]\)", saas_text, re.S)
    if not match:
        raise AssertionError("missing SAAS_CLI_COMMANDS declaration")
    surfaces["saas"] = sorted_unique(re.findall(r"[\"']([^\"']+)[\"']", match.group(1)))

    surfaces["runner-cli"] = ["run-agent-batch"]
    return dict(sorted(surfaces.items()))


def ts_agent_input_modalities(index_path: Path) -> list[str]:
    text = read_text(index_path)
    match = re.search(r"type\s+AgentInputPartType\s*=\s*([^;]+);", text)
    if not match:
        raise AssertionError("missing AgentInputPartType")
    values = set(re.findall(r"[\"']([^\"']+)[\"']", match.group(1)))
    if values == set(MEDIA_MODALITIES):
        return list(MEDIA_MODALITIES)
    return sorted(values)


def ts_calibration_modalities(path: Path) -> list[str]:
    text = read_text(path)
    values = re.findall(r"[\"'](text|image|audio|file|video)[\"']", text)
    return [item for item in MEDIA_MODALITIES if item in values]


def ts_named_string(path: Path, name: str) -> str:
    text = read_text(path)
    match = re.search(
        rf"(?:export\s+)?const\s+{re.escape(name)}\s*=\s*[\"']([^\"']+)[\"']",
        text,
    )
    if not match:
        raise AssertionError(f"missing {name} in {repo_path(path)}")
    return match.group(1)


def ts_named_string_collection(path: Path, name: str) -> list[str]:
    text = read_text(path)
    match = re.search(
        rf"(?:export\s+)?const\s+{re.escape(name)}(?:\s*:[^=]+)?\s*=\s*"
        r"(?:(?:new\s+Set(?:<[^>]+>)?|Object\.freeze)\s*\()?\[([^\]]*)\]",
        text,
        re.S,
    )
    if not match:
        raise AssertionError(f"missing {name} in {repo_path(path)}")
    return sorted_unique(re.findall(r"[\"']([^\"']+)[\"']", match.group(1)))


def ts_manifest_section(path: Path, section: str) -> dict[str, bool]:
    text = read_text(path)
    function_match = re.search(
        r"export function unifiedIdentityContractManifest\(\).*?return\s*\{(.*?)\n\s*\};\n\}",
        text,
        re.S,
    )
    if not function_match:
        raise AssertionError(f"missing unifiedIdentityContractManifest in {repo_path(path)}")
    section_match = re.search(
        rf"{re.escape(section)}\s*:\s*\{{(.*?)\}}",
        function_match.group(1),
        re.S,
    )
    if not section_match:
        raise AssertionError(f"missing manifest section {section} in {repo_path(path)}")
    return {
        key: value == "true"
        for key, value in re.findall(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(true|false)",
            section_match.group(1),
        )
    }


def ts_unified_identity_routes(path: Path) -> list[dict[str, str]]:
    text = read_text(path)
    match = re.search(
        r"UNIFIED_IDENTITY_ROUTES[^=]*=\s*Object\.freeze\(\[(.*?)\]\);",
        text,
        re.S,
    )
    if not match:
        raise AssertionError(f"missing UNIFIED_IDENTITY_ROUTES in {repo_path(path)}")
    routes = [
        {"operation": operation, "method": method, "path": route}
        for operation, method, route in re.findall(
            r"\{\s*operation:\s*[\"']([^\"']+)[\"'],\s*"
            r"method:\s*[\"']([^\"']+)[\"'],\s*path:\s*[\"']([^\"']+)[\"']\s*\}",
            match.group(1),
        )
    ]
    if not routes:
        raise AssertionError(f"empty UNIFIED_IDENTITY_ROUTES in {repo_path(path)}")
    return routes


def python_unified_identity_contract(path: Path) -> dict[str, Any]:
    sdk_root = ROOT / "packages" / "sdk"
    if str(sdk_root) not in sys.path:
        sys.path.insert(0, str(sdk_root))
    from ashr_clone import unified_identity as identity

    manifest = identity.unified_identity_contract_manifest()
    replacements = {
        "account_contract": "{account_id}",
        "credential_contract": "{credential_id}",
        "recovery_contract": "{recovery_id}",
        "challenge_contract": "{challenge_id}",
        "github": "{provider}",
    }
    routes = []
    for operation, method, function_name, args in UNIFIED_IDENTITY_ROUTE_OPERATIONS:
        value = getattr(identity, function_name)(*args)
        for literal, placeholder in replacements.items():
            value = value.replace(literal, placeholder)
        if operation == "account_merge":
            value = value.replace("{account_id}", "{canonical_account_id}")
        routes.append({"operation": operation, "method": method, "path": value})
    verification = {
        **manifest["verification"],
        "providers": sorted(manifest["verification"]["providers"]),
        "purposes": sorted(manifest["verification"]["purposes"]),
        "challenge_statuses": sorted(manifest["verification"]["challenge_statuses"]),
        "receipt_statuses": sorted(manifest["verification"]["receipt_statuses"]),
        "public_surface": sorted(manifest["verification"]["public_surface"]),
    }
    return {
        "schema_version": python_scalar_literal(path, "UNIFIED_IDENTITY_SCHEMA_VERSION"),
        "providers": python_set_literal(path, "UNIFIED_IDENTITY_PROVIDERS"),
        "account_statuses": python_set_literal(path, "UNIFIED_IDENTITY_ACCOUNT_STATUSES"),
        "credential_statuses": python_set_literal(path, "UNIFIED_IDENTITY_CREDENTIAL_STATUSES"),
        "membership_roles": python_set_literal(path, "UNIFIED_IDENTITY_MEMBERSHIP_ROLES"),
        "membership_statuses": python_set_literal(path, "UNIFIED_IDENTITY_MEMBERSHIP_STATUSES"),
        "stable_error_codes": python_set_literal(path, "UNIFIED_IDENTITY_ERROR_CODES"),
        "verification_providers": python_set_literal(path, "IDENTITY_VERIFICATION_PROVIDERS"),
        "verification_purposes": python_set_literal(path, "IDENTITY_VERIFICATION_PURPOSES"),
        "verification_challenge_statuses": python_set_literal(
            path, "IDENTITY_VERIFICATION_CHALLENGE_STATUSES"
        ),
        "verification_receipt_statuses": python_set_literal(
            path, "IDENTITY_VERIFICATION_RECEIPT_STATUSES"
        ),
        "verification_audit_event_types": python_set_literal(
            path, "IDENTITY_VERIFICATION_AUDIT_EVENT_TYPES"
        ),
        "verification_audit_outcome_codes": python_set_literal(
            path, "IDENTITY_VERIFICATION_AUDIT_OUTCOME_CODES"
        ),
        "verification_public_surface": python_set_literal(
            path, "IDENTITY_VERIFICATION_PUBLIC_SURFACE"
        ),
        "verification": verification,
        "subject_model": manifest["subject_model"],
        "invariants": dict(sorted(manifest["invariants"].items())),
        "public_safety": dict(sorted(manifest["public_safety"].items())),
        "forbidden_public_keys": python_set_literal(path, "_FORBIDDEN_PUBLIC_KEYS"),
        "forbidden_key_suffixes": python_set_literal(path, "_FORBIDDEN_KEY_SUFFIXES"),
        "recovery_providers": python_set_literal(path, "_RECOVERY_PROVIDERS"),
        "routes": routes,
    }


def ts_unified_identity_contract(path: Path) -> dict[str, Any]:
    text = read_text(path)
    subject_match = re.search(
        r"subject_model\s*:\s*[\"']([^\"']+)[\"']",
        text,
    )
    if not subject_match:
        raise AssertionError(f"missing unified identity subject_model in {repo_path(path)}")
    return {
        "schema_version": ts_named_string(path, "UNIFIED_IDENTITY_SCHEMA_VERSION"),
        "providers": ts_named_string_collection(path, "UNIFIED_IDENTITY_PROVIDERS"),
        "account_statuses": ts_named_string_collection(path, "UNIFIED_IDENTITY_ACCOUNT_STATUSES"),
        "credential_statuses": ts_named_string_collection(
            path, "UNIFIED_IDENTITY_CREDENTIAL_STATUSES"
        ),
        "membership_roles": ts_named_string_collection(path, "UNIFIED_IDENTITY_MEMBERSHIP_ROLES"),
        "membership_statuses": ts_named_string_collection(
            path, "UNIFIED_IDENTITY_MEMBERSHIP_STATUSES"
        ),
        "stable_error_codes": ts_named_string_collection(path, "UNIFIED_IDENTITY_ERROR_CODES"),
        "verification_providers": ts_named_string_collection(
            path, "IDENTITY_VERIFICATION_PROVIDERS"
        ),
        "verification_purposes": ts_named_string_collection(
            path, "IDENTITY_VERIFICATION_PURPOSES"
        ),
        "verification_challenge_statuses": ts_named_string_collection(
            path, "IDENTITY_VERIFICATION_CHALLENGE_STATUSES"
        ),
        "verification_receipt_statuses": ts_named_string_collection(
            path, "IDENTITY_VERIFICATION_RECEIPT_STATUSES"
        ),
        "verification_audit_event_types": ts_named_string_collection(
            path, "IDENTITY_VERIFICATION_AUDIT_EVENT_TYPES"
        ),
        "verification_audit_outcome_codes": ts_named_string_collection(
            path, "IDENTITY_VERIFICATION_AUDIT_OUTCOME_CODES"
        ),
        "verification_public_surface": ts_named_string_collection(
            path, "IDENTITY_VERIFICATION_PUBLIC_SURFACE"
        ),
        "verification": {
            "providers": ts_named_string_collection(path, "IDENTITY_VERIFICATION_PROVIDERS"),
            "purposes": ts_named_string_collection(path, "IDENTITY_VERIFICATION_PURPOSES"),
            "challenge_statuses": ts_named_string_collection(
                path, "IDENTITY_VERIFICATION_CHALLENGE_STATUSES"
            ),
            "receipt_statuses": ts_named_string_collection(
                path, "IDENTITY_VERIFICATION_RECEIPT_STATUSES"
            ),
            "destination_input": "opaque_reference_only",
            "code_input": "opaque_reference_only",
            **ts_manifest_section(path, "verification"),
            "public_surface": ts_named_string_collection(
                path, "IDENTITY_VERIFICATION_PUBLIC_SURFACE"
            ),
        },
        "subject_model": subject_match.group(1),
        "invariants": dict(sorted(ts_manifest_section(path, "invariants").items())),
        "public_safety": dict(sorted(ts_manifest_section(path, "public_safety").items())),
        "forbidden_public_keys": ts_named_string_collection(path, "FORBIDDEN_PUBLIC_KEYS"),
        "forbidden_key_suffixes": ts_named_string_collection(path, "FORBIDDEN_KEY_SUFFIXES"),
        "recovery_providers": ts_named_string_collection(path, "RECOVERY_PROVIDERS"),
        "routes": ts_unified_identity_routes(path),
    }


def python_session_lifecycle_contract(path: Path) -> dict[str, Any]:
    sdk_root = ROOT / "packages" / "sdk"
    if str(sdk_root) not in sys.path:
        sys.path.insert(0, str(sdk_root))
    from ashr_clone.session_lifecycle import session_lifecycle_contract_manifest

    manifest = session_lifecycle_contract_manifest()
    manifest["statuses"] = sorted(manifest["statuses"])
    manifest["stable_error_codes"] = sorted(manifest["stable_error_codes"])
    manifest["invariants"] = dict(sorted(manifest["invariants"].items()))
    return manifest


def ts_session_lifecycle_routes(path: Path) -> list[dict[str, str]]:
    text = read_text(path)
    match = re.search(
        r"SESSION_LIFECYCLE_ROUTES[^=]*=\s*Object\.freeze\(\[(.*?)\]\);",
        text,
        re.S,
    )
    if not match:
        raise AssertionError(f"missing SESSION_LIFECYCLE_ROUTES in {repo_path(path)}")
    routes = [
        {"operation": operation, "method": method, "path": route}
        for operation, method, route in re.findall(
            r"\{\s*operation:\s*[\"']([^\"']+)[\"'],\s*"
            r"method:\s*[\"']([^\"']+)[\"'],\s*path:\s*[\"']([^\"']+)[\"']\s*\}",
            match.group(1),
        )
    ]
    if not routes:
        raise AssertionError(f"empty SESSION_LIFECYCLE_ROUTES in {repo_path(path)}")
    return routes


def ts_session_lifecycle_contract(path: Path) -> dict[str, Any]:
    text = read_text(path)
    function_match = re.search(
        r"export function sessionLifecycleContractManifest\(\).*?const manifest\s*=\s*\{(.*?)\n\s*\};",
        text,
        re.S,
    )
    if not function_match:
        raise AssertionError(f"missing sessionLifecycleContractManifest in {repo_path(path)}")
    body = function_match.group(1)
    invariant_match = re.search(r"invariants\s*:\s*\{(.*?)\}", body, re.S)
    if not invariant_match:
        raise AssertionError(f"missing session lifecycle invariants in {repo_path(path)}")
    invariants = {
        key: value == "true"
        for key, value in re.findall(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(true|false)",
            invariant_match.group(1),
        )
    }
    result: dict[str, Any] = {
        "schema_version": ts_named_string(path, "SESSION_LIFECYCLE_SCHEMA_VERSION"),
        "statuses": ts_named_string_collection(path, "SESSION_LIFECYCLE_STATUSES"),
        "stable_error_codes": ts_named_string_collection(path, "SESSION_LIFECYCLE_ERROR_CODES"),
        "routes": ts_session_lifecycle_routes(path),
        "invariants": dict(sorted(invariants.items())),
    }
    for key in ("digest_only", "rotation", "reuse_detection", "revocation", "recent_auth", "recovery"):
        match = re.search(rf"\b{re.escape(key)}\s*:\s*(true|false)", body)
        if not match:
            raise AssertionError(f"missing session lifecycle flag {key} in {repo_path(path)}")
        result[key] = match.group(1) == "true"
    return result


def python_identity_delivery_protocol_contract(path: Path) -> dict[str, Any]:
    sdk_root = ROOT / "packages" / "sdk"
    if str(sdk_root) not in sys.path:
        sys.path.insert(0, str(sdk_root))
    from ashr_clone.delivery_protocol import identity_delivery_protocol_contract_manifest

    manifest = identity_delivery_protocol_contract_manifest()
    for key in (
        "dto_kinds",
        "statuses",
        "acceptance_statuses",
        "stable_error_codes",
        "failure_codes",
    ):
        manifest[key] = sorted(manifest[key])
    manifest["invariants"] = dict(sorted(manifest["invariants"].items()))
    return manifest


def ts_identity_delivery_protocol_routes(path: Path) -> list[dict[str, str]]:
    text = read_text(path)
    match = re.search(
        r"IDENTITY_DELIVERY_ADMIN_ROUTES[^=]*=\s*Object\.freeze\(\[(.*?)\]\);",
        text,
        re.S,
    )
    if not match:
        raise AssertionError(f"missing IDENTITY_DELIVERY_ADMIN_ROUTES in {repo_path(path)}")
    routes = [
        {"operation": operation, "method": method, "path": route}
        for operation, method, route in re.findall(
            r"\{\s*operation:\s*[\"']([^\"']+)[\"'],\s*"
            r"method:\s*[\"']([^\"']+)[\"'],\s*path:\s*[\"']([^\"']+)[\"']\s*\}",
            match.group(1),
        )
    ]
    if not routes:
        raise AssertionError(f"empty IDENTITY_DELIVERY_ADMIN_ROUTES in {repo_path(path)}")
    return routes


def ts_identity_delivery_protocol_contract(path: Path) -> dict[str, Any]:
    text = read_text(path)
    function_match = re.search(
        r"export function identityDeliveryProtocolContractManifest\(\).*?"
        r"const manifest\s*=\s*\{(.*?)\n\s*\};",
        text,
        re.S,
    )
    if not function_match:
        raise AssertionError(
            f"missing identityDeliveryProtocolContractManifest in {repo_path(path)}"
        )
    invariant_match = re.search(
        r"invariants\s*:\s*\{(.*?)\}", function_match.group(1), re.S
    )
    if not invariant_match:
        raise AssertionError(f"missing delivery protocol invariants in {repo_path(path)}")
    invariants = {
        key: value == "true"
        for key, value in re.findall(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(true|false)",
            invariant_match.group(1),
        )
    }
    return {
        "schema_version": ts_named_string(
            path, "IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION"
        ),
        "dto_kinds": ts_named_string_collection(path, "IDENTITY_DELIVERY_DTO_KINDS"),
        "statuses": ts_named_string_collection(path, "IDENTITY_DELIVERY_STATUSES"),
        "acceptance_statuses": ts_named_string_collection(
            path, "IDENTITY_DELIVERY_ACCEPTANCE_STATUSES"
        ),
        "stable_error_codes": ts_named_string_collection(
            path, "IDENTITY_DELIVERY_ERROR_CODES"
        ),
        "failure_codes": ts_named_string_collection(
            path, "IDENTITY_DELIVERY_FAILURE_CODES"
        ),
        "routes": ts_identity_delivery_protocol_routes(path),
        "invariants": dict(sorted(invariants.items())),
    }


def route_literals(path: Path) -> list[str]:
    text = read_text(path)
    literals = re.findall(r"[\"'`](/v1/[^\"'`\\]*(?:\\.[^\"'`]*)?)[\"'`]", text)
    normalized: list[str] = []
    for literal in literals:
        value = re.sub(r"\$\{[^}]+\}", "{value}", literal)
        value = value.replace("\\", "")
        normalized.append(value)
    return sorted_unique(normalized)


def python_hosted_route_literals() -> list[str]:
    sdk_root = ROOT / "packages" / "sdk"
    if str(sdk_root) not in sys.path:
        sys.path.insert(0, str(sdk_root))
    from ashr_clone.saas import _operation_route

    routes: list[str] = []
    for operation, payload in PYTHON_ROUTE_EXAMPLES.items():
        _method, path = _operation_route(operation, payload)
        normalized = path.replace("project_contract", "{project_id}").replace("run_contract", "{run_id}").replace("key_contract", "{key_id}").replace("job_contract", "{job_id}")
        routes.append(normalized)
    return sorted_unique(routes)


def canonical_hosted_routes(routes: list[str]) -> set[str]:
    canonical: set[str] = set()
    for route in routes:
        value_index = 0

        def replace_value(_: re.Match[str]) -> str:
            nonlocal value_index
            replacements = ["{project_id}", "{run_id}", "{key_id}", "{job_id}"]
            replacement = replacements[value_index] if value_index < len(replacements) else "{value}"
            value_index += 1
            return replacement

        canonical.add(re.sub(r"\{value\}", replace_value, route))
    return canonical


def status_from_sets(left: set[str], right: set[str]) -> str:
    if left == right:
        return "parity"
    if left and right and left - right and right - left:
        return "partial"
    if left - right:
        return "python_leads"
    return "typescript_leads"


def generate_matrix() -> dict[str, Any]:
    py_pkg = ROOT / "packages" / "sdk" / "ashr_clone"
    ts_pkg = ROOT / "packages" / "ts" / "ashr-clone"
    ts_src = ts_pkg / "src"

    py_exports = python_all_exports(py_pkg / "__init__.py")
    ts_modules = ts_barrel_modules(ts_src / "index.ts")
    ts_symbols_by_module = ts_exported_symbols(ts_src, ts_modules)
    ts_export_names = sorted_unique({name for names in ts_symbols_by_module.values() for name in names})

    py_saas_commands = python_subparser_commands(py_pkg / "saas_cli.py")
    py_calibrate_flags = python_cli_flags(py_pkg / "calibrate.py")
    ts_commands = ts_command_surfaces(ts_src)

    py_routes = python_hosted_route_literals()
    ts_routes = route_literals(ts_src / "saas.ts")

    py_media = {
        "agent_input_part_types": python_set_literal(py_pkg / "adapter.py", "AGENT_INPUT_PART_TYPES"),
        "calibration_modalities": [item for item in MEDIA_MODALITIES if item in read_text(py_pkg / "calibrate.py")],
    }
    required_ts_calibration_exports = ["CalibrationArgs", "CalibrationManifest", "main", "parseArgs", "runCalibration"]
    ts_media = {
        "agent_input_part_types": ts_agent_input_modalities(ts_src / "index.ts"),
        "calibration_modalities": ts_calibration_modalities(ts_src / "calibrate.ts"),
        "safe_media_envelope_exported": "buildSafeMediaEnvelope" in ts_export_names and "SaaSMediaEnvelope" in ts_export_names,
    }

    python_export_set = set(py_exports)
    ts_export_set = set(ts_export_names)
    py_command_set = set(py_saas_commands)
    ts_command_set = {command for commands in ts_commands.values() for command in commands}
    py_route_set = set(py_routes)
    ts_route_set = set(ts_routes)
    py_hosted_route_set = canonical_hosted_routes(py_routes)
    ts_hosted_route_set = canonical_hosted_routes(ts_routes)
    required_route_set = set(REQUIRED_HOSTED_ROUTE_LITERALS)
    ts_calibration_exports = set(ts_symbols_by_module.get("calibrate", []))
    ts_calibration_contract = {
        "barrel_module_exported": "calibrate" in ts_modules,
        "required_exports": required_ts_calibration_exports,
        "exported_symbols": sorted(ts_calibration_exports),
        "missing_required_exports": sorted(set(required_ts_calibration_exports) - ts_calibration_exports),
        "sdk_import_surface": "public" if "calibrate" in ts_modules else "cli_only",
    }
    py_identity = python_unified_identity_contract(py_pkg / "unified_identity.py")
    ts_identity = ts_unified_identity_contract(ts_src / "unified-identity.ts")
    py_session = python_session_lifecycle_contract(py_pkg / "session_lifecycle.py")
    ts_session = ts_session_lifecycle_contract(ts_src / "session-lifecycle.ts")
    py_delivery = python_identity_delivery_protocol_contract(py_pkg / "delivery_protocol.py")
    ts_delivery = ts_identity_delivery_protocol_contract(ts_src / "delivery-protocol.ts")
    identity_contract_requirements = {
        "seven_credential_kinds": len(py_identity["providers"]) == 7
        and set(py_identity["providers"])
        == {"github", "google", "wechat", "qq", "alipay", "phone", "email"},
        "stable_account_principal": py_identity["subject_model"]
        == "one_account_many_credentials",
        "memberships_independent": py_identity["invariants"].get(
            "memberships_attach_to_canonical_account"
        )
        is True,
        "no_email_automerge": py_identity["invariants"].get(
            "email_match_does_not_merge_accounts"
        )
        is True,
        "public_safe": all(
            value is False
            for key, value in py_identity["public_safety"].items()
            if key != "provider_subject_presence_marker_only"
        )
        and py_identity["public_safety"].get("provider_subject_presence_marker_only") is True,
    }
    identity_contract_parity = py_identity == ts_identity and all(
        identity_contract_requirements.values()
    )
    py_media_set = set(py_media["agent_input_part_types"])
    ts_media_set = set(ts_media["agent_input_part_types"])

    return {
        "schema_version": "ashr.clone.a1_ts_python_gap_matrix.v2",
        "generated_by": "tests/a1/ts_python_parity_matrix.py",
        "generated_at": "deterministic-public-source-scan",
        "public_safe": True,
        "secret_policy": {
            "private_evidence_read": False,
            "tokens_included": False,
            "raw_private_payloads_included": False,
            "input_sources": PUBLIC_INPUT_SOURCES,
        },
        "source_paths": {
            "python_package": repo_path(py_pkg),
            "typescript_package": repo_path(ts_pkg),
            "generator": "tests/a1/ts_python_parity_matrix.py",
        },
        "generated_contract": {
            "symbols": {
                "python_top_level_exports": py_exports,
                "typescript_barrel_modules": ts_modules,
                "typescript_exported_symbols_by_module": ts_symbols_by_module,
                "typescript_effective_export_names": ts_export_names,
                "shared_export_names": sorted(python_export_set & ts_export_set),
                "python_only_export_names": sorted(python_export_set - ts_export_set),
                "typescript_only_export_names": sorted(ts_export_set - python_export_set),
            },
            "cli": {
                "python_commands": {
                    "ashr_clone.saas_cli": py_saas_commands,
                    "ashr_clone.calibrate_flags": py_calibrate_flags,
                },
                "typescript_commands": {
                    "package_bins": package_bins(ts_pkg / "package.json"),
                    **ts_commands,
                },
                "shared_saas_command_names": sorted(py_command_set & ts_command_set),
                "python_only_saas_command_names": sorted(py_command_set - ts_command_set),
                "typescript_only_saas_command_names": sorted(ts_command_set - py_command_set),
            },
            "routes": {
                "required_hosted_route_literals": REQUIRED_HOSTED_ROUTE_LITERALS,
                "python_saas_route_literals": py_routes,
                "typescript_saas_route_literals": ts_routes,
                "shared_route_literals": sorted(py_route_set & ts_route_set),
                "python_only_route_literals": sorted(py_route_set - ts_route_set),
                "typescript_only_route_literals": sorted(ts_route_set - py_route_set),
                "missing_required_python_hosted_routes": sorted(required_route_set - py_hosted_route_set),
                "missing_required_typescript_hosted_routes": sorted(required_route_set - ts_hosted_route_set),
            },
            "media": {
                "required_modalities": MEDIA_MODALITIES,
                "python": py_media,
                "typescript": ts_media,
                "shared_agent_input_part_types": sorted(py_media_set & ts_media_set),
                "python_only_agent_input_part_types": sorted(py_media_set - ts_media_set),
                "typescript_only_agent_input_part_types": sorted(ts_media_set - py_media_set),
            },
            "calibration": {
                "python_module": "packages/sdk/ashr_clone/calibrate.py",
                "typescript_module": "packages/ts/ashr-clone/src/calibrate.ts",
                "typescript": ts_calibration_contract,
            },
            "unified_identity": {
                "requirements": identity_contract_requirements,
                "python": py_identity,
                "typescript": ts_identity,
                "matching_fields": sorted(
                    key for key in py_identity if py_identity[key] == ts_identity.get(key)
                ),
                "differing_fields": sorted(
                    key for key in py_identity if py_identity[key] != ts_identity.get(key)
                ),
            },
            "session_lifecycle": {
                "python": py_session,
                "typescript": ts_session,
                "matching_fields": sorted(
                    key for key in py_session if py_session[key] == ts_session.get(key)
                ),
                "differing_fields": sorted(
                    key for key in py_session if py_session[key] != ts_session.get(key)
                ),
            },
            "identity_delivery_protocol": {
                "python": py_delivery,
                "typescript": ts_delivery,
                "matching_fields": sorted(
                    key for key in py_delivery if py_delivery[key] == ts_delivery.get(key)
                ),
                "differing_fields": sorted(
                    key for key in py_delivery if py_delivery[key] != ts_delivery.get(key)
                ),
            },
        },
        "gap_matrix": [
            {
                "area": "exported Python functions/classes/types vs TS exports",
                "status": status_from_sets(python_export_set, ts_export_set),
                "python_leads": sorted(python_export_set - ts_export_set),
                "typescript_leads": sorted(ts_export_set - python_export_set),
                "shared": sorted(python_export_set & ts_export_set),
                "evidence": [
                    "packages/sdk/ashr_clone/__init__.py",
                    "packages/ts/ashr-clone/src/index.ts",
                    *[f"packages/ts/ashr-clone/src/{module}.ts" for module in ts_modules],
                ],
            },
            {
                "area": "CLI commands",
                "status": status_from_sets(py_command_set, ts_command_set),
                "python_commands": {"ashr_clone.saas_cli": py_saas_commands, "ashr_clone.calibrate_flags": py_calibrate_flags},
                "typescript_commands": {"package_bins": package_bins(ts_pkg / "package.json"), **ts_commands},
                "gaps": [
                    f"Python-only SaaS CLI commands: {', '.join(sorted(py_command_set - ts_command_set)) or 'none'}",
                    f"TypeScript-only SaaS CLI commands: {', '.join(sorted(ts_command_set - py_command_set)) or 'none'}",
                ],
                "evidence": [
                    "packages/sdk/ashr_clone/saas_cli.py",
                    "packages/sdk/ashr_clone/calibrate.py",
                    "packages/ts/ashr-clone/package.json",
                    "packages/ts/ashr-clone/src/cloud-cli.ts",
                    "packages/ts/ashr-clone/src/dataset-adapter-cli.ts",
                    "packages/ts/ashr-clone/src/runner-cli.ts",
                    "packages/ts/ashr-clone/src/saas.ts",
                ],
            },
            {
                "area": "SaaS route literals",
                "status": status_from_sets(py_route_set, ts_route_set),
                "python_leads": sorted(py_route_set - ts_route_set),
                "typescript_leads": sorted(ts_route_set - py_route_set),
                "shared": sorted(py_route_set & ts_route_set),
                "required_hosted_route_literals": REQUIRED_HOSTED_ROUTE_LITERALS,
                "missing_required_python_hosted_routes": sorted(required_route_set - py_hosted_route_set),
                "missing_required_typescript_hosted_routes": sorted(required_route_set - ts_hosted_route_set),
                "evidence": ["packages/sdk/ashr_clone/saas.py", "packages/ts/ashr-clone/src/saas.ts"],
            },
            {
                "area": "media text/audio/file/image/video parity",
                "status": "parity" if py_media_set == ts_media_set == set(MEDIA_MODALITIES) else "partial",
                "shared": sorted(py_media_set & ts_media_set),
                "python_leads": sorted(py_media_set - ts_media_set),
                "typescript_leads": sorted(ts_media_set - py_media_set),
                "evidence": [
                    "packages/sdk/ashr_clone/adapter.py",
                    "packages/sdk/ashr_clone/calibrate.py",
                    "packages/ts/ashr-clone/src/index.ts",
                    "packages/ts/ashr-clone/src/calibrate.ts",
                    "packages/ts/ashr-clone/src/saas.ts",
                ],
            },
            {
                "area": "official API calibration SDK import surface",
                "status": "parity" if ts_calibration_contract["barrel_module_exported"] and not ts_calibration_contract["missing_required_exports"] else "typescript_lags",
                "python_leads": [] if ts_calibration_contract["barrel_module_exported"] else ["calibrate module is importable from Python package path"],
                "typescript_leads": [],
                "shared": ["dry-run default", "small-batch guardrails", "quota gate", "text/image/audio/file/video modality plan"],
                "typescript_missing_exports": ts_calibration_contract["missing_required_exports"],
                "evidence": [
                    "packages/sdk/ashr_clone/calibrate.py",
                    "packages/ts/ashr-clone/src/index.ts",
                    "packages/ts/ashr-clone/src/calibrate.ts",
                    "packages/ts/ashr-clone/test/calibrate.test.mjs",
                    "packages/ts/ashr-clone/test/calibration-parity.test.mjs",
                ],
            },
            {
                "area": "Python/TypeScript unified identity contract",
                "status": "parity" if identity_contract_parity else "partial",
                "requirements": identity_contract_requirements,
                "matching_fields": sorted(
                    key for key in py_identity if py_identity[key] == ts_identity.get(key)
                ),
                "differing_fields": sorted(
                    key for key in py_identity if py_identity[key] != ts_identity.get(key)
                ),
                "evidence": [
                    "packages/sdk/ashr_clone/unified_identity.py",
                    "packages/ts/ashr-clone/src/unified-identity.ts",
                    "tests/a1/test_python_unified_identity.py",
                    "packages/ts/ashr-clone/test/unified-identity.test.mjs",
                ],
            },
            {
                "area": "Python/TypeScript session lifecycle contract",
                "status": "parity" if py_session == ts_session else "partial",
                "matching_fields": sorted(
                    key for key in py_session if py_session[key] == ts_session.get(key)
                ),
                "differing_fields": sorted(
                    key for key in py_session if py_session[key] != ts_session.get(key)
                ),
                "evidence": [
                    "packages/sdk/ashr_clone/session_lifecycle.py",
                    "packages/ts/ashr-clone/src/session-lifecycle.ts",
                    "tests/a1/test_python_session_lifecycle.py",
                    "packages/ts/ashr-clone/test/session-lifecycle.test.mjs",
                ],
            },
            {
                "area": "Python/TypeScript identity delivery protocol",
                "status": "parity" if py_delivery == ts_delivery else "partial",
                "matching_fields": sorted(
                    key for key in py_delivery if py_delivery[key] == ts_delivery.get(key)
                ),
                "differing_fields": sorted(
                    key for key in py_delivery if py_delivery[key] != ts_delivery.get(key)
                ),
                "evidence": [
                    "packages/sdk/ashr_clone/delivery_protocol.py",
                    "packages/ts/ashr-clone/src/delivery-protocol.ts",
                    "tests/a1/test_identity_delivery_protocol_sdk.py",
                    "packages/ts/ashr-clone/test/delivery-protocol.test.mjs",
                ],
            },
        ],
        "next_actions": [
            "When intentional TS/Python symbol, CLI, route, or media changes land, refresh with `python tests/a1/ts_python_parity_matrix.py --write`.",
            "Keep this artifact public-safe: add only source paths, symbol names, command names, route templates, and modality names.",
        ],
    }


def write_artifact() -> None:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(generate_matrix(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_artifact() -> None:
    expected = generate_matrix()
    actual = json.loads(ARTIFACT.read_text(encoding="utf-8-sig"))
    if actual != expected:
        raise SystemExit("ts_python_gap_matrix.json is stale; run `python tests/a1/ts_python_parity_matrix.py --write`")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--write"]:
        write_artifact()
        return 0
    if args in ([], ["--check"]):
        check_artifact()
        return 0
    raise SystemExit("usage: python tests/a1/ts_python_parity_matrix.py [--check|--write]")


if __name__ == "__main__":
    raise SystemExit(main())
