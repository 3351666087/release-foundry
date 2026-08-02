import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sdk"))
sys.path.insert(0, str(ROOT))

from releasefoundry import AGENT_INPUT_SCHEMA_VERSION, TraceEvent, build_run_fixture, trace_events_from_vm_stream  # noqa: E402
from releasefoundry.trace import RUN_FIXTURE_SCHEMA, TRACE_SCHEMA, VM_STREAM_SCHEMA, build_vm_stream, load_run_fixture, replay_observations, validate_run_fixture  # noqa: E402
from examples.agents.mock_agent import MockAgent, build_default_fixtures  # noqa: E402
from services.api import CLOUD_API_SCHEMA_VERSION  # noqa: E402


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

    def test_schema_snapshots_are_valid_json_and_match_versions(self):
        schema_dir = ROOT / "docs" / "a1" / "schemas"
        schemas = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in schema_dir.glob("*.schema.json")}
        self.assertEqual(schemas["run_fixture.schema.json"]["properties"]["schema"]["const"], RUN_FIXTURE_SCHEMA)
        self.assertEqual(schemas["trace_event.schema.json"]["properties"]["schema"]["const"], TRACE_SCHEMA)
        self.assertEqual(schemas["vm_stream_frame.schema.json"]["properties"]["schema"]["const"], VM_STREAM_SCHEMA)
        self.assertEqual(schemas["agent_input.schema.json"]["properties"]["schema_version"]["const"], AGENT_INPUT_SCHEMA_VERSION)
        self.assertEqual(schemas["cloud_api.schema.json"]["properties"]["schema_version"]["const"], CLOUD_API_SCHEMA_VERSION)
        self.assertEqual(schemas["agent_turn.schema.json"]["properties"]["schema_version"]["const"], "releasefoundry.agent_turn.v1")
        self.assertEqual(schemas["run_result.schema.json"]["properties"]["aggregate_metrics"]["properties"]["schema_version"]["const"], "releasefoundry.run_result.v1")
        self.assertIn("case_result.schema.json", schemas)
        self.assertIn("observation.schema.json", schemas)
        self.assertIn("grade_result.schema.json", schemas)
        self.assertEqual(schemas["run_result.schema.json"]["properties"]["cases"]["items"]["$ref"], "case_result.schema.json")
        self.assertEqual(schemas["case_result.schema.json"]["properties"]["agent_output"]["$ref"], "agent_turn.schema.json")
        self.assertEqual(schemas["run_fixture.schema.json"]["properties"]["events"]["items"]["$ref"], "trace_event.schema.json")
        self.assertEqual(schemas["run_fixture.schema.json"]["properties"]["vm_stream"]["items"]["$ref"], "vm_stream_frame.schema.json")

    def test_replay_roundtrip_preserves_observation_count(self):
        fixture = MockAgent().run("tool_math_success")
        self.assertEqual(len(list(replay_observations(fixture["events"]))), len(fixture["events"]))
        self.assertEqual(build_vm_stream(fixture["events"]), fixture["vm_stream"])

    def test_validate_run_fixture_rejects_bad_vm_frames(self):
        fixture = MockAgent().run("tool_math_success")
        mutations = []
        mutations.append(lambda frame: frame.update({"schema": "bad.schema"}))
        mutations.append(lambda frame: frame.update({"stream": "unknown"}))
        mutations.append(lambda frame: frame.update({"event_id": "evt_wrong"}))
        mutations.append(lambda frame: frame.update({"seq": 0 if frame["seq"] != 0 else 1}))
        mutations.append(lambda frame: frame.update({"data": "not-a-map"}))
        mutations.append(lambda frame: frame.pop("status"))
        mutations.append(lambda frame: frame.update({"extra": True}))
        for mutate in mutations:
            broken = json.loads(json.dumps(fixture))
            mutate(broken["vm_stream"][1])
            with self.assertRaises(ValueError):
                validate_run_fixture(broken)

    def test_trace_events_from_vm_stream_rejects_bad_frames(self):
        fixture = MockAgent().run("echo_success")
        broken = json.loads(json.dumps(fixture["vm_stream"]))
        broken[0]["stream"] = "unknown"
        with self.assertRaises(ValueError):
            trace_events_from_vm_stream(fixture["run"]["run_id"], broken)

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
