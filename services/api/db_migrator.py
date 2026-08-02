from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Mapping, Sequence

from services.api.data_model import DATA_MODEL_SCHEMA_VERSION, Index, TABLES, Table

TENANT_SCOPE_COLUMN = "tenant_id"
SCHEMA_LEDGER_TABLE = "schema_migrations"
SUPPORTED_DIALECTS = frozenset({"sqlite", "postgres"})
GO_POSTGRES_VERTICAL_SLICE_TABLES = frozenset({"runs", "idempotency_keys", "usage_ledger", "audit_log", "jobs"})
GO_POSTGRES_VERTICAL_SLICE_FUNCTIONS = frozenset(
    {"ensure_idempotency_fingerprint", "rollup_usage", "audit_chain_tail"}
)

GO_POSTGRES_VERTICAL_SLICE_CONTRACT: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "runs": {
        "required_columns": (
            "organization_id",
            "project_id",
            "status",
            "request_fingerprint",
            "created_at",
            "updated_at",
        ),
        "required_indexes": ("idx_runs_project_created", "idx_runs_project_status"),
    },
    "idempotency_keys": {
        "required_columns": (
            "organization_id",
            "project_id",
            "idempotency_key",
            "request_method",
            "request_path",
            "fingerprint",
            "created_at",
        ),
        "required_indexes": ("idx_idempotency_keys_created",),
    },
    "usage_ledger": {
        "required_columns": (
            "organization_id",
            "project_id",
            "meter",
            "quantity",
            "unit",
            "idempotency_key_id",
            "period_start",
            "period_end",
            "created_at",
        ),
        "required_indexes": (
            "idx_usage_ledger_idempotency_key_unique",
            "idx_usage_ledger_scope_meter_period",
            "idx_usage_ledger_workspace_meter_period",
        ),
    },
    "audit_log": {
        "required_columns": (
            "organization_id",
            "project_id",
            "actor_type",
            "action",
            "resource_type",
            "idempotency_key_id",
            "entry_hash",
            "created_at",
        ),
        "required_indexes": ("idx_audit_log_scope_created", "idx_audit_log_resource"),
    },
    "jobs": {
        "required_columns": (
            "organization_id",
            "project_id",
            "job_type",
            "status",
            "priority",
            "dedupe_key",
            "run_after",
            "attempts",
            "max_attempts",
            "payload",
            "created_at",
            "updated_at",
        ),
        "required_indexes": ("idx_jobs_ready_queue", "idx_jobs_project_status"),
    },
}


@dataclass(frozen=True, slots=True)
class MigrationStep:
    """One deterministic DB migration operation derived from data_model.TABLES."""

    name: str
    kind: str
    sql: str
    table: str


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """Dialect-specific migration plan plus validation metadata."""

    schema_version: str
    dialect: str
    steps: tuple[MigrationStep, ...]
    tenant_index_violations: tuple[str, ...]
    checksum: str

    @property
    def is_valid(self) -> bool:
        return not self.tenant_index_violations

    def sql_script(self) -> str:
        return "\n".join(step.sql for step in self.steps) + ("\n" if self.steps else "")

    def ledger_sql_script(self, *, ledger_table: str = SCHEMA_LEDGER_TABLE) -> str:
        """Return DDL/DML that records this plan in a schema-version ledger."""

        return "\n".join(
            (
                _create_ledger_table_sql(ledger_table, self.dialect),
                _upsert_ledger_sql(ledger_table, self.dialect, self.schema_version, self.checksum),
            )
        ) + "\n"

    def rollback_sql_script(self, *, ledger_table: str = SCHEMA_LEDGER_TABLE) -> str:
        """Return best-effort rollback DDL for an unapplied or empty deployment."""

        statements = [
            f"DELETE FROM {_quote_identifier(ledger_table)} WHERE schema_version = {_quote_literal(self.schema_version)};"
        ]
        for step in reversed(self.steps):
            if step.kind == "create_index":
                statements.append(f"DROP INDEX IF EXISTS {_quote_identifier(step.name.removeprefix('create_index_'))};")
            elif step.kind == "create_table":
                suffix = " CASCADE" if self.dialect == "postgres" else ""
                statements.append(f"DROP TABLE IF EXISTS {_quote_identifier(step.table)}{suffix};")
        return "\n".join(statements) + "\n"

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dialect": self.dialect,
            "checksum": self.checksum,
            "valid": self.is_valid,
            "tenant_index_violations": list(self.tenant_index_violations),
            "steps": [
                {"name": step.name, "kind": step.kind, "table": step.table, "sql": step.sql}
                for step in self.steps
            ],
        }


