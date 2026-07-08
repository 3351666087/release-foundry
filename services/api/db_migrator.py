from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, Sequence

from services.api.data_model import DATA_MODEL_SCHEMA_VERSION, Index, TABLES, Table

TENANT_SCOPE_COLUMN = "tenant_id"


@dataclass(frozen=True, slots=True)
class MigrationStep:
    """One deterministic DB migration operation derived from data_model.TABLES."""

    name: str
    kind: str
    sql: str
    table: str


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """SQLite-applicable migration plan plus validation metadata."""

    schema_version: str
    dialect: str
    steps: tuple[MigrationStep, ...]
    tenant_index_violations: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.tenant_index_violations

    def sql_script(self) -> str:
        return "\n".join(step.sql for step in self.steps) + ("\n" if self.steps else "")

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dialect": self.dialect,
            "valid": self.is_valid,
            "tenant_index_violations": list(self.tenant_index_violations),
            "steps": [
                {"name": step.name, "kind": step.kind, "table": step.table, "sql": step.sql}
                for step in self.steps
            ],
        }


@dataclass(frozen=True, slots=True)
class SqliteIntrospection:
    """Minimal sqlite_schema snapshot used by tests and adapters."""

    table_names: tuple[str, ...]
    index_names: tuple[str, ...]

    def to_manifest(self) -> dict[str, list[str]]:
        return {"table_names": list(self.table_names), "index_names": list(self.index_names)}


def generate_migration_plan(tables: Sequence[Table] = TABLES, *, dialect: str = "sqlite") -> MigrationPlan:
    """Build a deterministic SQLite migration plan from the canonical data model.

    The existing data_model export remains SQL-ish documentation. This helper is the
    next layer down: it translates the same Table/Index objects into standard-library
    sqlite3-compatible DDL that can be validated and applied in memory.
    """

    if dialect != "sqlite":
        raise ValueError(f"unsupported dialect: {dialect!r}")

    steps: list[MigrationStep] = []
    for table in tables:
        steps.append(
            MigrationStep(
                name=f"create_table_{table.name}",
                kind="create_table",
                table=table.name,
                sql=_create_table_sqlite(table),
            )
        )
        for index in table.indexes:
            steps.append(
                MigrationStep(
                    name=f"create_index_{index.name}",
                    kind="create_index",
                    table=table.name,
                    sql=_create_index_sqlite(table, index),
                )
            )
    return MigrationPlan(
        schema_version=DATA_MODEL_SCHEMA_VERSION,
        dialect=dialect,
        steps=tuple(steps),
        tenant_index_violations=tuple(validate_tenant_indexes(tables)),
    )


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
) -> sqlite3.Connection:
    """Apply a plan to sqlite and return the connection.

    Passing no connection creates an in-memory database. The function intentionally
    reads no environment variables and depends only on Python's standard sqlite3.
    """

    plan = plan or generate_migration_plan()
    if fail_on_tenant_index_violations and plan.tenant_index_violations:
        joined = "; ".join(plan.tenant_index_violations)
        raise ValueError(f"tenant index validation failed: {joined}")
    connection = connection or sqlite3.connect(":memory:")
    with connection:
        for step in plan.steps:
            connection.execute(step.sql)
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


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ValueError(f"invalid sqlite identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
