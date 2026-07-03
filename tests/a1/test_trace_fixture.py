import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sdk"))
sys.path.insert(0, str(ROOT))

from ashr_clone.trace import RUN_FIXTURE_SCHEMA, build_vm_stream, load_run_fixture, replay_observations, validate_run_fixture  # noqa: E402
from examples.agents.mock_agent import MockAgent, build_default_fixtures  # noqa: E402


class TraceFixtureTests(unittest.TestCase):
    def test_mock_agent_generates_three_a3_consumable_fixtures(self):
        fixtures = [MockAgent().run(name) for name in ("echo_success", "tool_math_success", "recoverable_error")]
        self.assertEqual(len(fixtures), 3)
        for fixture in fixtures:
            self.assertEqual(fixture["schema"], RUN_FIXTURE_SCHEMA)
            self.assertTrue(validate_run_fixture(fixture))
            self.assertEqual(len(fixture["events"]), len(fixture["vm_stream"]))

    def test_replay_roundtrip_preserves_observation_count(self):
        fixture = MockAgent().run("tool_math_success")
        self.assertEqual(len(list(replay_observations(fixture["events"]))), len(fixture["events"]))
        self.assertEqual(build_vm_stream(fixture["events"]), fixture["vm_stream"])

    def test_fixture_cli_writes_and_replays_json(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            paths = build_default_fixtures(Path(raw_tmp))
            fixture = load_run_fixture(paths[0])
            completed = subprocess.run([sys.executable, str(ROOT / "examples" / "agents" / "mock_agent.py"), "--replay", str(paths[0])], cwd=str(ROOT), text=True, capture_output=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["observations"], len(fixture["events"]))


if __name__ == "__main__":
    unittest.main()
