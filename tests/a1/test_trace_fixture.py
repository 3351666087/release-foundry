import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sdk"))
sys.path.insert(0, str(ROOT))

from ashr_clone import TraceEvent, build_run_fixture, trace_events_from_vm_stream  # noqa: E402
from ashr_clone.trace import RUN_FIXTURE_SCHEMA, build_vm_stream, load_run_fixture, replay_observations, validate_run_fixture  # noqa: E402
from examples.agents.mock_agent import MockAgent, build_default_fixtures  # noqa: E402


class TraceFixtureTests(unittest.TestCase):
    def test_mock_agent_generates_three_a3_consumable_fixtures(self):
        fixtures = [MockAgent().run(name) for name in ("echo_success", "tool_math_success", "recoverable_error")]
        self.assertEqual(len(fixtures), 3)
        for fixture in fixtures:
            self.assertEqual(fixture["schema"], RUN_FIXTURE_SCHEMA)
            self.assertIn("a3", fixture["labels"])
            self.assertTrue(validate_run_fixture(fixture))
            self.assertEqual(len(fixture["events"]), len(fixture["vm_stream"]))

    def test_committed_a3_fixtures_are_loadable(self):
        fixture_paths = sorted((ROOT / "examples" / "agents" / "fixtures").glob("*.json"))
        self.assertGreaterEqual(len(fixture_paths), 3)
        for path in fixture_paths:
            fixture = load_run_fixture(path)
            self.assertIn("a3", fixture["labels"])
            self.assertTrue(fixture["events"])
            self.assertEqual(len(fixture["events"]), len(fixture["vm_stream"]))

    def test_replay_roundtrip_preserves_observation_count(self):
        fixture = MockAgent().run("tool_math_success")
        self.assertEqual(len(list(replay_observations(fixture["events"]))), len(fixture["events"]))
        self.assertEqual(build_vm_stream(fixture["events"]), fixture["vm_stream"])

    def test_top_level_sdk_exports_a3_fixture_helpers(self):
        fixture = MockAgent().run("echo_success")
        events = trace_events_from_vm_stream(fixture["run"]["run_id"], fixture["vm_stream"])
        rebuilt = build_run_fixture("rebuilt", "A3 import check", events, labels=("a3",))
        self.assertIsInstance(events[0], TraceEvent)
        self.assertTrue(validate_run_fixture(rebuilt))

    def test_fixture_cli_writes_and_replays_json(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            paths = build_default_fixtures(Path(raw_tmp))
            fixture = load_run_fixture(paths[0])
            completed = subprocess.run([sys.executable, "-B", str(ROOT / "examples" / "agents" / "mock_agent.py"), "--replay", str(paths[0])], cwd=str(ROOT), text=True, capture_output=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["observations"], len(fixture["events"]))


if __name__ == "__main__":
    unittest.main()
