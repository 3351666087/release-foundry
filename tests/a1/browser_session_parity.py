from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from releasefoundry.browser_session import (  # noqa: E402
    BROWSER_SESSION_COOKIE_NAMES,
    BROWSER_SESSION_ERROR_CODES,
    BROWSER_SESSION_MODALITIES,
    browser_session_capability_manifest,
    browser_session_openapi_document,
)


PARITY_SCHEMA_VERSION = "releasefoundry.browser_session.parity.v1"
FIXTURE_DIR = ROOT / "tests" / "a1" / "fixtures"
PARITY_PATH = FIXTURE_DIR / "browser_session_sdk_parity.json"
OPENAPI_PATH = FIXTURE_DIR / "browser_session_openapi_3_1.json"
TS_GENERATED_PATH = (
    ROOT
    / "packages"
    / "ts"
    / "releasefoundry"
    / "src"
    / "browser-session-openapi.generated.ts"
)
GO_SERVER_PATH = ROOT / "packages" / "go" / "releasefoundry" / "server.go"
GO_IDENTITY_HTTP_PATH = (
    ROOT / "packages" / "go" / "releasefoundry" / "identity_verification_http.go"
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def pretty_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _function(source: str, name: str) -> str:
    marker = f"func {name}("
    start = source.find(marker)
    if start < 0:
        marker = f"func (server *HTTPServer) {name}("
        start = source.find(marker)
    if start < 0:
        raise RuntimeError(f"Go function {name} is missing")
    next_function = source.find("\nfunc ", start + len(marker))
    return source[start:] if next_function < 0 else source[start:next_function]


def _go_contract() -> dict[str, Any]:
    server = GO_SERVER_PATH.read_text(encoding="utf-8")
    identity = GO_IDENTITY_HTTP_PATH.read_text(encoding="utf-8")
    handler = _function(identity, "handleIdentitySessionRefresh")
    login_handler = _function(identity, "handleIdentityVerification")
    public_login = _function(identity, "publicIdentityVerificationResult")
    routes = {
        "complete_login": (
            'parts[1] == "identity-verification"' in server
            and 'case "verify":' in login_handler
            and "CompleteAndIssueSession" in login_handler
            and "WriteIdentitySessionReceipt" in login_handler
        ),
        "bootstrap": "/browser-sessions/bootstrap" in server,
        "refresh": (
            '"/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh"'
            in server
            and "handleIdentitySessionRefresh" in server
        ),
        "logout": "/browser-sessions/logout" in server,
        "revoke_all": "/browser-sessions/revoke-all" in server,
    }
    cookie_names = []
    for constant in ("IdentitySessionCookieName", "IdentityRefreshCookieName"):
        match = re.search(rf"{constant}\s*=\s*\"([^\"]+)\"", identity)
        if match is None:
            raise RuntimeError(f"Go cookie constant {constant} is missing")
        cookie_names.append(match.group(1))
    quoted_codes = set(re.findall(r'"([a-z][a-z0-9_]{2,127})"', identity))
    error_codes = sorted(quoted_codes.intersection(BROWSER_SESSION_ERROR_CODES))
    refresh_fields = sorted(
        set(re.findall(r'"([a-z][a-z0-9_]*)"\s*:', handler)).intersection(
            {"schema_version", "status"}
        )
    )
    login_fields = sorted(
        set(re.findall(r'"([a-z][a-z0-9_]*)"\s*:', public_login))
    )
    return {
        "source_paths": [
            GO_SERVER_PATH.relative_to(ROOT).as_posix(),
            GO_IDENTITY_HTTP_PATH.relative_to(ROOT).as_posix(),
        ],
        "executable_operations": [name for name, supported in routes.items() if supported],
        "unsupported_operations": [name for name, supported in routes.items() if not supported],
        "operation_support": routes,
        "cookie_names": cookie_names,
        "refresh_response_fields": refresh_fields,
        "login_response_fields": login_fields,
        "stable_error_codes": error_codes,
        "security_invariants": {
            "https_required": "ValidateIdentitySessionRequest" in handler,
            "same_origin_required": "validateIdentitySessionRefreshBrowserRequest" in handler,
            "idempotency_header_required": "identitySessionRefreshIdempotencyKey" in handler,
            "refresh_reuse_clears_cookies": (
                "ErrIdentitySessionRefreshReused" in handler
                and "clearIdentitySessionCookies" in handler
            ),
            "cookie_values_absent_from_public_response": (
                "accessBearer" not in handler and "refreshBearer" not in handler
            ),
        },
    }


def _openapi_surface(document: Mapping[str, Any]) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    for path, path_item in sorted(document["paths"].items()):
        for method, operation in sorted(path_item.items()):
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": operation["operationId"],
                    "response_statuses": sorted(operation["responses"]),
                    "parameter_refs": sorted(
                        parameter.get("$ref", parameter.get("name", ""))
                        for parameter in operation.get("parameters", [])
                    ),
                }
            )
    schemas = document["components"]["schemas"]
    schema_fields = {
        name: sorted(schema.get("properties", {}))
        for name, schema in sorted(schemas.items())
    }
    return {
        "operations": operations,
        "schema_fields": schema_fields,
        "security_schemes": sorted(document["components"]["securitySchemes"]),
        "header_components": sorted(document["components"]["headers"]),
    }


