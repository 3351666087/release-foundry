from __future__ import annotations

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from packages.sdk.ashr_clone.provider_journal import (
    PERSISTENCE_CAPABILITIES,
    PROVIDER_MODALITIES,
    ProviderJournalConflict,
    ProviderJournalError,
    ProviderJournalStateError,
    ProviderRequestIdentity,
    ProviderRequestJournal,
)
from packages.sdk.ashr_clone.provider_stream import ProviderStreamLedger


def identity(**overrides: str) -> ProviderRequestIdentity:
    values = {
        "tenant_id": "tenant-private-name",
        "project_id": "project-private-name",
        "provider": "openai-compatible",
        "model": "private-model-name",
        "endpoint_operation": "responses.create",
    }
    values.update(overrides)
    return ProviderRequestIdentity(**values)


def sensitive_request() -> dict:
    return {
        "prompt": "the raw prompt must never persist",
        "stream": True,
        "tools": [{"name": "lookup"}, {"name": "save"}],
        "headers": {"authorization": "Bearer credential-must-not-persist"},
        "parts": [
            {"type": "text", "text": "private text content"},
            {"type": "image", "url": "https://private.example/image.png"},
            {"type": "audio", "data": "private-audio-base64"},
            {"type": "file", "path": "C:/private/customer.pdf"},
            {"type": "video", "url": "https://private.example/video.mp4"},
        ],
    }


def begin(journal: ProviderRequestJournal, key: str = "private-idempotency-key") -> str:
    return journal.begin(
        identity(), key, sensitive_request(), now="2026-07-12T01:00:00Z"
    ).entry["entry_id"]


def claim(
    journal: ProviderRequestJournal,
    entry_id: str,
    owner: str = "private-worker-alpha",
    now: str = "2026-07-12T01:00:01Z",
) -> dict:
    return journal.claim(
        entry_id, lease_owner=owner, lease_seconds=30, now=now
    )


def test_reserved_claim_and_terminal_replay_survive_restart_with_five_modalities(tmp_path: Path):
    path = tmp_path / "journal.json"
    journal = ProviderRequestJournal(path)
    decision = journal.begin(
        identity(), "key", sensitive_request(), now="2026-07-12T01:00:00Z"
    )
    assert decision.entry["state"] == "reserved"
    assert decision.entry["request_evidence"]["modalities_present"] == list(PROVIDER_MODALITIES)
    assert decision.entry["request_evidence"]["modality_counts"] == {
        "text": 2, "image": 1, "audio": 1, "file": 1, "video": 1
    }

    claimed = claim(journal, decision.entry["entry_id"])
    assert claimed["state"] == "in_flight"
    assert claimed["attempt_count"] == 1
    assert claimed["fencing_token"] == 1
    assert claimed["lease_owner_fingerprint"] != "private-worker-alpha"
    assert claimed["lease_expires_at"] == "2026-07-12T01:00:31Z"
    journal.mark_succeeded(
        decision.entry["entry_id"],
        lease_owner="private-worker-alpha",
        fencing_token=1,
        usage={
            "prompt_tokens": 11, "completion_tokens": 4, "images": 1,
            "audio_seconds": 3.5, "file_bytes": 2048, "video_seconds": 8,
        },
        evidence={"finish_reason": "stop", "provider_request_id": "req_safe_1", "status_code": 200},
        now="2026-07-12T01:00:02Z",
    )

    restored = ProviderRequestJournal(path)
    replay = restored.begin(
        identity(), "key", sensitive_request(), now="2026-07-12T02:00:00Z"
    )
    assert replay.idempotent_replay is True
    assert replay.entry["state"] == "succeeded"
    assert replay.entry["lease_owner_fingerprint"] is None
    assert replay.entry["usage_evidence"] == {
        "input_tokens": 11, "output_tokens": 4, "total_tokens": 15,
        "image_units": 1, "audio_seconds": 3.5, "file_bytes": 2048, "video_seconds": 8,
    }
    assert replay.entry["replay_evidence"]["persistence_capabilities"] == PERSISTENCE_CAPABILITIES


