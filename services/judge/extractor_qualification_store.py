"""Durable, fenced persistence for A2 extractor qualifications."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

from .extractor_registry import (
    ExtractorQualificationRegistry,
    qualification_record_hash,
    validate_qualification_record,
)
from .result_persistence import stable_hash

STORE_SCHEMA_VERSION = "a2.extractor_qualification_store.v1"

DDL = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS a2_extractor_qualifications (
  record_id TEXT PRIMARY KEY,
  extractor_id TEXT NOT NULL,
  extractor_version TEXT NOT NULL,
  record_hash TEXT NOT NULL,
  record_json TEXT NOT NULL,
  generation INTEGER NOT NULL CHECK (generation > 0),
  created_at TEXT NOT NULL,
  UNIQUE(extractor_id, extractor_version)
);
CREATE TABLE IF NOT EXISTS a2_extractor_revocations (
  record_id TEXT PRIMARY KEY REFERENCES a2_extractor_qualifications(record_id),
  reason_code TEXT NOT NULL,
  generation INTEGER NOT NULL CHECK (generation > 0),
  revoked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS a2_extractor_registry_state (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  generation INTEGER NOT NULL CHECK (generation >= 0),
  updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO a2_extractor_registry_state(singleton, generation, updated_at)
VALUES (1, 0, '1970-01-01T00:00:00Z');
"""


class QualificationStoreConflict(ValueError):
    """A stale writer or conflicting immutable record was rejected."""


def initialize_qualification_store(connection: sqlite3.Connection) -> None:
    connection.executescript(DDL)
    connection.commit()


def persist_qualification(
    connection: sqlite3.Connection,
    record: Mapping[str, Any],
    *,
    trusted_issuers: Mapping[str, set[str] | frozenset[str]],
    expected_generation: int,
    created_at: str,
) -> dict[str, Any]:
    blockers = validate_qualification_record(record, trusted_issuers=trusted_issuers)
    if blockers:
        raise ValueError(", ".join(blockers))
    if record["record_hash"] != qualification_record_hash(record):
        raise ValueError("record_hash_mismatch")
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
    try:
        connection.execute("BEGIN IMMEDIATE")
        generation = _generation(connection)
        if generation != expected_generation:
            raise QualificationStoreConflict("registry_generation_conflict")
        existing = connection.execute(
            "SELECT record_id, record_hash FROM a2_extractor_qualifications WHERE extractor_id=? AND extractor_version=?",
            (record["extractor"]["id"], record["extractor"]["version"]),
        ).fetchone()
        if existing and (existing[0] != record["record_id"] or existing[1] != record["record_hash"]):
            raise QualificationStoreConflict("extractor_version_record_conflict")
        next_generation = generation + (0 if existing else 1)
        if not existing:
            connection.execute(
                "INSERT INTO a2_extractor_qualifications VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record["record_id"], record["extractor"]["id"], record["extractor"]["version"],
                 record["record_hash"], payload, next_generation, created_at),
            )
            _advance(connection, generation, next_generation, created_at)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {"record_id": existing[0] if existing else record["record_id"], "record_hash": record["record_hash"], "generation": next_generation}


def revoke_qualification(
    connection: sqlite3.Connection,
    *,
    record_id: str,
    reason_code: str,
    expected_generation: int,
    revoked_at: str,
) -> dict[str, Any]:
    try:
        connection.execute("BEGIN IMMEDIATE")
        generation = _generation(connection)
        if generation != expected_generation:
            raise QualificationStoreConflict("registry_generation_conflict")
        if connection.execute("SELECT 1 FROM a2_extractor_qualifications WHERE record_id=?", (record_id,)).fetchone() is None:
            raise KeyError("qualification record is not registered")
        existing = connection.execute("SELECT reason_code, generation FROM a2_extractor_revocations WHERE record_id=?", (record_id,)).fetchone()
        if existing:
            if existing[0] != reason_code:
                raise QualificationStoreConflict("revocation_reason_conflict")
            next_generation = generation
        else:
            next_generation = generation + 1
            connection.execute("INSERT INTO a2_extractor_revocations VALUES (?, ?, ?, ?)", (record_id, reason_code, next_generation, revoked_at))
            _advance(connection, generation, next_generation, revoked_at)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {"record_id": record_id, "status": "revoked", "generation": next_generation}


def load_qualification_registry(
    connection: sqlite3.Connection,
    *,
    trusted_issuers: Mapping[str, set[str] | frozenset[str]],
) -> tuple[ExtractorQualificationRegistry, dict[str, Any]]:
    rows = connection.execute(
        "SELECT record_id, record_hash, record_json FROM a2_extractor_qualifications ORDER BY record_id"
    ).fetchall()
    records = []
    for stored_record_id, stored_hash, payload in rows:
        record = json.loads(payload)
        if record.get("record_id") != stored_record_id:
            raise ValueError("stored_record_id_mismatch")
        if record.get("record_hash") != stored_hash or qualification_record_hash(record) != stored_hash:
            raise ValueError("stored_record_hash_mismatch")
        records.append(record)
    registry = ExtractorQualificationRegistry(records, trusted_issuers=trusted_issuers)
    revocations = connection.execute("SELECT record_id, reason_code FROM a2_extractor_revocations ORDER BY record_id").fetchall()
    for record_id, reason in revocations:
        registry.revoke(record_id, reason_code=reason)
    generation = _generation(connection)
    snapshot_hash = stable_hash({"generation": generation, "record_hashes": [r["record_hash"] for r in records], "revoked_record_ids": [r[0] for r in revocations]})
    return registry, {
        "schema_version": STORE_SCHEMA_VERSION,
        "generation": generation,
        "snapshot_hash": snapshot_hash,
        "record_count": len(records),
        "revocation_count": len(revocations),
        "raw_records_included": False,
        "secret_material_included": False,
    }


def _generation(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT generation FROM a2_extractor_registry_state WHERE singleton=1").fetchone()
    if row is None:
        raise ValueError("qualification store is not initialized")
    return int(row[0])


def _advance(connection: sqlite3.Connection, old: int, new: int, updated_at: str) -> None:
    cursor = connection.execute("UPDATE a2_extractor_registry_state SET generation=?, updated_at=? WHERE singleton=1 AND generation=?", (new, updated_at, old))
    if cursor.rowcount != 1:
        raise QualificationStoreConflict("registry_generation_conflict")
