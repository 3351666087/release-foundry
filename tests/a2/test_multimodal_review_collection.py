import unittest

import jsonschema

from scripts.a2_verify_multimodal_review_conservation import (
    validate_review_collection,
)


class MultimodalReviewCollectionTests(unittest.TestCase):
    def test_pending_collection_must_be_empty(self):
        collection = {
            "schema_version": "a2.multimodal_real_review_collection.v1",
            "collection_state": "pending",
            "receipts": [],
            "note": "No verified reviewer was available in this round.",
            "release_authority": False,
            "public_safe": True,
        }
        validate_review_collection(collection)
        collection["receipts"] = [{}]
        with self.assertRaises(jsonschema.ValidationError):
            validate_review_collection(collection)

    def test_reviewed_collection_requires_receipt(self):
        collection = {
            "schema_version": "a2.multimodal_real_review_collection.v1",
            "collection_state": "reviewed",
            "receipts": [],
            "note": "Reviewed collection.",
            "release_authority": False,
            "public_safe": True,
        }
        with self.assertRaises(jsonschema.ValidationError):
            validate_review_collection(collection)


if __name__ == "__main__":
    unittest.main()
