import json
import subprocess
from pathlib import Path

import pytest

from ashr_clone.provider_stream import (
    ProviderStreamIntegrityError,
    ProviderStreamLedger,
    canonical_provider_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
TS_PACKAGE = REPO_ROOT / "packages" / "ts" / "ashr-clone"


def complete_stream() -> ProviderStreamLedger:
    ledger = ProviderStreamLedger()
    ledger.observe(0, "text_delta", "hello")
    ledger.observe(1, "tool_delta", {"name": "lookup", "index": 0})
    ledger.observe(2, "completed", {"finish_reason": "tool_calls"}, terminal=True)
    return ledger


def bound_stream() -> ProviderStreamLedger:
    ledger = ProviderStreamLedger(entry_id="pjr_round58", fencing_token=7)
    ledger.observe(0, "text_delta", "private prompt")
    ledger.observe(1, "completed", {"finish_reason": "stop"}, terminal=True)
    return ledger


def test_sequence_digest_terminal_and_idempotency():
    ledger = ProviderStreamLedger()
    first = ledger.observe(0, "text_delta", "hello")
    assert ledger.observe(0, "text_delta", "hello") == first
    with pytest.raises(ProviderStreamIntegrityError, match="conflicts"):
        ledger.observe(0, "text_delta", "different")
    with pytest.raises(ProviderStreamIntegrityError, match="gap"):
        ledger.observe(2, "text_delta", "late")
    with pytest.raises(ProviderStreamIntegrityError, match="missing a terminal"):
        ledger.finalize()
    ledger.observe(1, "completed", {"finish_reason": "stop"}, terminal=True)
    assert ledger.finalize()["terminal_observed"] is True
    with pytest.raises(ProviderStreamIntegrityError, match="terminal"):
        ledger.observe(2, "text_delta", "impossible")


def test_snapshot_round_trip_and_tamper_fail_closed():
    snapshot = complete_stream().finalize()
    assert ProviderStreamLedger(snapshot).finalize() == snapshot
    tampered = json.loads(json.dumps(snapshot))
    tampered["frames"][1]["content_digest"] = "f" * 64
    with pytest.raises(ProviderStreamIntegrityError, match="digest chain"):
        ProviderStreamLedger(tampered)


@pytest.mark.parametrize(
    "invalid_digest",
    [
        "A" * 64,
        "g" * 64,
        "0" * 63,
        "0" * 65,
        f"{'0' * 63} ",
        "０" * 64,
    ],
)
def test_snapshot_rejects_noncanonical_sha256_digests(invalid_digest: str):
    ledger = ProviderStreamLedger()
    ledger.observe(0, "delta", "hello")
    ledger.observe(1, "done", "", terminal=True)
    snapshot = ledger.finalize()
    snapshot["frames"][0]["content_digest"] = invalid_digest
    with pytest.raises(ProviderStreamIntegrityError, match="malformed"):
        ProviderStreamLedger(snapshot)


def test_journal_binding_is_digest_bound_strict_and_content_free():
    snapshot = bound_stream().finalize()
    assert snapshot["entry_id"] == "pjr_round58"
    assert snapshot["fencing_token"] == 7
    assert all(frame["entry_id"] == "pjr_round58" for frame in snapshot["frames"])
    assert all(frame["fencing_token"] == 7 for frame in snapshot["frames"])
    assert "private prompt" not in canonical_provider_json(snapshot)
    assert ProviderStreamLedger(
        snapshot, entry_id="pjr_round58", fencing_token=7
    ).finalize() == snapshot

    for mutate in (
        lambda value: value.update(fencing_token=8),
        lambda value: value["frames"][0].update(entry_id="pjr_other"),
        lambda value: value["frames"][0].pop("fencing_token"),
    ):
        tampered = json.loads(json.dumps(snapshot))
        mutate(tampered)
        with pytest.raises(ProviderStreamIntegrityError):
            ProviderStreamLedger(tampered)

    with pytest.raises(ProviderStreamIntegrityError, match="conflicts"):
        ProviderStreamLedger(snapshot, entry_id="pjr_round58", fencing_token=8)
    with pytest.raises(ProviderStreamIntegrityError, match="appear together"):
        ProviderStreamLedger(entry_id="pjr_round58")
    with pytest.raises(ProviderStreamIntegrityError, match="positive integer"):
        ProviderStreamLedger(entry_id="pjr_round58", fencing_token=True)


def test_python_and_typescript_snapshots_are_cross_language_compatible(tmp_path: Path):
    snapshot_path = tmp_path / "python-stream.json"
    python_snapshot = bound_stream().finalize()
    snapshot_path.write_text(canonical_provider_json(python_snapshot), encoding="utf-8")
    node_output_path = tmp_path / "typescript-stream.json"
    script = """
import { readFileSync, writeFileSync } from "node:fs";
import { ProviderStreamLedger, canonicalProviderJson } from "./dist/provider-stream.js";

const pythonSnapshot = JSON.parse(readFileSync(process.argv[1], "utf8"));
const validated = new ProviderStreamLedger(pythonSnapshot).finalize();
if (canonicalProviderJson(validated) !== canonicalProviderJson(pythonSnapshot)) process.exit(2);
const ledger = new ProviderStreamLedger(undefined, { entry_id: "pjr_typescript", fencing_token: 11 });
ledger.observe(0, "text_delta", "你好，跨语言流");
ledger.observe(1, "image_delta", { index: 0, bytes: 128 });
ledger.observe(2, "completed", { finish_reason: "stop" }, true);
writeFileSync(process.argv[2], canonicalProviderJson(ledger.finalize()), "utf8");
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(snapshot_path), str(node_output_path)],
        cwd=TS_PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    typescript_snapshot = json.loads(node_output_path.read_text(encoding="utf-8"))
    assert ProviderStreamLedger(typescript_snapshot).finalize() == typescript_snapshot
    assert typescript_snapshot["entry_id"] == "pjr_typescript"
    assert typescript_snapshot["fencing_token"] == 11
    assert canonical_provider_json(ProviderStreamLedger(python_snapshot).finalize()) == snapshot_path.read_text(
        encoding="utf-8"
    )
    persisted = snapshot_path.read_text(encoding="utf-8") + node_output_path.read_text(encoding="utf-8")
    assert "private prompt" not in persisted
    assert "你好，跨语言流" not in persisted