@dataclass(frozen=True, slots=True)
class SchemaVersionLedgerEntry:
    """Expected or observed schema ledger row."""

    schema_version: str
    checksum: str
    dialect: str = ""

    def to_manifest(self) -> dict[str, str]:
        payload = {"schema_version": self.schema_version, "checksum": self.checksum}
        if self.dialect:
            payload["dialect"] = self.dialect
        return payload


@dataclass(frozen=True, slots=True)
class DriftReport:
    """Schema drift validation result."""

    expected_version: str
    expected_checksum: str
    observed_version: str | None
    observed_checksum: str | None
    issues: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def to_manifest(self) -> dict[str, object]:
        return {
            "valid": self.is_valid,
            "expected_version": self.expected_version,
            "expected_checksum": self.expected_checksum,
            "observed_version": self.observed_version,
            "observed_checksum": self.observed_checksum,
            "issues": list(self.issues),
        }


@dataclass(frozen=True, slots=True)
class SqliteIntrospection:
    """Minimal sqlite_schema snapshot used by tests and adapters."""

    table_names: tuple[str, ...]
    index_names: tuple[str, ...]

    def to_manifest(self) -> dict[str, list[str]]:
        return {"table_names": list(self.table_names), "index_names": list(self.index_names)}


def generate_migration_plan(tables: Sequence[Table] = TABLES, *, dialect: str = "sqlite") -> MigrationPlan:
    """Build a deterministic migration plan from the canonical data model.

    The existing data_model export remains SQL-ish documentation. This helper is the
    next layer down: it translates the same Table/Index objects into concrete DDL for
    sqlite smoke tests and Postgres-compatible production planning.
    """

    if dialect not in SUPPORTED_DIALECTS:
        raise ValueError(f"unsupported dialect: {dialect!r}")

    steps: list[MigrationStep] = []
    for table in tables:
        create_table_sql = _create_table_sqlite(table) if dialect == "sqlite" else _create_table_postgres(table)
        steps.append(
            MigrationStep(
                name=f"create_table_{table.name}",
                kind="create_table",
                table=table.name,
                sql=create_table_sql,
            )
        )
        for index in table.indexes:
            create_index_sql = _create_index_sqlite(table, index) if dialect == "sqlite" else _create_index_postgres(table, index)
            steps.append(
                MigrationStep(
                    name=f"create_index_{index.name}",
                    kind="create_index",
                    table=table.name,
                    sql=create_index_sql,
                )
            )
    steps_tuple = tuple(steps)
    return MigrationPlan(
        schema_version=DATA_MODEL_SCHEMA_VERSION,
        dialect=dialect,
        steps=steps_tuple,
        tenant_index_violations=tuple(validate_tenant_indexes(tables)),
        checksum=_schema_checksum(tables, dialect, steps_tuple),
    )


def build_ledger_entry(plan: MigrationPlan | None = None) -> SchemaVersionLedgerEntry:
    plan = plan or generate_migration_plan()
    return SchemaVersionLedgerEntry(schema_version=plan.schema_version, checksum=plan.checksum, dialect=plan.dialect)


def build_go_postgres_vertical_slice_manifest() -> dict[str, object]:
    """Return the schema contract the Go/Postgres worker path must preserve.

    This is intentionally static and dependency-free so CI can validate the backend
    persistence shape without needing a Docker daemon or a live Postgres service.
    """

    return {
        "dialect": "postgres",
        "tables": sorted(GO_POSTGRES_VERTICAL_SLICE_TABLES),
        "functions": sorted(GO_POSTGRES_VERTICAL_SLICE_FUNCTIONS),
        "contract": {
            table: {
                "required_columns": list(details["required_columns"]),
                "required_indexes": list(details["required_indexes"]),
            }
            for table, details in sorted(GO_POSTGRES_VERTICAL_SLICE_CONTRACT.items())
        },
    }


