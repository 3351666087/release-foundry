from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

DATA_MODEL_SCHEMA_VERSION = "releasefoundry.worker_data_model.v1"

JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type: str
    required: bool = True
    description: str = ""
    default: str | None = None
    ref: str | None = None
    enum: tuple[str, ...] = ()
    pii: bool = False

    def to_schema(self) -> JsonDict:
        schema: JsonDict = {"description": self.description or self.name}
        if self.type in {"uuid", "text", "timestamp", "date", "json", "decimal", "integer", "boolean"}:
            schema.update(_json_type_for(self.type))
        else:
            schema.update({"type": "string"})
        if self.enum:
            schema["enum"] = list(self.enum)
        if self.default is not None:
            schema["default"] = self.default
        if self.ref is not None:
            schema["x-ref"] = self.ref
        if self.pii:
            schema["x-pii"] = True
        return schema


@dataclass(frozen=True, slots=True)
class Index:
    name: str
    columns: tuple[str, ...]
    unique: bool = False
    tenant_scoped: bool = True
    where: str | None = None
    description: str = ""

    def to_manifest(self, table_name: str) -> JsonDict:
        payload: JsonDict = {
            "name": self.name,
            "table": table_name,
            "columns": list(self.columns),
            "unique": self.unique,
            "tenant_scoped": self.tenant_scoped,
            "description": self.description,
        }
        if self.where:
            payload["where"] = self.where
        return payload


@dataclass(frozen=True, slots=True)
class Table:
    name: str
    description: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...]
    indexes: tuple[Index, ...] = field(default_factory=tuple)
    retention: str | None = None

    def required_columns(self) -> list[str]:
        return [column.name for column in self.columns if column.required]

    def to_json_schema(self) -> JsonDict:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://releasefoundry.local/schemas/a1/{self.name}.schema.json",
            "title": f"A1 SaaS {self.name} row",
            "description": self.description,
            "type": "object",
            "required": self.required_columns(),
            "properties": {column.name: column.to_schema() for column in self.columns},
            "additionalProperties": False,
            "x-primary-key": list(self.primary_key),
            "x-retention": self.retention,
        }

    def create_table_sqlish(self) -> str:
        lines = [f"CREATE TABLE {self.name} ("]
        rendered = []
        for column in self.columns:
            bits = [f"  {column.name} {column.type.upper()}"]
            if column.required:
                bits.append("NOT NULL")
            if column.default is not None:
                bits.append(f"DEFAULT {column.default}")
            if column.ref is not None:
                bits.append(f"REFERENCES {column.ref}")
            rendered.append(" ".join(bits))
        rendered.append(f"  PRIMARY KEY ({', '.join(self.primary_key)})")
        lines.extend([line + ("," if idx < len(rendered) - 1 else "") for idx, line in enumerate(rendered)])
        lines.append(");")
        return "\n".join(lines)


COMMON_TIMESTAMPS = (
    Column("created_at", "timestamp", description="UTC creation timestamp", default="now()"),
    Column("updated_at", "timestamp", description="UTC last update timestamp", default="now()"),
)

TENANT = Column("tenant_id", "text", description="Organization/tenant boundary identifier")
WORKSPACE = Column("workspace_id", "text", description="Workspace identifier within tenant")
PROJECT = Column("project_id", "text", description="Project identifier within workspace")
ENVIRONMENT = Column("environment_id", "text", description="Environment identifier such as dev/staging/prod")
RUN = Column("run_id", "text", description="Evaluation or worker run identifier")
DATASET = Column("dataset_id", "text", description="Dataset identifier")


def c(name: str, type_: str, *, required: bool = True, description: str = "", default: str | None = None, ref: str | None = None, enum: tuple[str, ...] = (), pii: bool = False) -> Column:
    return Column(name, type_, required=required, description=description, default=default, ref=ref, enum=enum, pii=pii)


