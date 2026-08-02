import json
import re
import tempfile
import unittest
from pathlib import Path

from services.judge.cross_lane_security import build_cross_lane_security_context


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/a2/results/a2_cross_lane_security_context.json"
SCHEMA = ROOT / "docs/a2/schemas/cross_lane_security_context.schema.json"

SECRET_PATTERNS = [
    re.compile("tp_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("releasefoundry_live_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("sk-" + r"[A-Za-z0-9]"),
    re.compile("Bearer" + r"\\s+"),
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs"),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class A2CrossLaneSecurityTests(unittest.TestCase):
    def test_default_fixture_matches_builder_and_consumes_main_a1_route_scope(self):
        actual = build_cross_lane_security_context()
        expected = load_json(FIXTURE)

        self.assertEqual(actual, expected)
        self.assertEqual(actual["schema_version"], "a2.cross_lane_security_context.v1")
        self.assertTrue(actual["a1_route_scope"]["available"])
        self.assertTrue(actual["a1_route_scope"]["ready_for_a2_security_context"])
        self.assertRegex(actual["a1_route_scope"]["source_sha256"], r"^[a-f0-9]{64}$")
        self.assertTrue(actual["a1_route_scope"]["public_safe_source_verified"])
        self.assertTrue(actual["a1_route_scope"]["source_policy_verified"])
        self.assertTrue(actual["a1_route_scope"]["declared_route_counts_match"])
        self.assertTrue(actual["a1_route_scope"]["tenancy_route_parity_verified"])
        self.assertEqual(
            actual["a1_route_scope"]["declared_route_counts"],
            {"go": 114, "python": 35, "typescript": 38},
        )
        self.assertEqual(
            actual["a1_route_scope"]["observed_route_counts"],
            actual["a1_route_scope"]["declared_route_counts"],
        )
        self.assertEqual(actual["a1_route_scope"]["route_count"], 125)
        self.assertEqual(actual["a1_route_scope"]["intentional_difference_count"], 124)
        self.assertTrue(actual["a2_policy_implications"]["should_add_route_scope_security_cases"])
        self.assertTrue(actual["a3_auth_rbac_boundary"]["available"])
        self.assertTrue(actual["a3_auth_rbac_boundary"]["ready_for_a2_security_context"])
        self.assertRegex(actual["a3_auth_rbac_boundary"]["source_sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(actual["a3_auth_rbac_boundary"]["openapi_source_sha256"], r"^[a-f0-9]{64}$")
        self.assertTrue(actual["a3_auth_rbac_boundary"]["auth_operation_parity_verified"])
        self.assertEqual(
            actual["a3_auth_rbac_boundary"]["documented_auth_operations"],
            actual["a3_auth_rbac_boundary"]["openapi_auth_operations"],
        )
        self.assertTrue(actual["a3_fail_closed_rbac"]["available"])
        self.assertTrue(actual["a3_fail_closed_rbac"]["ready_for_a2_security_context"])
        self.assertRegex(actual["a3_fail_closed_rbac"]["source_sha256"], r"^[a-f0-9]{64}$")
        self.assertTrue(actual["a3_event_outbox"]["available"])
        self.assertTrue(actual["a3_event_outbox"]["ready_for_a2_security_context"])
        self.assertRegex(actual["a3_event_outbox"]["source_sha256"], r"^[a-f0-9]{64}$")
        self.assertTrue(actual["a2_policy_implications"]["should_add_auth_rbac_abuse_cases"])
        self.assertTrue(actual["a2_policy_implications"]["should_add_fail_closed_write_abuse_cases"])
        self.assertTrue(actual["a2_policy_implications"]["should_add_event_outbox_integrity_cases"])
        followup_ids = {item["followup_id"] for item in actual["a2_security_followups"]}
        self.assertEqual(
            followup_ids,
            {
                "a2-route-scope-tenant-boundary",
                "a2-auth-rbac-denied-state-cases",
                "a2-a3-fail-closed-write-abuse-cases",
                "a2-a3-event-outbox-integrity-cases",
            },
        )

    def test_schema_and_fixture_are_public_safe(self):
        payload = load_json(FIXTURE)
        schema = load_json(SCHEMA)
        payload_text = FIXTURE.read_text(encoding="utf-8")

        self.assertEqual(schema["properties"]["schema_version"]["const"], payload["schema_version"])
        self.assertLessEqual(set(schema["required"]), set(payload))
        self.assertTrue(payload["metadata"]["public_safe"])
        self.assertFalse(payload["metadata"]["requires_network"])
        self.assertFalse(payload["metadata"]["requires_releasefoundry_api_key"])
        self.assertTrue(payload["metadata"]["does_not_read_private_evidence"])
        self.assertTrue(payload["metadata"]["raw_private_evidence_not_recorded"])
        self.assertTrue(payload["metadata"]["secrets_not_recorded"])

        for pattern in SECRET_PATTERNS:
            self.assertIsNone(pattern.search(payload_text), pattern.pattern)

    def test_ready_a1_a3_public_contracts_unlock_security_implications(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            a1_path = tmp / "route_scope.json"
            a3_doc_path = tmp / "auth_rbac.md"
            a3_openapi_path = tmp / "openapi.json"
            a3_fail_closed_path = tmp / "fail_closed_rbac.md"
            a3_event_outbox_path = tmp / "event_outbox.md"

            a1_path.write_text(json.dumps(_a1_route_scope_fixture(), indent=2) + "\n", encoding="utf-8")
            a3_doc_path.write_text(_a3_auth_rbac_doc(), encoding="utf-8")
            a3_openapi_path.write_text(json.dumps(_a3_openapi_fixture(), indent=2) + "\n", encoding="utf-8")
            a3_fail_closed_path.write_text(_a3_fail_closed_rbac_doc(), encoding="utf-8")
            a3_event_outbox_path.write_text(_a3_event_outbox_doc(), encoding="utf-8")

            payload = build_cross_lane_security_context(
                a1_route_scope_path=a1_path,
                a3_auth_rbac_doc_path=a3_doc_path,
                a3_openapi_path=a3_openapi_path,
                a3_fail_closed_rbac_doc_path=a3_fail_closed_path,
                a3_event_outbox_doc_path=a3_event_outbox_path,
            )

        self.assertTrue(payload["a1_route_scope"]["available"])
        self.assertTrue(payload["a1_route_scope"]["ready_for_a2_security_context"])
        self.assertGreaterEqual(payload["a1_route_scope"]["api_key_route_count"], 1)
        self.assertGreaterEqual(payload["a1_route_scope"]["release_gate_route_count"], 1)
        self.assertTrue(payload["a1_route_scope"]["rls_or_tenant_hardening_observed"])
        self.assertTrue(payload["a3_auth_rbac_boundary"]["available"])
        self.assertTrue(payload["a3_auth_rbac_boundary"]["ready_for_a2_security_context"])
        self.assertTrue(payload["a3_auth_rbac_boundary"]["anchor_present"])
        self.assertEqual(payload["a3_auth_rbac_boundary"]["openapi_auth_path_count"], 3)
        self.assertTrue(payload["a3_auth_rbac_boundary"]["auth_operation_parity_verified"])
        self.assertEqual(
            payload["a3_auth_rbac_boundary"]["documented_auth_operations"],
            payload["a3_auth_rbac_boundary"]["openapi_auth_operations"],
        )
        self.assertTrue(payload["a3_auth_rbac_boundary"]["safety"]["actor_hash_required"])
        self.assertTrue(payload["a3_auth_rbac_boundary"]["safety"]["raw_identity_redacted"])
        self.assertTrue(payload["a3_auth_rbac_boundary"]["safety"]["tokens_forbidden"])
        self.assertTrue(payload["a3_auth_rbac_boundary"]["safety"]["hosted_mutations_blocked"])
        self.assertTrue(payload["a3_auth_rbac_boundary"]["safety"]["metadata_only_audit"])
        self.assertTrue(payload["a3_fail_closed_rbac"]["available"])
        self.assertTrue(payload["a3_fail_closed_rbac"]["ready_for_a2_security_context"])
        self.assertEqual(payload["a3_fail_closed_rbac"]["mutation_endpoint_count"], 9)
        self.assertTrue(payload["a3_fail_closed_rbac"]["safety"]["fail_closed_declared"])
        self.assertTrue(payload["a3_fail_closed_rbac"]["safety"]["denied_response_schema_declared"])
        self.assertTrue(payload["a3_fail_closed_rbac"]["safety"]["raw_request_body_not_echoed"])
        self.assertTrue(payload["a3_event_outbox"]["available"])
        self.assertTrue(payload["a3_event_outbox"]["ready_for_a2_security_context"])
        self.assertEqual(payload["a3_event_outbox"]["write_endpoint_count"], 7)
        self.assertTrue(payload["a3_event_outbox"]["dashboard_payload_declared"])
        self.assertTrue(payload["a3_event_outbox"]["read_surface_declared"])
        self.assertTrue(payload["a3_event_outbox"]["safety"]["event_envelope_declared"])
        self.assertTrue(payload["a3_event_outbox"]["safety"]["metadata_only_events"])
        self.assertTrue(payload["a3_event_outbox"]["safety"]["payload_hashing_declared"])
        self.assertTrue(payload["a2_policy_implications"]["should_block_hosted_mutations_without_a1_auth"])
        self.assertTrue(payload["a2_policy_implications"]["should_require_metadata_only_audit_events"])
        self.assertTrue(payload["a2_policy_implications"]["should_keep_raw_actor_identity_forbidden"])
        self.assertTrue(payload["a2_policy_implications"]["should_require_fail_closed_a3_writes"])
        self.assertTrue(payload["a2_policy_implications"]["should_require_a3_event_outbox_metadata_only"])
        self.assertTrue(payload["a2_policy_implications"]["should_add_route_scope_security_cases"])
        self.assertTrue(payload["a2_policy_implications"]["should_add_auth_rbac_abuse_cases"])
        self.assertTrue(payload["a2_policy_implications"]["should_add_fail_closed_write_abuse_cases"])
        self.assertTrue(payload["a2_policy_implications"]["should_add_event_outbox_integrity_cases"])
        self.assertEqual(
            {item["followup_id"] for item in payload["a2_security_followups"]},
            {
                "a2-route-scope-tenant-boundary",
                "a2-auth-rbac-denied-state-cases",
                "a2-a3-fail-closed-write-abuse-cases",
                "a2-a3-event-outbox-integrity-cases",
            },
        )

    def test_a1_route_scope_fails_closed_on_public_contract_drift(self):
        mutations = {
            "declared_route_count": lambda payload: payload.update(go_route_count=999),
            "public_safe": lambda payload: payload.update(public_safe=False),
            "source_policy": lambda payload: payload["source_policy"].update(tokens_included=True),
            "tenancy_parity": lambda payload: payload["tenancy_route_parity"].update(exact_parity=False),
        }
        expected_fields = {
            "declared_route_count": "declared_route_counts_match",
            "public_safe": "public_safe_source_verified",
            "source_policy": "source_policy_verified",
            "tenancy_parity": "tenancy_route_parity_verified",
        }

        for drift, mutate in mutations.items():
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as tmp_dir:
                path = Path(tmp_dir) / "route_scope.json"
                payload = _a1_route_scope_fixture()
                mutate(payload)
                path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

                context = build_cross_lane_security_context(a1_route_scope_path=path)
                route_scope = context["a1_route_scope"]

                self.assertTrue(route_scope["available"])
                self.assertFalse(route_scope[expected_fields[drift]])
                self.assertFalse(route_scope["ready_for_a2_security_context"])
                self.assertFalse(context["a2_policy_implications"]["should_add_route_scope_security_cases"])

    def test_a3_auth_rbac_fails_closed_on_openapi_operation_drift(self):
        mutations = {
            "missing_operation": lambda paths: paths.pop("/api/a3/auth/context"),
            "wrong_method": lambda paths: paths["/api/a3/auth/authorize"].update(
                {"get": paths["/api/a3/auth/authorize"].pop("post")}
            ),
            "extra_operation": lambda paths: paths.update(
                {"/api/a3/auth/session": {"get": {"responses": {}}}}
            ),
        }

        for drift, mutate in mutations.items():
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir)
                doc_path = tmp / "auth_rbac.md"
                openapi_path = tmp / "openapi.json"
                doc_path.write_text(_a3_auth_rbac_doc(), encoding="utf-8")
                openapi = _a3_openapi_fixture()
                mutate(openapi["paths"])
                openapi_path.write_text(json.dumps(openapi, indent=2) + "\n", encoding="utf-8")

                context = build_cross_lane_security_context(
                    a3_auth_rbac_doc_path=doc_path,
                    a3_openapi_path=openapi_path,
                )
                auth_rbac = context["a3_auth_rbac_boundary"]

                self.assertTrue(auth_rbac["available"])
                self.assertFalse(auth_rbac["auth_operation_parity_verified"])
                self.assertFalse(auth_rbac["ready_for_a2_security_context"])
                self.assertFalse(context["a2_policy_implications"]["should_add_auth_rbac_abuse_cases"])


def _a1_route_scope_fixture() -> dict:
    tenancy_route = "POST /v1/organizations/{organization_id}/projects/{project_id}/runs"
    return {
        "schema_version": "a1.route_scope_manifest.v1",
        "python_hosted_routes": [
            "POST /v1/api-keys",
            "POST /v1/release-gates/evaluate",
            tenancy_route,
        ],
        "ts_openapi_routes": [
            "POST /v1/projects/{project_id}/release-gates",
            tenancy_route,
        ],
        "go_manifest_routes": [
            tenancy_route,
        ],
        "go_route_count": 1,
        "python_route_count": 3,
        "ts_route_count": 2,
        "intentional_route_differences": {"hosted_python_only": ["POST /v1/api-keys"]},
        "public_safe": True,
        "source_paths": [
            "packages/sdk/releasefoundry/saas.py",
            "packages/ts/releasefoundry/src/saas.ts",
            "services/api/migrations/001_a1_large_saas_foundation.sql",
        ],
        "source_policy": {
            "private_evidence_read": False,
            "raw_payloads_included": False,
            "tokens_included": False,
        },
        "tenancy_route_parity": {
            "exact_parity": True,
            "expected_route_count": 1,
            "go_only": [],
            "go_routes": [tenancy_route],
            "python_only": [],
            "python_routes": [tenancy_route],
            "shared_all": [tenancy_route],
            "typescript_only": [],
            "typescript_routes": [tenancy_route],
        },
        "security_notes": [
            "RLS validates organization_id and project_id for tenant isolation.",
        ],
    }


def _a3_auth_rbac_doc() -> str:
    return "\n".join(
        [
            "# A3 Auth RBAC Boundary",
            "ANCHOR: A3_AUTH_RBAC_BOUNDARY_CONTRACT",
            "GET /api/a3/auth/context",
            "GET /api/a3/auth/rbac-policy",
            "POST /api/a3/auth/authorize",
            "actor_hash is required on every local auth context.",
            "Raw actor identity is redacted before A3 stores local state.",
            "API keys, tokens, and cookies are forbidden in dashboard payloads.",
            "Hosted mutations are blocked until A1 hosted auth is available.",
            "A3 emits metadata-only audit events using releasefoundry.event_envelope.v1.",
            "A1 remains source of truth for backend auth and tenant enforcement.",
            "A2 remains source of truth for release policy and abuse verification.",
            "",
        ]
    )


def _a3_openapi_fixture() -> dict:
    return {
        "openapi": "3.1.0",
        "paths": {
            "/api/a3/auth/context": {"get": {"responses": {}}},
            "/api/a3/auth/rbac-policy": {"get": {"responses": {}}},
            "/api/a3/auth/authorize": {"post": {"responses": {}}},
            "/api/a3/reports": {"get": {"responses": {}}},
        },
    }


def _a3_fail_closed_rbac_doc() -> str:
    return "\n".join(
        [
            "# A3 Fail-Closed RBAC Write Paths",
            "",
            "Fail-closed means denied writes return sanitized 403 before state changes.",
            "",
            "## Enforced Routes",
            "",
            "- POST /api/a3/import/a1-run-result",
            "- POST /api/a3/import/a2-grade-result",
            "- POST /api/a3/releases/:releaseId/readbacks",
            "- POST /api/a3/admin/actions/plan",
            "- POST /api/a3/admin/actions/submit",
            "- POST /api/a3/review/waivers",
            "- POST /api/a3/review/approvals",
            "- POST /api/a3/reports/share",
            "- POST /api/a3/reports/:reportId/revoke",
            "- POST /api/a3/reports/:reportId/view",
            "- GET /api/a3/events/outbox",
            "",
            "## Added Operation Policies",
            "",
            "- view_report",
            "- capture_release_readback",
            "- read_event_outbox",
            "- plan_admin_action",
            "",
            "## Local Demo Roles",
            "",
            "- reviewer: share report",
            "- owner: admin action",
            "- auditor: read event outbox",
            "- developer: import local evidence",
            "",
            "Denied responses use a3.api_authz_denied.v1.",
            "Denied responses do not echo the raw request body.",
            "Bearer-value strings, cookies, and API keys are forbidden.",
            "Each denial emits a metadata-only authz audit event.",
            "A1 hosted auth/session middleware remains the hosted dependency.",
            "A2 still owns Scenario, Judge, GradeResult, score, pass/fail, and release gate.",
            "",
        ]
    )


def _a3_event_outbox_doc() -> str:
    return "\n".join(
        [
            "# A3 Event Outbox SaaS Backbone",
            "",
            "Every important A3 control-plane write creates a metadata-only releasefoundry.event_envelope.v1 row.",
            "",
            "## Covered Write Paths",
            "",
            "- POST /api/a3/reports/share",
            "- POST /api/a3/reports/:reportId/view",
            "- POST /api/a3/reports/:reportId/revoke",
            "- POST /api/a3/admin/actions/submit",
            "- POST /api/a3/review/waivers",
            "- POST /api/a3/review/approvals",
            "- POST /api/a3/releases/:releaseId/readbacks",
            "",
            "## New Read Surface",
            "",
            "- GET /api/a3/events/outbox",
            "",
            "## Dashboard Payload",
            "",
            "event_outbox.schema_version = a3.event_outbox_dashboard.v1",
            "",
            "## Idempotency",
            "",
            "Repeated requests with the same key and same payload return duplicate receipts.",
            "",
            "## Safety",
            "",
            "No raw payload body is embedded.",
            "No raw share token is stored.",
            "No API key is stored.",
            "No cookie is stored.",
            "No signed media URL is stored.",
            "No raw email is stored.",
            "Event payloads are hashed with SHA-256.",
            "A1 still owns RunResult, Trace, Observation, ToolCall, runner evidence, and runtime artifacts.",
            "A2 still owns Scenario, Judge, GradeResult, score, pass/fail, release gate, and failure taxonomy.",
            "",
        ]
    )


if __name__ == "__main__":
    unittest.main()