def validate_schema_ledger(
    observed: Mapping[str, object] | SchemaVersionLedgerEntry | None,
    plan: MigrationPlan | None = None,
) -> DriftReport:
    """Validate an observed ledger row against the expected schema version/checksum."""

    plan = plan or generate_migration_plan()
    observed_version: str | None = None
    observed_checksum: str | None = None
    if isinstance(observed, SchemaVersionLedgerEntry):
        observed_version = observed.schema_version
        observed_checksum = observed.checksum
    elif observed is not None:
        version_value = observed.get("schema_version")
        checksum_value = observed.get("checksum")
        observed_version = str(version_value) if version_value is not None else None
        observed_checksum = str(checksum_value) if checksum_value is not None else None

    issues: list[str] = []
    if observed_version is None:
        issues.append("missing schema_version ledger row")
    elif observed_version != plan.schema_version:
        issues.append(f"schema_version mismatch: expected {plan.schema_version}, observed {observed_version}")
    if observed_checksum is None:
        issues.append("missing schema checksum")
    elif observed_checksum != plan.checksum:
        issues.append(f"schema checksum mismatch: expected {plan.checksum}, observed {observed_checksum}")
    return DriftReport(
        expected_version=plan.schema_version,
        expected_checksum=plan.checksum,
        observed_version=observed_version,
        observed_checksum=observed_checksum,
        issues=tuple(issues),
    )


