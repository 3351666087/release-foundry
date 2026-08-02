import json
import unittest

import jsonschema

from scripts.a2_ollama_multimodal_matrix import ROOT


class Round39EvidenceSchemaTests(unittest.TestCase):
    def validate(self, schema_name, evidence_name):
        schema = json.loads(
            (ROOT / "docs/a2/schemas" / schema_name).read_text(encoding="utf-8")
        )
        evidence = json.loads(
            (ROOT / "docs/evidence" / evidence_name).read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(evidence)

    def test_round38_miss_diagnosis_has_exact_schema(self):
        self.validate(
            "multimodal_miss_diagnosis.schema.json",
            "a2_multimodal_miss_diagnosis_round38.json",
        )

    def test_round38_postgresql_qualification_has_exact_schema(self):
        self.validate(
            "postgresql_persistence_qualification.schema.json",
            "a2_postgresql_persistence_qualification_round38.json",
        )


if __name__ == "__main__":
    unittest.main()