def build_outputs() -> tuple[dict[str, Any], dict[str, Any], str]:
    capability = browser_session_capability_manifest()
    openapi = browser_session_openapi_document()
    openapi_canonical = canonical_json(openapi)
    openapi_sha256 = hashlib.sha256(openapi_canonical.encode("utf-8")).hexdigest()
    go_contract = _go_contract()
    expected_go = {
        item["operation"]: item["go_executable"] for item in capability["operations"]
    }
    if go_contract["operation_support"] != expected_go:
        raise RuntimeError(
            "Python capability declarations drifted from executable Go route detection"
        )
    if go_contract["cookie_names"] != list(BROWSER_SESSION_COOKIE_NAMES):
        raise RuntimeError("Python and Go cookie names drifted")
    parity = {
        "schema_version": PARITY_SCHEMA_VERSION,
        "public_safe": True,
        "contains_credential_values": False,
        "source_paths": [
            "packages/sdk/releasefoundry/browser_session.py",
            "packages/ts/releasefoundry/src/browser-session.ts",
            "packages/go/releasefoundry/server.go",
            "packages/go/releasefoundry/identity_verification_http.go",
        ],
        "python_typescript_contract": capability,
        "openapi": {
            "path": OPENAPI_PATH.relative_to(ROOT).as_posix(),
            "sha256": openapi_sha256,
            "version": openapi["openapi"],
            "schema_version": openapi["x-releasefoundry-contract-schema-version"],
            "surface": _openapi_surface(openapi),
        },
        "go": go_contract,
        "modalities": list(BROWSER_SESSION_MODALITIES),
        "modality_policy": "text_image_audio_file_video_equal",
        "gates": {
            "python_typescript_manifest_exact": True,
            "python_typescript_openapi_exact": True,
            "go_route_support_is_detected_not_claimed": True,
            "go_response_fields_are_generated": True,
            "cookie_values_are_never_serialized": True,
        },
    }
    generated_ts = (
        "// Generated by tests/a1/browser_session_parity.py. Do not edit manually.\n"
        "export const BROWSER_SESSION_CAPABILITY_MANIFEST = "
        + pretty_json(capability).rstrip()
        + " as const;\n\n"
        "export const BROWSER_SESSION_OPENAPI_DOCUMENT = "
        + pretty_json(openapi).rstrip()
        + " as const;\n"
    )
    return parity, openapi, generated_ts


def write_outputs() -> None:
    parity, openapi, generated_ts = build_outputs()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    PARITY_PATH.write_text(pretty_json(parity), encoding="utf-8", newline="\n")
    OPENAPI_PATH.write_text(pretty_json(openapi), encoding="utf-8", newline="\n")
    TS_GENERATED_PATH.write_text(generated_ts, encoding="utf-8", newline="\n")


def check_outputs() -> list[str]:
    parity, openapi, generated_ts = build_outputs()
    expected = {
        PARITY_PATH: pretty_json(parity),
        OPENAPI_PATH: pretty_json(openapi),
        TS_GENERATED_PATH: generated_ts,
    }
    stale: list[str] = []
    for path, content in expected.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            stale.append(path.relative_to(ROOT).as_posix())
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        write_outputs()
        print("browser-session parity artifacts refreshed")
        return 0
    stale = check_outputs()
    if stale:
        print("browser-session parity artifacts are stale:", file=sys.stderr)
        for path in stale:
            print(f"- {path}", file=sys.stderr)
        return 1
    print("browser-session parity artifacts are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