def validate_sqlite_drift(connection: sqlite3.Connection, plan: MigrationPlan | None = None) -> DriftReport:
    """Validate a sqlite schema ledger row against the expected plan checksum."""

    plan = plan or generate_migration_plan(dialect="sqlite")
    try:
        row = connection.execute(
            f"SELECT schema_version, checksum FROM {_quote_identifier(SCHEMA_LEDGER_TABLE)} "
            "WHERE schema_version = ? ORDER BY applied_at DESC LIMIT 1",
            (plan.schema_version,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    observed = None if row is None else {"schema_version": row[0], "checksum": row[1]}
    return validate_schema_ledger(observed, plan)


def validate_tenant_indexes(tables: Sequence[Table] = TABLES, *, tenant_column: str = TENANT_SCOPE_COLUMN) -> list[str]:
    """Validate tenant isolation assumptions for tables, PKs, and secondary indexes."""

    violations: list[str] = []
    seen_indexes: set[str] = set()
    for table in tables:
        column_names = {column.name for column in table.columns}
        if tenant_column not in column_names:
            violations.append(f"{table.name}: missing {tenant_column} column")
        if not table.primary_key:
            violations.append(f"{table.name}: missing primary key")
        elif table.primary_key[0] != tenant_column:
            violations.append(f"{table.name}: primary key must start with {tenant_column}")
        for primary_key_column in table.primary_key:
            if primary_key_column not in column_names:
                violations.append(f"{table.name}: primary key references unknown column {primary_key_column}")
        for index in table.indexes:
            if index.name in seen_indexes:
                violations.append(f"{table.name}.{index.name}: duplicate index name")
            seen_indexes.add(index.name)
            if index.tenant_scoped and (not index.columns or index.columns[0] != tenant_column):
                violations.append(f"{table.name}.{index.name}: tenant-scoped index must start with {tenant_column}")
            for index_column in index.columns:
                if index_column not in column_names:
                    violations.append(f"{table.name}.{index.name}: index references unknown column {index_column}")
    return violations


def apply_migration_plan(
    plan: MigrationPlan | None = None,
    connection: sqlite3.Connection | None = None,
    *,
    fail_on_tenant_index_violations: bool = True,
    record_ledger: bool = False,
) -> sqlite3.Connection:
    """Apply a sqlite plan and return the connection.

    Passing no connection creates an in-memory database. The function intentionally
    reads no environment variables and depends only on Python's standard sqlite3.
    """

    plan = plan or generate_migration_plan()
    if plan.dialect != "sqlite":
        raise ValueError(f"apply_migration_plan only executes sqlite plans, got {plan.dialect!r}")
    if fail_on_tenant_index_violations and plan.tenant_index_violations:
        joined = "; ".join(plan.tenant_index_violations)
        raise ValueError(f"tenant index validation failed: {joined}")
    connection = connection or sqlite3.connect(":memory:")
    with connection:
        for step in plan.steps:
            connection.execute(step.sql)
        if record_ledger:
            connection.executescript(plan.ledger_sql_script())
    return connection


def apply_to_memory_and_introspect(plan: MigrationPlan | None = None) -> SqliteIntrospection:
    """Apply the generated plan to an in-memory sqlite DB and return table/index names."""

    connection = apply_migration_plan(plan, sqlite3.connect(":memory:"))
    try:
        return introspect_sqlite(connection)
    finally:
        connection.close()


def introspect_sqlite(connection: sqlite3.Connection) -> SqliteIntrospection:
    table_names = _sqlite_schema_names(connection, "table")
    index_names = _sqlite_schema_names(connection, "index")
    return SqliteIntrospection(table_names=table_names, index_names=index_names)


def _sqlite_schema_names(connection: sqlite3.Connection, schema_type: str) -> tuple[str, ...]:
    rows = connection.execute(
        "SELECT name FROM sqlite_schema WHERE type = ? AND name NOT LIKE 'sqlite_%' ORDER BY name",
        (schema_type,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _create_table_sqlite(table: Table) -> str:
    rendered: list[str] = []
    for column in table.columns:
        bits = [f"  {_quote_identifier(column.name)}", _sqlite_type(column.type)]
        if column.required:
            bits.append("NOT NULL")
        if column.default is not None:
            bits.append(f"DEFAULT {_sqlite_default(column.default)}")
        rendered.append(" ".join(bits))
    rendered.append(f"  PRIMARY KEY ({', '.join(_quote_identifier(column) for column in table.primary_key)})")
    body = ",\n".join(rendered)
    return f"CREATE TABLE IF NOT EXISTS {_quote_identifier(table.name)} (\n{body}\n);"


def _create_index_sqlite(table: Table, index: Index) -> str:
    unique = "UNIQUE " if index.unique else ""
    columns = ", ".join(_quote_identifier(column) for column in index.columns)
    where = f" WHERE {index.where}" if index.where else ""
    return (
        f"CREATE {unique}INDEX IF NOT EXISTS {_quote_identifier(index.name)} "
        f"ON {_quote_identifier(table.name)} ({columns}){where};"
    )


def _create_table_postgres(table: Table) -> str:
    rendered: list[str] = []
    for column in table.columns:
        bits = [f"  {_quote_identifier(column.name)}", _postgres_type(column.type)]
        if column.required:
            bits.append("NOT NULL")
        if column.default is not None:
            bits.append(f"DEFAULT {_postgres_default(column.default, column.type)}")
        rendered.append(" ".join(bits))
    rendered.append(f"  PRIMARY KEY ({', '.join(_quote_identifier(column) for column in table.primary_key)})")
    body = ",\n".join(rendered)
    return f"CREATE TABLE IF NOT EXISTS {_quote_identifier(table.name)} (\n{body}\n);"


def _create_index_postgres(table: Table, index: Index) -> str:
    unique = "UNIQUE " if index.unique else ""
    columns = ", ".join(_quote_identifier(column) for column in index.columns)
    where = f" WHERE {index.where}" if index.where else ""
    return (
        f"CREATE {unique}INDEX IF NOT EXISTS {_quote_identifier(index.name)} "
        f"ON {_quote_identifier(table.name)} ({columns}){where};"
    )


def _sqlite_type(type_name: str) -> str:
    return {
        "uuid": "TEXT",
        "text": "TEXT",
        "timestamp": "TEXT",
        "date": "TEXT",
        "json": "TEXT",
        "decimal": "NUMERIC",
        "integer": "INTEGER",
        "boolean": "INTEGER",
    }.get(type_name, "TEXT")


def _postgres_type(type_name: str) -> str:
    return {
        "uuid": "UUID",
        "text": "TEXT",
        "timestamp": "TIMESTAMPTZ",
        "date": "DATE",
        "json": "JSONB",
        "decimal": "NUMERIC",
        "integer": "INTEGER",
        "boolean": "BOOLEAN",
    }.get(type_name, "TEXT")


def _sqlite_default(default: str) -> str:
    if default == "now()":
        return "CURRENT_TIMESTAMP"
    if default in {"{}", "[]"}:
        return _quote_literal(default)
    if default.isdigit() or (default.startswith("-") and default[1:].isdigit()):
        return default
    upper = default.upper()
    if upper in {"CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME", "NULL", "TRUE", "FALSE"}:
        return upper
    if default.startswith("'") and default.endswith("'"):
        return default
    return _quote_literal(default)


def _postgres_default(default: str, type_name: str) -> str:
    if default == "now()":
        return "CURRENT_TIMESTAMP"
    if type_name == "json" and default in {"{}", "[]"}:
        return f"{_quote_literal(default)}::jsonb"
    if default.isdigit() or (default.startswith("-") and default[1:].isdigit()):
        return default
    upper = default.upper()
    if upper in {"CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME", "NULL", "TRUE", "FALSE"}:
        return upper
    if default.startswith("'") and default.endswith("'"):
        return default
    return _quote_literal(default)


def _create_ledger_table_sql(ledger_table: str, dialect: str) -> str:
    if dialect not in SUPPORTED_DIALECTS:
        raise ValueError(f"unsupported dialect: {dialect!r}")
    timestamp_type = "TEXT" if dialect == "sqlite" else "TIMESTAMPTZ"
    return (
        f"CREATE TABLE IF NOT EXISTS {_quote_identifier(ledger_table)} (\n"
        "  schema_version TEXT PRIMARY KEY,\n"
        "  checksum TEXT NOT NULL,\n"
        f"  applied_at {timestamp_type} NOT NULL DEFAULT CURRENT_TIMESTAMP\n"
        ");"
    )


def _upsert_ledger_sql(ledger_table: str, dialect: str, schema_version: str, checksum: str) -> str:
    if dialect == "sqlite":
        return (
            f"INSERT INTO {_quote_identifier(ledger_table)} (schema_version, checksum, applied_at) "
            f"VALUES ({_quote_literal(schema_version)}, {_quote_literal(checksum)}, CURRENT_TIMESTAMP) "
            "ON CONFLICT(schema_version) DO UPDATE SET "
            "checksum = excluded.checksum, applied_at = excluded.applied_at;"
        )
    if dialect == "postgres":
        return (
            f"INSERT INTO {_quote_identifier(ledger_table)} (schema_version, checksum, applied_at) "
            f"VALUES ({_quote_literal(schema_version)}, {_quote_literal(checksum)}, CURRENT_TIMESTAMP) "
            "ON CONFLICT (schema_version) DO UPDATE SET "
            "checksum = EXCLUDED.checksum, applied_at = EXCLUDED.applied_at;"
        )
    raise ValueError(f"unsupported dialect: {dialect!r}")


def _schema_checksum(tables: Sequence[Table], dialect: str, steps: Sequence[MigrationStep]) -> str:
    payload = {
        "schema_version": DATA_MODEL_SCHEMA_VERSION,
        "dialect": dialect,
        "tables": [
            {
                "name": table.name,
                "columns": [
                    {
                        "name": column.name,
                        "type": column.type,
                        "required": column.required,
                        "default": column.default,
                        "ref": column.ref,
                        "enum": list(column.enum),
                    }
                    for column in table.columns
                ],
                "primary_key": list(table.primary_key),
                "indexes": [index.to_manifest(table.name) for index in table.indexes],
            }
            for table in tables
        ],
        "steps": [{"name": step.name, "kind": step.kind, "table": step.table, "sql": step.sql} for step in steps],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ValueError(f"invalid identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
