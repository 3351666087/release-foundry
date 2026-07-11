import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = ROOT / "docs/strategy"
STRATEGY = STRATEGY_DIR / "large-saas-a1-a2-a3-full-plan.md"


class UnifiedReleaseStrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = STRATEGY.read_text(encoding="utf-8")
        cls.normalized_text = " ".join(cls.text.split())

    def test_strategy_directory_has_one_authoritative_document(self):
        self.assertEqual(
            [path.name for path in STRATEGY_DIR.glob("*.md")],
            [STRATEGY.name],
        )

    def test_strategy_defines_all_three_release_lanes(self):
        required = [
            "A1：执行、平台与企业基础设施",
            "A2：独立评测、学习与发布智能",
            "A3：产品控制台、审核与商业工作流",
            "Evidence Snapshot",
            "Decision Ledger",
            "Provider",
            "Release Gate",
        ]
        for anchor in required:
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, self.text)

    def test_strategy_locks_cross_lane_authority(self):
        required = [
            "A1 运行成功不等于 A2 评测成功",
            "A2 是评测语义和 Release Decision 的权威",
            "A3 只能展示或请求 A2 决策，不能自行重算分数",
            "没有有效 Decision Ledger 记录，不得显示 Release Ready",
            "人工 Override 必须追加新记录，不能删除机器原始决策",
        ]
        for invariant in required:
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, self.normalized_text)

    def test_strategy_is_fail_closed_and_provider_independent(self):
        required = [
            "Ashr 官方 API 降级为**可选校准 Provider**",
            "Ollama",
            "vLLM",
            "OpenAI-compatible",
            "完全离线",
            "Provider 超时、限流、额度耗尽、付款状态异常都不能产生“通过”",
        ]
        for invariant in required:
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, self.text)

    def test_strategy_covers_enterprise_release_and_domestic_constraints(self):
        required = [
            "微信开放平台登录",
            "QQ 互联登录",
            "支付宝登录",
            "微信支付",
            "支付宝",
            "OIDC",
            "SAML",
            "Helm",
            "Terraform",
            "SBOM",
            "升级",
            "回滚",
            "备份",
            "恢复",
        ]
        for anchor in required:
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, self.text)

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
