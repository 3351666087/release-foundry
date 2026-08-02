import json
import sqlite3
import unittest
from pathlib import Path

import jsonschema

from services.judge.extractor_qualification_store import (
    QualificationStoreConflict,
    initialize_qualification_store,
    load_qualification_registry,
    persist_qualification,
    revoke_qualification,
)
from services.judge.extractor_registry import ExtractorQualificationError
from tests.a2.test_extractor_registry import deployment, qualification_record

TRUST = {"a2.qualification-authority": frozenset({"extractor-promotion"})}
QUALITY = {"minimum_precision": 1.0, "minimum_recall": 1.0, "minimum_content_coverage": 1.0}


class ExtractorQualificationStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        initialize_qualification_store(self.db)

    def tearDown(self):
        self.db.close()

    def test_record_survives_restart_and_snapshot_is_public_safe(self):
        saved = persist_qualification(self.db, qualification_record(), trusted_issuers=TRUST, expected_generation=0, created_at="2026-07-12T00:00:00Z")
        self.assertEqual(saved["generation"], 1)
        registry, snapshot = load_qualification_registry(self.db, trusted_issuers=TRUST)
        qualified = registry.qualify(deployment(), media_type="application/pdf", language="en", observed_quality=QUALITY, now="2026-07-12T00:00:00Z")
        self.assertEqual(qualified.record_id, saved["record_id"])
        self.assertEqual(snapshot["generation"], 1)
        self.assertTrue(snapshot["snapshot_hash"].startswith("sha256:"))
        self.assertFalse(snapshot["raw_records_included"])

    def test_revocation_survives_restart_and_stale_writer_is_fenced(self):
        record = qualification_record()
        persist_qualification(self.db, record, trusted_issuers=TRUST, expected_generation=0, created_at="2026-07-12T00:00:00Z")
        with self.assertRaises(QualificationStoreConflict):
            revoke_qualification(self.db, record_id=record["record_id"], reason_code="incident", expected_generation=0, revoked_at="2026-07-12T01:00:00Z")
        revoked = revoke_qualification(self.db, record_id=record["record_id"], reason_code="incident", expected_generation=1, revoked_at="2026-07-12T01:00:00Z")
        self.assertEqual(revoked["generation"], 2)
        registry, snapshot = load_qualification_registry(self.db, trusted_issuers=TRUST)
        self.assertEqual(snapshot["revocation_count"], 1)
        with self.assertRaises(ExtractorQualificationError) as caught:
            registry.qualify(deployment(), media_type="application/pdf", language="en", observed_quality=QUALITY, now="2026-07-12T02:00:00Z")
        self.assertIn("qualification_revoked", caught.exception.blockers)

    def test_conflicting_immutable_record_cannot_replace_version(self):
        record = qualification_record()
        persist_qualification(self.db, record, trusted_issuers=TRUST, expected_generation=0, created_at="2026-07-12T00:00:00Z")
        changed = qualification_record()
        changed["record_id"] = "qual.pdf-text.4.2.1.changed"
        changed["record_hash"] = "sha256:" + "b" * 64
        with self.assertRaises(ValueError):
            persist_qualification(self.db, changed, trusted_issuers=TRUST, expected_generation=1, created_at="2026-07-12T00:01:00Z")

    def test_same_extractor_version_with_different_record_id_is_rejected(self):
        record = qualification_record()
        persist_qualification(self.db, record, trusted_issuers=TRUST, expected_generation=0, created_at="2026-07-12T00:00:00Z")
        changed = qualification_record()
        changed["record_id"] = "qual.pdf-text.4.2.1.alias"
        from services.judge.extractor_registry import qualification_record_hash
        changed["record_hash"] = qualification_record_hash(changed)
        with self.assertRaisesRegex(QualificationStoreConflict, "extractor_version_record_conflict"):
            persist_qualification(self.db, changed, trusted_issuers=TRUST, expected_generation=1, created_at="2026-07-12T00:01:00Z")

    def test_database_payload_tamper_fails_closed_on_reload(self):
        record = qualification_record()
        persist_qualification(self.db, record, trusted_issuers=TRUST, expected_generation=0, created_at="2026-07-12T00:00:00Z")
        payload = json.loads(self.db.execute("SELECT record_json FROM a2_extractor_qualifications").fetchone()[0])
        payload["extractor"]["version"] = "9.9.9"
        self.db.execute("UPDATE a2_extractor_qualifications SET record_json=?", (json.dumps(payload),))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "stored_record_hash_mismatch"):
            load_qualification_registry(self.db, trusted_issuers=TRUST)

    def test_trusted_issuer_rotation_config_is_schema_valid(self):
        config = {
            "schema_version": "a2.extractor_trusted_issuers.v1",
            "config_id": "a2.extractor-trust.production",
            "generation": 2,
            "valid_from": "2026-07-12T00:00:00Z",
            "issuers": [{"id": "a2.qualification-authority", "authorities": ["extractor-promotion"]}],
        }
        schema = json.loads((Path(__file__).parents[2] / "docs/a2/schemas/extractor_trusted_issuers.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(config)
        rotated = {**config, "generation": 3, "issuers": [{"id": "a2.next-authority", "authorities": ["extractor-promotion"]}]}
        jsonschema.Draft202012Validator(schema).validate(rotated)
        persist_qualification(self.db, qualification_record(), trusted_issuers=TRUST, expected_generation=0, created_at="2026-07-12T00:00:00Z")
        with self.assertRaises(ExtractorQualificationError):
            load_qualification_registry(self.db, trusted_issuers={"a2.next-authority": frozenset({"extractor-promotion"})})


if __name__ == "__main__":
    unittest.main()
