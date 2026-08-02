"""Verification contract for an installable ReleaseFoundry Product Release.

The verifier is intentionally strict:

* a product release has a canonical ``releasefoundry-product@<semver>`` identifier;
* the source tree must be represented as clean and pinned to a commit;
* every required capability is backed by a hashed, live verification receipt;
* released services are pinned by digest;
* ReleaseFoundry-owned images carry SBOM, signature, and provenance evidence;
* installers, SDK packages, and operator runbooks are hashed;
* fixture, test, cache, and runtime directories cannot satisfy release evidence.

The resulting manifest digest is the value that a Customer Agent Release must
bind alongside ``product_release_id``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping


PRODUCT_RELEASE_MANIFEST_SCHEMA = "releasefoundry.product_release_manifest.v1"
PRODUCT_RELEASE_VERIFICATION_SCHEMA = "releasefoundry.product_release_verification.v1"
VERIFICATION_RECEIPT_SCHEMA = "releasefoundry.verification_receipt.v1"

_PRODUCT_RELEASE_ID_RE = re.compile(
    r"^releasefoundry-product@"
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RFC3339_Z_RE = re.compile(r"Z$")
_DISALLOWED_LIVE_EVIDENCE_ROOTS = {
    ".data",
    ".next",
    ".pytest_cache",
    ".runtime",
    "examples",
    "fixtures",
    "node_modules",
    "test-results",
    "tests",
    "tmp",
}
_SAFE_SECRET_SENTINELS = {"", "redacted", "<redacted>", "not-set", "none"}
_SENSITIVE_KEY_PARTS = ("password", "private_key", "secret", "token")


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    path: str
    message: str


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = _RFC3339_Z_RE.sub("+00:00", value.strip())
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


class _Verifier:
    def __init__(self, manifest_path: Path, repo_root: Path | None) -> None:
        self.manifest_path = manifest_path.resolve()
        self.repo_root = (repo_root or manifest_path.parent).resolve()
        self.issues: list[VerificationIssue] = []
        self.checked_receipt_ids: list[str] = []
        self.policy_id: str | None = None

    def issue(self, code: str, path: str, message: str) -> None:
        self.issues.append(VerificationIssue(code=code, path=path, message=message))

    def require_mapping(self, value: Any, path: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            self.issue("invalid_type", path, "must be an object")
            return {}
        return value

    def require_list(self, value: Any, path: str) -> list[Any]:
        if not isinstance(value, list):
            self.issue("invalid_type", path, "must be an array")
            return []
        return value

    def resolve_repo_path(
        self,
        raw_path: Any,
        path: str,
        *,
        live_evidence: bool,
    ) -> Path | None:
        if not isinstance(raw_path, str) or not raw_path.strip():
            self.issue("missing_path", path, "must be a non-empty repository-relative path")
            return None
        if "\\" in raw_path:
            self.issue("non_portable_path", path, "must use forward slashes")
            return None
        portable = PurePosixPath(raw_path)
        if portable.is_absolute() or ".." in portable.parts:
            self.issue("unsafe_path", path, "must stay inside the repository")
            return None
        if live_evidence and portable.parts:
            root = portable.parts[0].lower()
            if root in _DISALLOWED_LIVE_EVIDENCE_ROOTS:
                self.issue(
                    "non_release_evidence",
                    path,
                    f"{root!r} cannot satisfy live release evidence",
                )
                return None
        resolved = (self.repo_root / Path(*portable.parts)).resolve()
        if resolved != self.repo_root and self.repo_root not in resolved.parents:
            self.issue("unsafe_path", path, "resolved path escapes the repository")
            return None
        return resolved

    def verify_file_ref(
        self,
        value: Any,
        path: str,
        *,
        live_evidence: bool,
        load_json: bool = False,
    ) -> tuple[Path | None, Any | None]:
        ref = self.require_mapping(value, path)
        resolved = self.resolve_repo_path(
            ref.get("path"),
            f"{path}.path",
            live_evidence=live_evidence,
        )
        expected_sha256 = ref.get("sha256")
        if not isinstance(expected_sha256, str) or not _SHA256_RE.fullmatch(expected_sha256):
            self.issue("invalid_sha256", f"{path}.sha256", "must be a lowercase SHA-256")
        if resolved is None:
            return None, None
        if not resolved.is_file():
            self.issue("missing_evidence_file", f"{path}.path", f"{resolved} does not exist")
            return resolved, None
        actual_sha256 = _sha256_file(resolved)
        if expected_sha256 != actual_sha256:
            self.issue(
                "evidence_digest_mismatch",
                f"{path}.sha256",
                f"expected {expected_sha256!r}, got {actual_sha256}",
            )
        if not load_json:
            return resolved, None
        try:
            return resolved, json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.issue("invalid_json_evidence", f"{path}.path", str(exc))
            return resolved, None

    def verify_policy(self, manifest: Mapping[str, Any]) -> Mapping[str, Any]:
        policy_ref = self.require_mapping(manifest.get("policy"), "policy")
        _, policy = self.verify_file_ref(
            policy_ref,
            "policy",
            live_evidence=False,
            load_json=True,
        )
        if not isinstance(policy, Mapping):
            return {}
        self.policy_id = str(policy.get("policy_id") or "")
        if policy_ref.get("id") != self.policy_id:
            self.issue(
                "policy_id_mismatch",
                "policy.id",
                f"expected {self.policy_id!r} from the pinned policy",
            )
        if policy.get("schema_version") != "releasefoundry.product_release_policy.v1":
            self.issue(
                "unsupported_policy_schema",
                "policy.schema_version",
                "must be releasefoundry.product_release_policy.v1",
            )
        return policy

    def verify_source(self, manifest: Mapping[str, Any]) -> str:
        source = self.require_mapping(manifest.get("source"), "source")
        repository = source.get("repository")
        if not isinstance(repository, str) or not repository.strip():
            self.issue("missing_repository", "source.repository", "must identify the source repository")
        commit_sha = source.get("commit_sha")
        if not isinstance(commit_sha, str) or not _COMMIT_RE.fullmatch(commit_sha):
            self.issue("invalid_commit", "source.commit_sha", "must be a 40- or 64-character Git commit SHA")
            commit_sha = ""
        if source.get("dirty") is not False:
            self.issue("dirty_source", "source.dirty", "a Product Release must come from a clean source tree")
        return commit_sha

    def verify_deployment(self, manifest: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
        deployment = self.require_mapping(manifest.get("deployment"), "deployment")
        self.verify_file_ref(
            deployment.get("bundle"),
            "deployment.bundle",
            live_evidence=True,
        )
        self.verify_file_ref(
            deployment.get("compose"),
            "deployment.compose",
            live_evidence=True,
        )
        installers = self.require_mapping(deployment.get("installers"), "deployment.installers")
        for installer_name in ("posix", "powershell"):
            self.verify_file_ref(
                installers.get(installer_name),
                f"deployment.installers.{installer_name}",
                live_evidence=True,
            )

        services = self.require_list(deployment.get("services"), "deployment.services")
        observed_roles: set[str] = set()
        observed_names: set[str] = set()
        for index, item in enumerate(services):
            item_path = f"deployment.services[{index}]"
            service = self.require_mapping(item, item_path)
            name = service.get("name")
            if not isinstance(name, str) or not name.strip():
                self.issue("invalid_service_name", f"{item_path}.name", "must be non-empty")
            elif name in observed_names:
                self.issue("duplicate_service", f"{item_path}.name", f"duplicate service {name!r}")
            else:
                observed_names.add(name)
            image = service.get("image")
            if not isinstance(image, str) or not image.strip():
                self.issue("invalid_image", f"{item_path}.image", "must be non-empty")
            digest = service.get("digest")
            if (
                not isinstance(digest, str)
                or not digest.startswith("sha256:")
                or not _SHA256_RE.fullmatch(digest.removeprefix("sha256:"))
            ):
                self.issue(
                    "unpinned_image",
                    f"{item_path}.digest",
                    "released services must use an immutable sha256 digest",
                )
            roles = self.require_list(service.get("roles"), f"{item_path}.roles")
            for role in roles:
                if isinstance(role, str) and role:
                    observed_roles.add(role)
                else:
                    self.issue("invalid_service_role", f"{item_path}.roles", "roles must be strings")
            ownership = service.get("ownership")
            if ownership not in {"releasefoundry", "third_party"}:
                self.issue(
                    "invalid_service_ownership",
                    f"{item_path}.ownership",
                    "must be 'releasefoundry' or 'third_party'",
                )
            if ownership == "releasefoundry":
                supply_chain = self.require_mapping(
                    service.get("supply_chain"),
                    f"{item_path}.supply_chain",
                )
                for evidence_name in ("sbom", "signature", "provenance"):
                    self.verify_file_ref(
                        supply_chain.get(evidence_name),
                        f"{item_path}.supply_chain.{evidence_name}",
                        live_evidence=True,
                    )

        required_roles = {
            role
            for role in self.require_list(
                policy.get("required_service_roles"),
                "policy.required_service_roles",
            )
            if isinstance(role, str)
        }
        for missing_role in sorted(required_roles - observed_roles):
            self.issue(
                "missing_service_role",
                "deployment.services",
                f"no released service provides required role {missing_role!r}",
            )

    def verify_sdks(self, manifest: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
        sdks = self.require_list(manifest.get("sdks"), "sdks")
        observed_languages: set[str] = set()
        for index, item in enumerate(sdks):
            item_path = f"sdks[{index}]"
            sdk = self.require_mapping(item, item_path)
            language = sdk.get("language")
            if not isinstance(language, str) or not language:
                self.issue("invalid_sdk_language", f"{item_path}.language", "must be non-empty")
            elif language in observed_languages:
                self.issue("duplicate_sdk_language", f"{item_path}.language", f"duplicate {language!r}")
            else:
                observed_languages.add(language)
            for field in ("package", "version"):
                if not isinstance(sdk.get(field), str) or not sdk.get(field):
                    self.issue("invalid_sdk_metadata", f"{item_path}.{field}", "must be non-empty")
            self.verify_file_ref(
                sdk.get("artifact"),
                f"{item_path}.artifact",
                live_evidence=True,
            )
        required_languages = {
            language
            for language in self.require_list(
                policy.get("required_sdk_languages"),
                "policy.required_sdk_languages",
            )
            if isinstance(language, str)
        }
        for missing_language in sorted(required_languages - observed_languages):
            self.issue(
                "missing_sdk",
                "sdks",
                f"missing released SDK artifact for {missing_language!r}",
            )

    def verify_runbooks(self, manifest: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
        runbooks = self.require_mapping(manifest.get("runbooks"), "runbooks")
        required_runbooks = self.require_list(
            policy.get("required_runbooks"),
            "policy.required_runbooks",
        )
        for name in required_runbooks:
            if not isinstance(name, str):
                self.issue("invalid_policy_runbook", "policy.required_runbooks", "entries must be strings")
                continue
            self.verify_file_ref(
                runbooks.get(name),
                f"runbooks.{name}",
                live_evidence=False,
            )

    def verify_receipt(
        self,
        receipt_id: str,
        ref: Any,
        *,
        product_release_id: str,
        source_commit: str,
        required_environment_fields: Iterable[str],
    ) -> None:
        _, receipt = self.verify_file_ref(
            ref,
            f"verification.receipts.{receipt_id}",
            live_evidence=True,
            load_json=True,
        )
        if not isinstance(receipt, Mapping):
            return
        self.checked_receipt_ids.append(receipt_id)
        prefix = f"verification.receipts.{receipt_id}.content"
        if receipt.get("schema_version") != VERIFICATION_RECEIPT_SCHEMA:
            self.issue(
                "unsupported_receipt_schema",
                f"{prefix}.schema_version",
                f"must be {VERIFICATION_RECEIPT_SCHEMA}",
            )
        if receipt.get("receipt_id") != receipt_id:
            self.issue("receipt_id_mismatch", f"{prefix}.receipt_id", f"must be {receipt_id!r}")
        if receipt.get("product_release_id") != product_release_id:
            self.issue(
                "receipt_release_mismatch",
                f"{prefix}.product_release_id",
                f"must be {product_release_id!r}",
            )
        if receipt.get("source_commit") != source_commit:
            self.issue(
                "receipt_source_mismatch",
                f"{prefix}.source_commit",
                f"must be {source_commit!r}",
            )
        if receipt.get("mode") != "live":
            self.issue(
                "non_live_receipt",
                f"{prefix}.mode",
                "fixtures, mocks, dry runs, and synthetic receipts cannot release the product",
            )
        if receipt.get("status") != "passed":
            self.issue("failed_receipt", f"{prefix}.status", "must be 'passed'")
        if type(receipt.get("exit_code")) is not int or receipt.get("exit_code") != 0:
            self.issue("failed_receipt", f"{prefix}.exit_code", "must be integer 0")
        command = receipt.get("command")
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(part, str) or not part for part in command)
        ):
            self.issue(
                "invalid_receipt_command",
                f"{prefix}.command",
                "must be a non-empty argv array",
            )
        started_at = _parse_rfc3339(receipt.get("started_at"))
        finished_at = _parse_rfc3339(receipt.get("finished_at"))
        if started_at is None:
            self.issue("invalid_timestamp", f"{prefix}.started_at", "must be timezone-aware RFC 3339")
        if finished_at is None:
            self.issue("invalid_timestamp", f"{prefix}.finished_at", "must be timezone-aware RFC 3339")
        if started_at is not None and finished_at is not None and finished_at < started_at:
            self.issue("invalid_timestamp_order", f"{prefix}.finished_at", "precedes started_at")
        environment = self.require_mapping(receipt.get("environment"), f"{prefix}.environment")
        for field in required_environment_fields:
            if not isinstance(environment.get(field), str) or not environment.get(field):
                self.issue(
                    "missing_receipt_environment",
                    f"{prefix}.environment.{field}",
                    "must be recorded for reproducibility",
                )

    def receipt_environment_fields(
        self,
        receipt_id: str,
        policy: Mapping[str, Any],
    ) -> list[str]:
        configuration = self.require_mapping(
            policy.get("receipt_environment_fields"),
            "policy.receipt_environment_fields",
        )
        fields: list[str] = []
        default_fields = configuration.get("default", [])
        if isinstance(default_fields, list):
            fields.extend(field for field in default_fields if isinstance(field, str))
        for selector, selected_fields in configuration.items():
            if not isinstance(selector, str) or not selector.startswith("prefix:"):
                continue
            if not receipt_id.startswith(selector.removeprefix("prefix:")):
                continue
            if isinstance(selected_fields, list):
                fields.extend(field for field in selected_fields if isinstance(field, str))
        return list(dict.fromkeys(fields))

    def verify_receipts(
        self,
        manifest: Mapping[str, Any],
        policy: Mapping[str, Any],
        *,
        product_release_id: str,
        source_commit: str,
    ) -> None:
        verification = self.require_mapping(manifest.get("verification"), "verification")
        receipts = self.require_mapping(verification.get("receipts"), "verification.receipts")
        required_receipts = self.require_list(
            policy.get("required_receipts"),
            "policy.required_receipts",
        )
        for receipt_id in required_receipts:
            if not isinstance(receipt_id, str):
                self.issue("invalid_policy_receipt", "policy.required_receipts", "entries must be strings")
                continue
            if receipt_id not in receipts:
                self.issue(
                    "missing_receipt",
                    f"verification.receipts.{receipt_id}",
                    "required live verification evidence is absent",
                )
                continue
            self.verify_receipt(
                receipt_id,
                receipts[receipt_id],
                product_release_id=product_release_id,
                source_commit=source_commit,
                required_environment_fields=self.receipt_environment_fields(receipt_id, policy),
            )

    def scan_secret_material(self, value: Any, path: str = "$") -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                lowered = str(key).lower()
                if (
                    isinstance(child, str)
                    and any(part in lowered for part in _SENSITIVE_KEY_PARTS)
                    and child.strip().lower() not in _SAFE_SECRET_SENTINELS
                    and not child.startswith(("env:", "vault:", "secret:"))
                ):
                    self.issue(
                        "embedded_secret_material",
                        child_path,
                        "release manifests may contain only secret references, never secret values",
                    )
                self.scan_secret_material(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self.scan_secret_material(child, f"{path}[{index}]")

    def verify(self) -> dict[str, Any]:
        try:
            manifest_raw = self.manifest_path.read_bytes()
        except OSError as exc:
            self.issue("manifest_read_failed", "$", str(exc))
            return self.result(product_release_id=None, manifest_sha256=None)
        manifest_sha256 = _sha256_bytes(manifest_raw)
        try:
            manifest = json.loads(manifest_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.issue("invalid_manifest_json", "$", str(exc))
            return self.result(product_release_id=None, manifest_sha256=manifest_sha256)
        manifest = self.require_mapping(manifest, "$")
        if manifest.get("schema_version") != PRODUCT_RELEASE_MANIFEST_SCHEMA:
            self.issue(
                "unsupported_manifest_schema",
                "schema_version",
                f"must be {PRODUCT_RELEASE_MANIFEST_SCHEMA}",
            )
        product_release_id = manifest.get("product_release_id")
        if not isinstance(product_release_id, str) or not _PRODUCT_RELEASE_ID_RE.fullmatch(product_release_id):
            self.issue(
                "invalid_product_release_id",
                "product_release_id",
                "must be canonical releasefoundry-product@<semver>",
            )
            product_release_id = str(product_release_id or "")
        if _parse_rfc3339(manifest.get("generated_at")) is None:
            self.issue(
                "invalid_timestamp",
                "generated_at",
                "must be a timezone-aware RFC 3339 timestamp",
            )
        self.scan_secret_material(manifest)
        policy = self.verify_policy(manifest)
        source_commit = self.verify_source(manifest)
        self.verify_deployment(manifest, policy)
        self.verify_sdks(manifest, policy)
        self.verify_runbooks(manifest, policy)
        self.verify_receipts(
            manifest,
            policy,
            product_release_id=product_release_id,
            source_commit=source_commit,
        )
        return self.result(
            product_release_id=product_release_id or None,
            manifest_sha256=manifest_sha256,
        )

    def result(
        self,
        *,
        product_release_id: str | None,
        manifest_sha256: str | None,
    ) -> dict[str, Any]:
        issues = sorted(
            self.issues,
            key=lambda issue: (issue.code, issue.path, issue.message),
        )
        approved = not issues
        return {
            "schema_version": PRODUCT_RELEASE_VERIFICATION_SCHEMA,
            "decision": "approve_product_release" if approved else "block_product_release",
            "product_release_id": product_release_id,
            "product_release_manifest_sha256": manifest_sha256,
            "policy_id": self.policy_id,
            "checked_receipt_ids": sorted(set(self.checked_receipt_ids)),
            "blocking_reasons": sorted({issue.code for issue in issues}),
            "issues": [asdict(issue) for issue in issues],
        }


def verify_product_release_manifest(
    manifest_path: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify a Product Release manifest and return a fail-closed decision."""

    path = Path(manifest_path)
    root = Path(repo_root) if repo_root is not None else None
    return _Verifier(path, root).verify()

