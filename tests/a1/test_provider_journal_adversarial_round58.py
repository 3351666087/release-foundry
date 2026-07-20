from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from packages.sdk.ashr_clone.provider_journal import (
    PROVIDER_MODALITIES,
    ProviderJournalStateError,
    ProviderRequestIdentity,
    ProviderRequestJournal,
)


def _identity(**overrides: str) -> ProviderRequestIdentity:
    values = {
        "tenant_id": "round58-tenant-secret",
        "project_id": "round58-project-secret",
        "provider": "round58-provider-secret",
        "model": "round58-model-secret",
        "endpoint_operation": "responses.create",
    }
    values.update(overrides)
    return ProviderRequestIdentity(**values)


def _request() -> dict:
    return {
        "prompt": "ROUND58_RAW_PROMPT_MUST_NOT_PERSIST",
        "stream": True,
        "headers": {
            "authorization": "Bearer ROUND58_RAW_BEARER_SECRET",
            "x-api-key": "ROUND58_RAW_API_KEY",
        },
        "parts": [
            {"type": "text", "text": "ROUND58_RAW_TEXT"},
            {"type": "image", "url": "https://media.invalid/i?sig=ROUND58_IMAGE_URL_SECRET"},
            {"type": "audio", "data": "ROUND58_RAW_AUDIO_BYTES"},
            {"type": "file", "path": "C:/round58/ROUND58_RAW_FILE.pdf"},
            {"type": "video", "url": "https://media.invalid/v?sig=ROUND58_VIDEO_URL_SECRET"},
        ],
    }


def test_restart_in_flight_is_fail_closed_indeterminate(tmp_path: Path):
    path = tmp_path / "journal.json"
    journal = ProviderRequestJournal(path)
    entry_id = journal.begin(_identity(), "restart-key", _request()).entry["entry_id"]
    journal.claim(
        entry_id,
        lease_owner="worker-a",
        lease_seconds=3600,
        now="2026-07-12T00:00:00Z",
    )

    recovered = ProviderRequestJournal(path).get(entry_id, now="2026-07-12T00:01:00Z")
    assert recovered["state"] == "indeterminate"
    assert recovered["lease_owner_fingerprint"] is None
    assert recovered["lease_expires_at"] is None