def test_retry_reclaim_increments_fence_and_rejects_old_fence_and_wrong_owner(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = begin(journal)
    claim(journal, entry_id)
    retry = journal.schedule_retry(
        entry_id,
        lease_owner="private-worker-alpha",
        fencing_token=1,
        error_code="rate_limit",
        retry_after_seconds=5,
        now="2026-07-12T01:00:02Z",
    )
    assert retry["state"] == "retry_wait"
    assert retry["retry_not_before"] == "2026-07-12T01:00:07Z"
    with pytest.raises(ProviderJournalStateError, match="not eligible"):
        claim(journal, entry_id, "private-worker-beta", "2026-07-12T01:00:06Z")

    reclaimed = claim(journal, entry_id, "private-worker-beta", "2026-07-12T01:00:07Z")
    assert reclaimed["fencing_token"] == 2
    assert reclaimed["attempt_count"] == 2
    with pytest.raises(ProviderJournalStateError, match="stale fencing"):
        journal.mark_succeeded(
            entry_id, lease_owner="private-worker-alpha", fencing_token=1,
            now="2026-07-12T01:00:08Z",
        )
    with pytest.raises(ProviderJournalStateError, match="lease owner"):
        journal.mark_failed_terminal(
            entry_id, lease_owner="private-worker-alpha", fencing_token=2,
            error_code="fatal", now="2026-07-12T01:00:08Z",
        )


def test_expired_claim_becomes_indeterminate_and_requires_explicit_reconciliation(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = begin(journal)
    claim(journal, entry_id)
    expired = journal.get(entry_id, now="2026-07-12T01:00:31Z")
    assert expired["state"] == "indeterminate"
    assert expired["indeterminate_evidence"]["reason"] == "lease_expired"
    assert expired["lease_owner_fingerprint"] is None
    with pytest.raises(ProviderJournalStateError, match="cannot claim"):
        claim(journal, entry_id, "private-worker-beta", "2026-07-12T01:00:32Z")

    resolved = journal.reconcile(
        entry_id,
        outcome="succeeded",
        reason="provider_receipt_confirmed",
        usage={"input_tokens": 2, "output_tokens": 3},
        evidence={"provider_request_id": "req_safe_2", "status_code": 200},
        now="2026-07-12T01:01:00Z",
    )
    assert resolved["state"] == "succeeded"
    assert resolved["reconciliation_evidence"][0]["prior_fencing_token"] == 1
    with pytest.raises(ProviderJournalStateError, match="only indeterminate"):
        journal.reconcile(
            entry_id, outcome="failed_terminal", reason="duplicate_operator_action"
        )


def test_reconcile_to_reserved_requires_new_claim_and_new_fence(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = begin(journal)
    claim(journal, entry_id)
    journal.expire_stale(now="2026-07-12T01:00:31Z")
    reserved = journal.reconcile(
        entry_id, outcome="reserved", reason="provider_proved_no_side_effect",
        now="2026-07-12T01:00:32Z",
    )
    assert reserved["state"] == "reserved"
    reclaimed = claim(journal, entry_id, "private-worker-beta", "2026-07-12T01:00:33Z")
    assert reclaimed["fencing_token"] == 2


def test_stream_observation_is_durable_and_permanently_forbids_automatic_retry(tmp_path: Path):
    path = tmp_path / "journal.json"
    journal = ProviderRequestJournal(path)
    entry_id = begin(journal)
    claim(journal, entry_id)
    observed = journal.observe_stream(
        entry_id, lease_owner="private-worker-alpha", fencing_token=1,
        now="2026-07-12T01:00:02Z",
    )
    assert observed["stream_observed"] is True

    restored = ProviderRequestJournal(path)
    assert restored.get(entry_id)["state"] == "indeterminate"
    with pytest.raises(ProviderJournalStateError, match="not in_flight"):
        restored.schedule_retry(
            entry_id, lease_owner="private-worker-alpha", fencing_token=1,
            error_code="connection_lost", now="2026-07-12T01:00:03Z",
        )
    assert restored.get(entry_id, now="2026-07-12T01:00:03Z")["stream_observed"] is True


def test_streamed_success_requires_active_fence_terminal_snapshot(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = begin(journal)
    claim(journal, entry_id)
    stream = ProviderStreamLedger(entry_id=entry_id, fencing_token=1)
    stream.observe(0, "delta", "private partial")
    journal.record_stream_snapshot(
        entry_id, stream.snapshot(), lease_owner="private-worker-alpha",
        fencing_token=1, now="2026-07-12T01:00:02Z",
    )
    with pytest.raises(ProviderJournalStateError, match="terminal snapshot"):
        journal.mark_succeeded(
            entry_id, lease_owner="private-worker-alpha", fencing_token=1,
            now="2026-07-12T01:00:03Z",
        )
    stream.observe(1, "done", "", terminal=True)
    journal.record_stream_snapshot(
        entry_id, stream.finalize(), lease_owner="private-worker-alpha",
        fencing_token=1, now="2026-07-12T01:00:04Z",
    )
    assert journal.mark_succeeded(
        entry_id, lease_owner="private-worker-alpha", fencing_token=1,
        now="2026-07-12T01:00:05Z",
    )["state"] == "succeeded"


def test_same_process_threaded_claim_has_one_winner(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = begin(journal)

    def attempt(owner: str) -> str:
        try:
            journal.claim(
                entry_id, lease_owner=owner, lease_seconds=30,
                now="2026-07-12T01:00:01Z",
            )
            return "won"
        except ProviderJournalStateError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, [f"worker-{index}" for index in range(8)]))
    assert outcomes.count("won") == 1
    assert outcomes.count("rejected") == 7


@pytest.mark.parametrize(
    "operation",
    [
        "https://provider.example/v1/responses",
        "/v1/chat/completions",
        "responses.create?token=x",
        "responses create",
        "Bearer credential",
        "",
        "A" * 65,
    ],
)
def test_endpoint_operation_rejects_url_or_uncontrolled_semantics(tmp_path: Path, operation: str):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    with pytest.raises(ValueError, match="controlled operation label"):
        journal.begin(identity(endpoint_operation=operation), "key", sensitive_request())


def test_persisted_json_excludes_private_owner_url_prompt_media_and_credentials(tmp_path: Path):
    path = tmp_path / "journal.json"
    journal = ProviderRequestJournal(path)
    entry_id = begin(journal)
    claim(journal, entry_id)
    raw = path.read_text(encoding="utf-8")
    for forbidden in (
        "private-worker-alpha", "tenant-private-name", "project-private-name",
        "private-model-name", "private-idempotency-key", "raw prompt", "private text",
        "private.example", "private-audio", "customer.pdf", "credential-must-not-persist",
        "/v1/", "https://",
    ):
        assert forbidden not in raw
    entry = next(iter(json.loads(raw)["entries"].values()))
    assert entry["identity_evidence"]["endpoint_operation"] == "responses.create"
    assert "endpoint_fingerprint" not in entry["identity_evidence"]


def test_scope_is_independent_for_each_commercial_identity_dimension(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    identities = [
        identity(),
        identity(tenant_id="tenant-b"),
        identity(project_id="project-b"),
        identity(provider="ollama"),
        identity(model="model-b"),
        identity(endpoint_operation="audio.transcribe"),
    ]
    entries = [journal.begin(item, "same-key", sensitive_request()).entry for item in identities]
    assert len({entry["entry_id"] for entry in entries}) == len(identities)


def test_same_scope_key_with_changed_request_conflicts_after_restart(tmp_path: Path):
    path = tmp_path / "journal.json"
    ProviderRequestJournal(path).begin(identity(), "same-key", sensitive_request())
    changed = sensitive_request()
    changed["prompt"] = "different private prompt"
    with pytest.raises(ProviderJournalConflict, match="different request fingerprint"):
        ProviderRequestJournal(path).begin(identity(), "same-key", changed)


def test_invalid_timing_fence_and_corrupt_lease_are_rejected(tmp_path: Path):
    path = tmp_path / "journal.json"
    journal = ProviderRequestJournal(path)
    entry_id = begin(journal)
    for bad in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="positive finite"):
            journal.claim(entry_id, lease_owner="worker", lease_seconds=bad)
    claim(journal, entry_id)
    with pytest.raises(ValueError, match="positive integer"):
        journal.observe_stream(entry_id, lease_owner="private-worker-alpha", fencing_token=0)

    state = json.loads(path.read_text(encoding="utf-8"))
    state["entries"][entry_id]["lease_expires_at"] = None
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ProviderJournalError, match="invalid lease"):
        ProviderRequestJournal(path).get(entry_id)


def test_terminal_failure_and_safe_evidence_validation(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = begin(journal)
    claim(journal, entry_id)
    with pytest.raises(ValueError, match="not safe journal evidence"):
        journal.mark_failed_terminal(
            entry_id,
            lease_owner="private-worker-alpha",
            fencing_token=1,
            error_code="invalid_request",
            evidence={"provider_request_id": "https://private.example/request?token=secret"},
            now="2026-07-12T01:00:02Z",
        )
    failed = journal.mark_failed_terminal(
        entry_id,
        lease_owner="private-worker-alpha",
        fencing_token=1,
        error_code="invalid_request",
        evidence={"provider_request_id": "req_safe_3", "status_code": 400},
        now="2026-07-12T01:00:03Z",
    )
    assert failed["state"] == "failed_terminal"
    assert failed["response_evidence"]["retryable"] is False
