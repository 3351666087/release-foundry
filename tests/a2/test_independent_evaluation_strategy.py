import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STRATEGY = ROOT / "docs/strategy/a2-independent-evaluation-intelligence-platform.md"


class A2IndependentEvaluationStrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = STRATEGY.read_text(encoding="utf-8")
        cls.normalized_text = " ".join(cls.text.split())

    def test_strategy_defines_commercial_control_plane(self):
        required = [
            "A2_INDEPENDENT_EVALUATION_INTELLIGENCE_PLATFORM",
            "Evidence Snapshot",
            "Decision Ledger",
            "Provider Control Plane",
            "Multi-Judge Governance",
            "Multimodal Security",
            "Dataset And Label Governance",
            "Commercial Acceptance Metrics",
        ]
        for anchor in required:
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, self.text)

    def test_strategy_locks_cross_lane_authority(self):
        required = [
            "A1 produces trusted execution facts",
            "A2 converts those facts into versioned",
            "A3 turns those decisions into review",
            "A3 must not recompute A2 grade or release decision",
            "A1 runtime success does not equal evaluation success",
        ]
        for invariant in required:
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, self.normalized_text)

    def test_strategy_is_fail_closed_and_provider_independent(self):
        required = [
            "Ashr API is optional",
            "evidence_missing",
            "Provider failure must not become pass",
            "`abstain`",
            "No Decision Ledger record means no release-ready state",
            "Human override preserves the original machine decision",
        ]
        for invariant in required:
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, self.text)

    def test_strategy_covers_all_modalities_and_non_goals(self):
        for modality in ("`text`", "`image`", "`audio`", "`file`", "`video`"):
            with self.subTest(modality=modality):
                self.assertIn(modality, self.text)
        self.assertIn("does not currently claim reinforcement learning or RLHF", self.text)
        self.assertIn("not a Dify-style general workflow builder", self.text)

    def test_strategy_contains_no_credentials_or_private_evidence_paths(self):
        forbidden = [
            re.compile(r"tp_[A-Za-z0-9_-]{12,}"),
            re.compile(r"ashr_live_[A-Za-z0-9_-]+"),
            re.compile(r"sk-[A-Za-z0-9]{12,}"),
            re.compile(r"Bearer\s+[A-Za-z0-9._-]+"),
            re.compile(r"docs[\\/]+evidence[\\/]+private_refs", re.IGNORECASE),
        ]
        for pattern in forbidden:
            with self.subTest(pattern=pattern.pattern):
                self.assertIsNone(pattern.search(self.text))


if __name__ == "__main__":
    unittest.main()
