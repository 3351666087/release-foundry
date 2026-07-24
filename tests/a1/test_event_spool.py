from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashr_clone import (
    DurableEventSpool,
    EventBackpressureError,
    EventValidationError,
    PermanentDeliveryError,
    RetryableDeliveryError,
    build_event_envelope,
    build_trace_ingestion_sender,
    deterministic_sample,
    validate_event_envelope,
)


NOW = "2026-07-24T00:00:00.000Z"


def event(
    *,
    event_id: str = "evt_1",
    purpose: str = "telemetry",
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return build_event_envelope(
        tenant_id="tenant_a",
        project_id="project_a",
        run_id="run_a",
        source="sdk",
        event_type="trace.observation",
        payload=payload or {"content": "hello"},
        event_id=event_id,
        purpose=purpose,
        occurred_at=NOW,
        metadata={"region": "cn-east", "source_version": "test"},
    )


def test_event_envelope_is_integrity_sealed_and_secret_metadata_is_rejected() -> None:
    envelope = event()
    assert validate_event_envelope(envelope) == envelope
    assert envelope["integrity_sha256"]

    tampered = dict(envelope)
    tampered["payload"] = {"content": "changed"}
    with pytest.raises(EventValidationError, match="integrity"):
        validate_event_envelope(tampered)

    with pytest.raises(EventValidationError, match="secret-bearing"):
        build_event_envelope(
            tenant_id="tenant_a",
            project_id="project_a",
            run_id="run_a",
            source="sdk",
            event_type="trace.observation",
            payload={"content": "hello"},
            metadata={"api_key": "must-not-enter-the-spool"},
        )


def test_sampling_is_deterministic_and_non_droppable_purposes_survive_zero_rate(tmp_path: Path) -> None:
    assert deterministic_sample("stable-event", 0.37) == deterministic_sample("stable-event", 0.37)
    assert deterministic_sample("stable-event", 0.0) is False
    assert deterministic_sample("stable-event", 1.0) is True

    spool = DurableEventSpool(tmp_path / "spool", sampling_rate=0.0)
    assert spool.append(event(event_id="telemetry-dropped")) is None
    accepted = spool.append(event(event_id="audit-kept", purpose="audit"))
    assert accepted is not None
    assert accepted["event_count"] == 1
    assert accepted["purposes"] == ["audit"]


def test_flush_reuses_idempotency_key_across_retry_and_resume(tmp_path: Path) -> None:
    spool = DurableEventSpool(
        tmp_path / "spool",
        retry_base_seconds=1,
        retry_max_seconds=4,
        lease_seconds=10,
    )
    accepted = spool.enqueue(
        [event(event_id="retry-event")],
        batch_id="batch_retry",
        idempotency_key="idem_retry",
        now=NOW,
    )
    assert accepted is not None
    seen: list[dict[str, object]] = []

    def sender(batch: dict[str, object]) -> None:
        seen.append(batch)
        if len(seen) == 1:
            raise RetryableDeliveryError("token=super-secret")

    first = spool.flush(sender, now=NOW, lease_owner="worker-a")
    assert first.to_dict() == {
        "attempted": 1,
        "delivered": 0,
        "retried": 1,
        "dead_lettered": 0,
        "remaining": 1,
    }
    metadata = spool.list_batches(now="2026-07-24T00:00:01.000Z")[0]
    assert metadata["attempts"] == 1
    assert metadata["last_failure_code"] == "retryable_delivery_failure"
    assert metadata["lease_expires_at"] is None
    assert "super-secret" not in json.dumps(metadata)

    second = spool.flush(sender, now="2026-07-24T00:00:01.000Z", lease_owner="worker-b")
    assert second.to_dict() == {
        "attempted": 1,
        "delivered": 1,
        "retried": 0,
        "dead_lettered": 0,
        "remaining": 0,
    }
    assert [batch["idempotency_key"] for batch in seen] == ["idem_retry", "idem_retry"]
    assert [batch["batch_id"] for batch in seen] == ["batch_retry", "batch_retry"]


def test_permanent_failure_dead_letters_and_redrive_is_explicit(tmp_path: Path) -> None:
    spool = DurableEventSpool(tmp_path / "spool", max_attempts=2)
    spool.enqueue([event(event_id="dead-event")], batch_id="batch_dead", now=NOW)

    report = spool.flush(
        lambda _batch: (_ for _ in ()).throw(PermanentDeliveryError("authorization=opaque")),
        now=NOW,
    )
    assert report.dead_lettered == 1
    assert report.remaining == 0
    assert spool.list_batches(include_dead_letters=True)[0]["status"] == "dead_letter"
    dead_file = tmp_path / "spool" / "dead-letter" / "batch_dead.json"
    assert dead_file.exists()
    assert "opaque" not in dead_file.read_text(encoding="utf-8")

    redriven = spool.redrive("batch_dead", now="2026-07-24T00:00:05.000Z")
    assert redriven["status"] == "pending"
    assert redriven["attempts"] == 0
    delivered = spool.flush(lambda _batch: None, now="2026-07-24T00:00:05.000Z")
    assert delivered.delivered == 1


def test_backpressure_rejects_by_default_and_drop_oldest_never_drops_audit(tmp_path: Path) -> None:
    rejected = DurableEventSpool(tmp_path / "reject", max_batches=1)
    rejected.enqueue([event(event_id="first")], now=NOW)
    with pytest.raises(EventBackpressureError):
        rejected.enqueue([event(event_id="second")], now=NOW)

    dropping = DurableEventSpool(tmp_path / "drop", max_batches=1, drop_policy="drop_oldest")
    dropping.enqueue([event(event_id="audit", purpose="audit")], now=NOW)
    with pytest.raises(EventBackpressureError):
        dropping.enqueue([event(event_id="telemetry-2")], now=NOW)

    telemetry = DurableEventSpool(tmp_path / "drop-telemetry", max_batches=1, drop_policy="drop_oldest")
    telemetry.enqueue([event(event_id="telemetry-1")], now=NOW)
    telemetry.enqueue([event(event_id="telemetry-2")], now=NOW)
    batches = telemetry.list_batches()
    assert [item["batch_id"] for item in batches] == [batches[0]["batch_id"]]
    assert batches[0]["event_count"] == 1


def test_atomic_files_are_valid_json_and_trace_sender_preserves_batch_identity(tmp_path: Path) -> None:
    spool = DurableEventSpool(tmp_path / "spool")
    spool.enqueue([event(event_id="trace-1", payload={"answer": 42})], batch_id="batch_trace", now=NOW)
    pending = tmp_path / "spool" / "pending" / "batch_trace.json"
    assert json.loads(pending.read_text(encoding="utf-8"))["batch_id"] == "batch_trace"

    calls: list[tuple[object, ...]] = []

    def ingest(
        tenant_id: str,
        project_id: str,
        run_id: str,
        observations: list[dict[str, object]],
        *,
        batch_id: str,
        api_key_id: str | None,
        idempotency_key: str,
    ) -> dict[str, object]:
        calls.append((tenant_id, project_id, run_id, observations, batch_id, api_key_id, idempotency_key))
        return {"accepted": True}

    report = spool.flush(
        build_trace_ingestion_sender(
            ingest,
            tenant_id="tenant_a",
            project_id="project_a",
            run_id="run_a",
            api_key_id="key_opaque",
        ),
        now=NOW,
    )
    assert report.delivered == 1
    assert calls == [
        (
            "tenant_a",
            "project_a",
            "run_a",
            [{"answer": 42}],
            "batch_trace",
            "key_opaque",
            "spool_batch_trace",
        )
    ]