def ix(name: str, columns: tuple[str, ...], *, unique: bool = False, tenant_scoped: bool = True, where: str | None = None, description: str = "") -> Index:
    return Index(name, columns, unique=unique, tenant_scoped=tenant_scoped, where=where, description=description)


TABLES: tuple[Table, ...] = (
    Table(
        "organizations",
        "Commercial SaaS tenant root for account ownership, data isolation, quota, and billing grouping.",
        (TENANT, c("slug", "text"), c("display_name", "text"), c("status", "text", enum=("active", "suspended", "deleted"), default="active"), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id",),
        (ix("organizations_slug_uidx", ("slug",), unique=True, tenant_scoped=False, description="Global organization slug lookup"),),
    ),
    Table(
        "workspaces",
        "Collaboration boundary below organization; projects inherit tenant and workspace scope.",
        (TENANT, WORKSPACE, c("slug", "text"), c("display_name", "text"), c("status", "text", enum=("active", "archived"), default="active"), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "workspace_id"),
        (ix("workspaces_tenant_slug_uidx", ("tenant_id", "slug"), unique=True, description="Tenant-scoped workspace slug lookup"),),
    ),
    Table(
        "projects",
        "Product or evaluation project containing datasets, environments, runs, artifacts, and integrations.",
        (TENANT, WORKSPACE, PROJECT, c("slug", "text"), c("display_name", "text"), c("status", "text", enum=("active", "archived"), default="active"), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "project_id"),
        (ix("projects_workspace_slug_uidx", ("tenant_id", "workspace_id", "slug"), unique=True), ix("projects_workspace_idx", ("tenant_id", "workspace_id"))),
    ),
    Table(
        "environments",
        "Named deploy/runtime context for a project, e.g. dev, staging, production, or private eval workers.",
        (TENANT, WORKSPACE, PROJECT, ENVIRONMENT, c("name", "text"), c("kind", "text", enum=("dev", "staging", "prod", "sandbox", "custom")), c("config", "json", required=False, default="{}"), c("status", "text", enum=("active", "disabled"), default="active"), *COMMON_TIMESTAMPS),
        ("tenant_id", "environment_id"),
        (ix("environments_project_name_uidx", ("tenant_id", "project_id", "name"), unique=True),),
    ),
    Table(
        "datasets",
        "Immutable or versioned benchmark case collection used by queued and completed runs.",
        (TENANT, WORKSPACE, PROJECT, DATASET, c("name", "text"), c("version", "text", default="v1"), c("case_count", "integer", default="0"), c("content_hash", "text", required=False), c("storage_uri", "text", required=False), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "dataset_id"),
        (ix("datasets_project_version_uidx", ("tenant_id", "project_id", "name", "version"), unique=True), ix("datasets_project_idx", ("tenant_id", "project_id"))),
    ),
    Table(
        "runs",
        "Worker/evaluation execution envelope with lifecycle, agent, dataset, and environment references.",
        (TENANT, WORKSPACE, PROJECT, ENVIRONMENT, DATASET, RUN, c("agent_ref", "text"), c("status", "text", enum=("queued", "running", "completed", "failed", "cancelled", "expired", "dead_lettered"), default="queued"), c("runner_id", "text", required=False), c("attempt", "integer", default="0"), c("max_attempts", "integer", default="3"), c("lease_owner_id", "text", required=False), c("lease_expires_at", "timestamp", required=False), c("lease_heartbeat_at", "timestamp", required=False), c("lease_reclaim_count", "integer", default="0"), c("started_at", "timestamp", required=False), c("finished_at", "timestamp", required=False), c("last_error", "json", required=False), c("dead_letter_reason", "text", required=False), c("summary", "json", required=False, default="{}"), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "run_id"),
        (ix("runs_project_status_idx", ("tenant_id", "project_id", "status", "created_at")), ix("runs_dataset_idx", ("tenant_id", "dataset_id", "created_at")), ix("runs_environment_idx", ("tenant_id", "environment_id", "created_at")), ix("runs_lease_expiry_idx", ("tenant_id", "status", "lease_expires_at"), where="lease_expires_at IS NOT NULL")),
    ),
    Table(
        "case_results",
        "Per-case result rows for pass/fail/error rollups, clustering, replay, and evidence lookup.",
        (TENANT, WORKSPACE, PROJECT, RUN, c("case_result_id", "text"), c("case_id", "text"), c("status", "text", enum=("passed", "failed", "errored", "timed_out", "skipped")), c("score", "decimal", required=False), c("duration_ms", "integer", required=False), c("assertions", "json", required=False, default="[]"), c("error", "json", required=False), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "case_result_id"),
        (ix("case_results_run_case_uidx", ("tenant_id", "run_id", "case_id"), unique=True), ix("case_results_project_status_idx", ("tenant_id", "project_id", "status"))),
    ),
    Table(
        "trace_events",
        "Append-only timeline of worker, tool, model, browser, and evaluator events for replay/debug.",
        (TENANT, WORKSPACE, PROJECT, RUN, c("trace_event_id", "text"), c("case_result_id", "text", required=False), c("sequence", "integer"), c("event_type", "text"), c("event_time", "timestamp", default="now()"), c("payload", "json", default="{}"), c("redaction_state", "text", enum=("raw_local", "redacted", "public"), default="redacted"), *COMMON_TIMESTAMPS),
        ("tenant_id", "trace_event_id"),
        (ix("trace_events_run_sequence_uidx", ("tenant_id", "run_id", "sequence"), unique=True), ix("trace_events_case_idx", ("tenant_id", "case_result_id", "sequence"))),
        retention="hot 30d, archive 400d unless evidence bundle pins event ids",
    ),
    Table(
        "artifacts",
        "Files and generated assets produced by workers, reports, screenshots, and exports.",
        (TENANT, WORKSPACE, PROJECT, RUN, c("artifact_id", "text"), c("case_result_id", "text", required=False), c("kind", "text", enum=("log", "screenshot", "report", "dataset", "export", "other")), c("name", "text"), c("mime_type", "text", required=False), c("size_bytes", "integer", required=False), c("sha256", "text", required=False), c("storage_uri", "text"), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "artifact_id"),
        (ix("artifacts_run_kind_idx", ("tenant_id", "run_id", "kind")), ix("artifacts_sha_idx", ("tenant_id", "sha256"), where="sha256 IS NOT NULL")),
    ),
    Table(
        "evidence_bundles",
        "Curated immutable evidence bundle linking runs, case results, trace events, and artifacts for audits or release gates.",
        (TENANT, WORKSPACE, PROJECT, c("evidence_bundle_id", "text"), c("name", "text"), c("status", "text", enum=("draft", "sealed", "superseded"), default="draft"), c("run_ids", "json", default="[]"), c("case_result_ids", "json", required=False, default="[]"), c("trace_event_ids", "json", required=False, default="[]"), c("artifact_ids", "json", required=False, default="[]"), c("sealed_at", "timestamp", required=False), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "evidence_bundle_id"),
        (ix("evidence_bundles_project_status_idx", ("tenant_id", "project_id", "status", "created_at")),),
    ),
    Table(
        "api_keys",
        "Hashed API key records for scoped SDK/API access; public exports never include raw secrets.",
        (TENANT, WORKSPACE, PROJECT, c("api_key_id", "text"), c("name", "text"), c("prefix", "text"), c("secret_hash", "text"), c("scopes", "json", default="[]"), c("status", "text", enum=("active", "revoked"), default="active"), c("last_used_at", "timestamp", required=False), c("expires_at", "timestamp", required=False), *COMMON_TIMESTAMPS),
        ("tenant_id", "api_key_id"),
        (ix("api_keys_project_prefix_uidx", ("tenant_id", "project_id", "prefix"), unique=True), ix("api_keys_active_idx", ("tenant_id", "project_id", "status"), where="status = 'active'")),
    ),
    Table(
        "webhooks",
        "Outbound webhook endpoints and delivery policy for run, evidence, and billing events.",
        (TENANT, WORKSPACE, PROJECT, c("webhook_id", "text"), c("url", "text", pii=True), c("event_types", "json", default="[]"), c("secret_hash", "text", required=False), c("status", "text", enum=("active", "disabled"), default="active"), c("retry_policy", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "webhook_id"),
        (ix("webhooks_project_status_idx", ("tenant_id", "project_id", "status")),),
    ),
    Table(
        "usage_ledger",
        "Append-only metering ledger for billable and quota-tracked SaaS operations.",
        (TENANT, WORKSPACE, PROJECT, c("usage_ledger_id", "text"), c("billing_account_id", "text", required=False), c("operation", "text"), c("units", "integer", default="1"), c("unit_type", "text", default="event"), c("occurred_at", "timestamp", default="now()"), c("idempotency_key", "text", required=False), c("source_id", "text", required=False), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "usage_ledger_id"),
        (ix("usage_ledger_idempotency_uidx", ("tenant_id", "project_id", "operation", "idempotency_key"), unique=True, where="idempotency_key IS NOT NULL"), ix("usage_ledger_project_time_idx", ("tenant_id", "project_id", "occurred_at"))),
        retention="append-only; compact monthly into billing exports after 24 months",
    ),
    Table(
        "quota_policies",
        "Tenant/workspace/project quota definitions and soft/hard limit policy.",
        (TENANT, c("quota_policy_id", "text"), WORKSPACE, PROJECT, c("operation", "text"), c("limit", "integer"), c("period", "text", enum=("minute", "hour", "day", "month", "lifetime"), default="month"), c("enforcement", "text", enum=("soft", "hard"), default="hard"), c("status", "text", enum=("active", "disabled"), default="active"), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "quota_policy_id"),
        (ix("quota_policies_scope_operation_uidx", ("tenant_id", "workspace_id", "project_id", "operation", "period"), unique=True),),
    ),
    Table(
        "billing_accounts",
        "Commercial billing profile linked to organization with plan, currency, tax, and invoice metadata.",
        (TENANT, c("billing_account_id", "text"), c("plan", "text", enum=("free", "team", "enterprise", "custom")), c("currency", "text", default="USD"), c("status", "text", enum=("active", "past_due", "cancelled"), default="active"), c("billing_email", "text", pii=True), c("external_customer_ref", "text", required=False), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "billing_account_id"),
        (ix("billing_accounts_tenant_status_idx", ("tenant_id", "status")),),
    ),
    Table(
        "integrations",
        "Project integrations such as GitHub, Slack, storage, CI, model providers, or internal webhooks.",
        (TENANT, WORKSPACE, PROJECT, c("integration_id", "text"), c("provider", "text"), c("display_name", "text"), c("status", "text", enum=("active", "disabled", "error"), default="active"), c("config", "json", required=False, default="{}"), c("secret_ref", "text", required=False), c("last_synced_at", "timestamp", required=False), *COMMON_TIMESTAMPS),
        ("tenant_id", "integration_id"),
        (ix("integrations_project_provider_uidx", ("tenant_id", "project_id", "provider", "display_name"), unique=True),),
    ),
    Table(
        "audit_log",
        "Append-only administrative and API activity log for tenant-scoped forensic review.",
        (TENANT, WORKSPACE, PROJECT, c("audit_log_id", "text"), c("actor_type", "text", enum=("user", "api_key", "system", "worker")), c("actor_id", "text", required=False), c("action", "text"), c("target_type", "text", required=False), c("target_id", "text", required=False), c("occurred_at", "timestamp", default="now()"), c("ip_hash", "text", required=False), c("user_agent", "text", required=False), c("metadata", "json", required=False, default="{}"), *COMMON_TIMESTAMPS),
        ("tenant_id", "audit_log_id"),
        (ix("audit_log_project_time_idx", ("tenant_id", "project_id", "occurred_at")), ix("audit_log_actor_idx", ("tenant_id", "actor_type", "actor_id", "occurred_at"))),
        retention="append-only; retain 400d minimum for commercial audit readiness",
    ),
)

TABLE_BY_NAME: Mapping[str, Table] = {table.name: table for table in TABLES}


def export_json_schema() -> JsonDict:
    """Return one self-contained JSON Schema bundle for the worker SaaS data model."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://releasefoundry.local/schemas/a1/worker_data_model.schema.json",
        "title": "A1 Worker Commercial SaaS DB-shaped Data Model",
        "schema_version": DATA_MODEL_SCHEMA_VERSION,
        "type": "object",
        "required": ["schema_version", "tables"],
        "properties": {
            "schema_version": {"const": DATA_MODEL_SCHEMA_VERSION},
            "tables": {
                "type": "object",
                "additionalProperties": {"type": "object"},
            },
        },
        "tables": {table.name: table.to_json_schema() for table in TABLES},
        "x-table-order": [table.name for table in TABLES],
    }


def export_sqlish_migration() -> str:
    """Return deterministic SQL-ish migration text with no external DB dependency."""
    sections = [
        "-- A1 Worker commercial SaaS DB-shaped data model",
        f"-- schema_version: {DATA_MODEL_SCHEMA_VERSION}",
        "-- Dialect: SQL-ish documentation/migration contract; adapters may translate types.",
        "",
    ]
    for table in TABLES:
        sections.append(f"-- {table.description}")
        sections.append(table.create_table_sqlish())
        for index in table.indexes:
            unique = "UNIQUE " if index.unique else ""
            where = f" WHERE {index.where}" if index.where else ""
            sections.append(f"CREATE {unique}INDEX {index.name} ON {table.name} ({', '.join(index.columns)}){where};")
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


def export_tenant_index_manifest() -> JsonDict:
    """Return indexes and access patterns that preserve tenant scoping by construction."""
    tables = []
    violations = []
    for table in TABLES:
        table_indexes = [index.to_manifest(table.name) for index in table.indexes]
        tenant_columns = [column.name for column in table.columns if column.name == "tenant_id"]
        if not tenant_columns:
            violations.append({"table": table.name, "issue": "missing tenant_id"})
        for index in table.indexes:
            if index.tenant_scoped and (not index.columns or index.columns[0] != "tenant_id"):
                violations.append({"table": table.name, "index": index.name, "issue": "tenant-scoped index must start with tenant_id"})
        tables.append(
            {
                "table": table.name,
                "primary_key": list(table.primary_key),
                "tenant_scoped": "tenant_id" in table.primary_key or any(column.name == "tenant_id" for column in table.columns),
                "indexes": table_indexes,
                "recommended_query_prefix": ["tenant_id"],
            }
        )
    return {
        "schema_version": DATA_MODEL_SCHEMA_VERSION,
        "tenant_scope_column": "tenant_id",
        "rule": "Every SaaS row carries tenant_id; every tenant-scoped secondary index begins with tenant_id.",
        "tables": tables,
        "violations": violations,
    }


def export_all() -> JsonDict:
    return {
        "json_schema": export_json_schema(),
        "sqlish_migration": export_sqlish_migration(),
        "tenant_index_manifest": export_tenant_index_manifest(),
    }


def dumps_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _json_type_for(type_name: str) -> JsonDict:
    if type_name in {"uuid", "text", "timestamp", "date", "decimal"}:
        payload: JsonDict = {"type": "string"}
        if type_name == "timestamp":
            payload["format"] = "date-time"
        return payload
    if type_name == "integer":
        return {"type": "integer"}
    if type_name == "boolean":
        return {"type": "boolean"}
    if type_name == "json":
        return {"type": ["object", "array", "string", "number", "boolean", "null"]}
    return {"type": "string"}
