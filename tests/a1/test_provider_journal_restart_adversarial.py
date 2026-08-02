from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.sdk.releasefoundry.provider_journal import (
    PERSISTENCE_CAPABILITIES,
    ProviderJournalError,
    ProviderJournalStateError,
    ProviderRequestIdentity,
    ProviderRequestJournal,
)
from packages.sdk.releasefoundry.provider_stream import ProviderStreamLedger


IDENTITY = ProviderRequestIdentity(
    tenant_id="tenant-private",
    project_id="project-private",
    provider="openai-compatible",
    model="model-private",
    endpoint_operation="responses.create",
)


def claimed(path: Path) -> tuple[str, ProviderRequestJournal]:
    journal = ProviderRequestJournal(path)
    entry_id = journal.begin(
        IDENTITY,
        "idempotency-private",
        {"stream": True, "parts": [{"type": "text", "text": "private"}]},
        now="2026-07-12T01:00:00Z",
    ).entry["entry_id"]
    journal.claim(
        entry_id,
        lease_owner="worker-private",
        lease_seconds=3600,
        now="2026-07-12T01:00:01Z",
    )
    return entry_id, journal


def test_restart_immediately_indeterminates_even_unexpired_claim_and_fences_old_worker(tmp_path: Path):
    path = tmp_path / "journal.json"
    entry_id, _ = claimed(path)

    restored = ProviderRequestJournal(path)
    entry = restored.get(entry_id)
    assert entry["state"] == "indeterminate"
    assert entry["indeterminate_evidence"]["reason"] == "process_restart"
    assert entry["lease_owner_fingerprint"] is None
    assert entry["lease_expires_at"] is None
    with pytest.raises(ProviderJournalStateError, match="not in_flight"):
        restored.mark_succeeded(
            entry_id,
            lease_owner="worker-private",
            fencing_token=1,
        )


def test_fenced_stream_snapshot_survives_restart_and_forbids_reserved_reconciliation(tmp_path: Path):
    path = tmp_path / "journal.json"
    entry_id, journal = claimed(path)
    stream = ProviderStreamLedger(entry_id=entry_id, fencing_token=1)
    stream.observe(0, "delta", "private partial output")
    recorded = journal.record_stream_snapshot(
        entry_id,
        stream.snapshot(),
        lease_owner="worker-private",
        fencing_token=1,
        now="2026-07-12T01:00:02Z",
    )
    assert recorded["stream_observed"] is True
    assert recorded["stream_snapshot"]["frame_count"] == 1
    assert "private partial output" not in path.read_text(encoding="utf-8")

    restored = ProviderRequestJournal(path)
    entry = restored.get(entry_id)
    assert ProviderStreamLedger(
        entry["stream_snapshot"], entry_id=entry_id, fencing_token=1
    ).snapshot() == entry["stream_snapshot"]
    with pytest.raises(ProviderJournalStateError, match="partial-stream"):
        restored.reconcile(
            entry_id,
            outcome="reserved",
            reason="provider_proved_no_side_effect",
        )
    resolved = restored.reconcile(
        entry_id,
        outcome="failed_terminal",
        reason="partial_stream_delivery_confirmed",
    )
    assert resolved["state"] == "failed_terminal"


def test_snapshot_reports_honest_local_persistence_capabilities(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    metadata = journal.snapshot()["metadata"]
    assert metadata["persistence_capabilities"] == PERSISTENCE_CAPABILITIES
    assert "durable" not in metadata
    assert metadata["persistence_capabilities"]["cross_process_claim_coordination"] is False
    assert metadata["persistence_capabilities"]["lease_survives_process_restart"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda state, entry: state.update(salt="not-a-secret-salt"), "invalid provider journal state"),
        (lambda state, entry: entry.update(state="running"), "entry state is invalid"),
        (lambda state, entry: entry.update(fencing_token=-1), "counters are invalid"),
        (lambda state, entry: entry.update(lease_owner_fingerprint="bad"), "invalid lease"),
        (lambda state, entry: entry.update(raw_request_persisted=True), "privacy flags are invalid"),
        (lambda state, entry: state["lookup"].update({"orphan": "missing"}), "lookup is invalid"),
    ],
)
def test_tampered_persisted_state_is_rejected_on_open(tmp_path: Path, mutation, message: str):
    path = tmp_path / "journal.json"
    entry_id, _ = claimed(path)
    state = json.loads(path.read_text(encoding="utf-8"))
    mutation(state, state["entries"][entry_id])
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ProviderJournalError, match=message):
        ProviderRequestJournal(path)


def test_stream_snapshot_rejects_stale_fence_and_digest_tampering(tmp_path: Path):
    path = tmp_path / "journal.json"
    entry_id, journal = claimed(path)
    stream = ProviderStreamLedger(entry_id=entry_id, fencing_token=1)
    stream.observe(0, "delta", "private")
    with pytest.raises(ProviderJournalStateError, match="stale fencing"):
        journal.record_stream_snapshot(
            entry_id,
            stream.snapshot(),
            lease_owner="worker-private",
            fencing_token=2,
            now="2026-07-12T01:00:02Z",
        )

    snapshot = stream.snapshot()
    snapshot["stream_digest"] = "f" * 64
    with pytest.raises(ValueError, match="summary is invalid"):
        journal.record_stream_snapshot(
            entry_id,
            snapshot,
            lease_owner="worker-private",
            fencing_token=1,
            now="2026-07-12T01:00:02Z",
        )