def test_concurrent_claim_has_one_winner_and_fencing_rejects_stale_completion(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = journal.begin(_identity(), "claim-key", _request()).entry["entry_id"]
    barrier = threading.Barrier(3)
    results: list[tuple[str, dict]] = []
    errors: list[Exception] = []

    def claim(owner: str) -> None:
        barrier.wait()
        try:
            result = journal.claim(
                entry_id,
                lease_owner=owner,
                lease_seconds=30,
                now="2026-07-12T00:00:00Z",
            )
            results.append((owner, result))
        except Exception as error:
            errors.append(error)

    workers = [
        threading.Thread(target=claim, args=("worker-a",)),
        threading.Thread(target=claim, args=("worker-b",)),
    ]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join()

    assert len(results) == 1
    assert len(errors) == 1
    owner, claimed = results[0]
    assert claimed["fencing_token"] == 1
    with pytest.raises(Exception, match="stale fencing token"):
        journal.mark_succeeded(
            entry_id,
            lease_owner=owner,
            fencing_token=2,
            now="2026-07-12T00:00:01Z",
        )


def test_stale_lease_becomes_indeterminate_and_old_fence_cannot_complete(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = journal.begin(_identity(), "stale-key", _request()).entry["entry_id"]
    claimed = journal.claim(
        entry_id,
        lease_owner="worker-a",
        lease_seconds=1,
        now="2026-07-12T00:00:00Z",
    )
    expired = journal.get(entry_id, now="2026-07-12T00:00:02Z")
    assert expired["state"] == "indeterminate"
    assert expired["indeterminate_evidence"]["reason"] == "lease_expired"
    with pytest.raises(Exception, match="not in_flight"):
        journal.mark_succeeded(
            entry_id,
            lease_owner="worker-a",
            fencing_token=claimed["fencing_token"],
            now="2026-07-12T00:00:03Z",
        )


def test_partial_stream_consumption_blocks_retry_and_retry_reconciliation(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = journal.begin(_identity(), "stream-key", _request()).entry["entry_id"]
    owner = "round58-stream-worker"
    claimed = journal.claim(
        entry_id,
        lease_owner=owner,
        lease_seconds=1,
        now="2026-07-12T00:00:00Z",
    )
    journal.observe_stream(
        entry_id,
        lease_owner=owner,
        fencing_token=claimed["fencing_token"],
        now="2026-07-12T00:00:00.100Z",
    )
    with pytest.raises(Exception, match="stream-observed"):
        journal.schedule_retry(
            entry_id,
            lease_owner=owner,
            fencing_token=claimed["fencing_token"],
            error_code="connection_lost",
            now="2026-07-12T00:00:00.200Z",
        )
    indeterminate = journal.get(entry_id, now="2026-07-12T00:00:02Z")
    assert indeterminate["state"] == "indeterminate"
    assert indeterminate["stream_observed"] is True
    with pytest.raises(ProviderJournalStateError, match="partial-stream"):
        journal.reconcile(
            entry_id,
            outcome="reserved",
            reason="unsafe automatic replay",
            now="2026-07-12T00:00:03Z",
        )
    assert journal.get(entry_id)["state"] == "indeterminate"


def test_reconciled_retry_increments_fence_and_rejects_old_owner(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    entry_id = journal.begin(_identity(), "fence-key", _request()).entry["entry_id"]
    first = journal.claim(
        entry_id,
        lease_owner="worker-a",
        lease_seconds=1,
        now="2026-07-12T00:00:00Z",
    )
    journal.get(entry_id, now="2026-07-12T00:00:02Z")
    journal.reconcile(
        entry_id,
        outcome="reserved",
        reason="provider_confirmed_not_accepted",
        now="2026-07-12T00:00:03Z",
    )
    second = journal.claim(
        entry_id,
        lease_owner="worker-b",
        lease_seconds=30,
        now="2026-07-12T00:00:04Z",
    )
    assert second["fencing_token"] == first["fencing_token"] + 1
    with pytest.raises(Exception, match="stale fencing token"):
        journal.mark_succeeded(
            entry_id,
            lease_owner="worker-a",
            fencing_token=first["fencing_token"],
            now="2026-07-12T00:00:05Z",
        )


def test_scope_isolates_tenant_project_provider_model_and_operation(tmp_path: Path):
    journal = ProviderRequestJournal(tmp_path / "journal.json")
    identities = [
        _identity(),
        _identity(tenant_id="tenant-other"),
        _identity(project_id="project-other"),
        _identity(provider="provider-other"),
        _identity(model="model-other"),
        _identity(endpoint_operation="audio.transcriptions.create"),
    ]
    entries = [
        journal.begin(identity, "shared-idempotency-key", _request()).entry
        for identity in identities
    ]
    assert len({entry["scope_fingerprint"] for entry in entries}) == len(identities)
    assert len({entry["entry_id"] for entry in entries}) == len(identities)


def test_five_modalities_are_equal_safe_evidence_and_raw_material_never_persists(tmp_path: Path):
    path = tmp_path / "journal.json"
    journal = ProviderRequestJournal(path)
    entry = journal.begin(_identity(), "ROUND58_RAW_IDEMPOTENCY_SECRET", _request()).entry

    evidence = entry["request_evidence"]
    assert evidence["modalities_present"] == list(PROVIDER_MODALITIES)
    assert evidence["modality_counts"] == {
        "text": 2,
        "image": 1,
        "audio": 1,
        "file": 1,
        "video": 1,
    }
    assert evidence["raw_prompt_persisted"] is False
    assert evidence["raw_media_persisted"] is False
    assert evidence["raw_url_persisted"] is False
    assert evidence["raw_credential_persisted"] is False

    raw = path.read_text(encoding="utf-8")
    for forbidden in (
        "round58-tenant-secret",
        "round58-project-secret",
        "round58-provider-secret",
        "round58-model-secret",
        "ROUND58_RAW_IDEMPOTENCY_SECRET",
        "ROUND58_RAW_PROMPT_MUST_NOT_PERSIST",
        "ROUND58_RAW_BEARER_SECRET",
        "ROUND58_RAW_API_KEY",
        "ROUND58_RAW_TEXT",
        "ROUND58_IMAGE_URL_SECRET",
        "ROUND58_RAW_AUDIO_BYTES",
        "ROUND58_RAW_FILE.pdf",
        "ROUND58_VIDEO_URL_SECRET",
        "media.invalid",
    ):
        assert forbidden not in raw

    persisted = json.loads(raw)
    persisted_entry = next(iter(persisted["entries"].values()))
    assert persisted_entry["raw_request_persisted"] is False
    assert persisted_entry["raw_response_persisted"] is False
    assert persisted_entry["credentials_persisted"] is False
