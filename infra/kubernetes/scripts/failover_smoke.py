#!/usr/bin/env python3
"""Readiness and one-pod failover smoke for an installed A1 Helm release."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


COMPONENTS = ("api", "queue-worker", "identity-delivery")
SERVICE_COMPONENTS = frozenset(("api", "identity-delivery"))
PART_OF_LABEL = "releasefoundry-a1-runtime"
CONFIRMATION = "delete-one-pod-per-a1-workload"


class SmokeError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def selector(component: str) -> str:
    return f"app.kubernetes.io/part-of={PART_OF_LABEL},app.kubernetes.io/component={component}"


def is_ready_pod(pod: Mapping[str, Any]) -> bool:
    conditions = pod.get("status", {}).get("conditions", [])
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in conditions
    )


def pod_identity(pod: Mapping[str, Any]) -> tuple[str, str]:
    metadata = pod.get("metadata", {})
    name = metadata.get("name")
    uid = metadata.get("uid")
    if not isinstance(name, str) or not name or not isinstance(uid, str) or not uid:
        raise SmokeError("pod metadata is missing name or uid")
    return name, uid


def ready_endpoint_addresses(endpoint_slices: Mapping[str, Any]) -> int:
    addresses: set[str] = set()
    for item in endpoint_slices.get("items", []):
        for endpoint in item.get("endpoints", []):
            conditions = endpoint.get("conditions", {})
            if conditions.get("ready") is not True:
                continue
            for address in endpoint.get("addresses", []):
                if isinstance(address, str) and address:
                    addresses.add(address)
    return len(addresses)


@dataclass(frozen=True)
class WorkloadSnapshot:
    component: str
    deployment_name: str
    desired: int
    ready: int
    available: int
    observed_generation: int
    generation: int
    ready_pods: tuple[tuple[str, str], ...]
    pdb_disruptions_allowed: int
    ready_endpoints: int | None

    @property
    def failover_floor(self) -> int:
        return self.desired - 1

    def validate(self) -> None:
        if self.component not in COMPONENTS:
            raise SmokeError(f"unexpected workload component {self.component!r}")
        if self.desired < 2:
            raise SmokeError(f"{self.component} requires at least two desired replicas")
        if self.ready < self.desired or self.available < self.desired:
            raise SmokeError(f"{self.component} is not fully ready before disruption")
        if self.observed_generation < self.generation:
            raise SmokeError(f"{self.component} deployment generation has not converged")
        if len(self.ready_pods) < self.desired:
            raise SmokeError(f"{self.component} does not have all desired Pods ready")
        if self.pdb_disruptions_allowed < 1:
            raise SmokeError(f"{self.component} PDB does not currently allow one disruption")
        if self.component in SERVICE_COMPONENTS:
            if self.ready_endpoints is None or self.ready_endpoints < self.desired:
                raise SmokeError(f"{self.component} Service lacks a ready endpoint per replica")


class Kubectl:
    def __init__(self, binary: str, context: str, namespace: str, timeout_seconds: int) -> None:
        self.binary = binary
        self.context = context
        self.namespace = namespace
        self.timeout_seconds = timeout_seconds

    def _base(self) -> list[str]:
        return [
            self.binary,
            "--context",
            self.context,
            "--namespace",
            self.namespace,
            "--request-timeout",
            f"{self.timeout_seconds}s",
        ]

    def run(self, args: Sequence[str], *, expect_json: bool = False) -> Any:
        completed = subprocess.run(
            [*self._base(), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout_seconds + 5,
            check=False,
        )
        if completed.returncode != 0:
            reason = " ".join((completed.stderr or completed.stdout).split())[:400]
            raise SmokeError(f"kubectl command failed ({args[0]} {args[1]}): {reason}")
        if not expect_json:
            return completed.stdout
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise SmokeError("kubectl returned invalid JSON") from exc

    def get_json(self, resource: str, *, label_selector: str) -> Mapping[str, Any]:
        result = self.run(["get", resource, "--selector", label_selector, "--output", "json"], expect_json=True)
        if not isinstance(result, dict):
            raise SmokeError(f"kubectl {resource} response must be an object")
        return result

    def delete_pod(self, pod_name: str, expected_uid: str) -> None:
        current = self.run(["get", "pod", pod_name, "--output", "json"], expect_json=True)
        _, current_uid = pod_identity(current)
        if current_uid != expected_uid:
            raise SmokeError(f"refusing to delete replaced Pod {pod_name}")
        self.run(["delete", "pod", pod_name, "--wait=false", "--grace-period=30"])


def exactly_one(items: Iterable[Mapping[str, Any]], description: str) -> Mapping[str, Any]:
    values = list(items)
    if len(values) != 1:
        raise SmokeError(f"expected exactly one {description}, found {len(values)}")
    return values[0]


def snapshot_workload(client: Kubectl, component: str) -> WorkloadSnapshot:
    labels = selector(component)
    deployment = exactly_one(client.get_json("deployments", label_selector=labels).get("items", []), f"{component} deployment")
    pdb = exactly_one(client.get_json("poddisruptionbudgets", label_selector=labels).get("items", []), f"{component} PDB")
    pods = client.get_json("pods", label_selector=labels).get("items", [])

    metadata = deployment.get("metadata", {})
    spec = deployment.get("spec", {})
    status = deployment.get("status", {})
    desired = int(spec.get("replicas", 0))
    ready_pods = tuple(sorted(pod_identity(pod) for pod in pods if is_ready_pod(pod)))

    endpoint_count: int | None = None
    if component in SERVICE_COMPONENTS:
        services = client.get_json("services", label_selector=labels).get("items", [])
        service = exactly_one(services, f"{component} Service")
        service_name = service.get("metadata", {}).get("name")
        if not isinstance(service_name, str) or not service_name:
            raise SmokeError(f"{component} Service has no name")
        slices = client.get_json(
            "endpointslices.discovery.k8s.io",
            label_selector=f"kubernetes.io/service-name={service_name}",
        )
        endpoint_count = ready_endpoint_addresses(slices)

    return WorkloadSnapshot(
        component=component,
        deployment_name=str(metadata.get("name", "")),
        desired=desired,
        ready=int(status.get("readyReplicas", 0)),
        available=int(status.get("availableReplicas", 0)),
        observed_generation=int(status.get("observedGeneration", 0)),
        generation=int(metadata.get("generation", 0)),
        ready_pods=ready_pods,
        pdb_disruptions_allowed=int(pdb.get("status", {}).get("disruptionsAllowed", 0)),
        ready_endpoints=endpoint_count,
    )


def choose_candidate(snapshot: WorkloadSnapshot) -> tuple[str, str]:
    snapshot.validate()
    return snapshot.ready_pods[0]


def snapshot_public(snapshot: WorkloadSnapshot) -> dict[str, Any]:
    return {
        "component": snapshot.component,
        "deployment": snapshot.deployment_name,
        "desired": snapshot.desired,
        "ready": snapshot.ready,
        "available": snapshot.available,
        "ready_pod_count": len(snapshot.ready_pods),
        "pdb_disruptions_allowed": snapshot.pdb_disruptions_allowed,
        "ready_endpoints": snapshot.ready_endpoints,
    }


def wait_for_replacement(
    client: Kubectl,
    before: WorkloadSnapshot,
    deleted_uid: str,
    deadline_seconds: int,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[WorkloadSnapshot, int, int | None]:
    deadline = time.monotonic() + deadline_seconds
    minimum_ready = before.desired
    minimum_endpoints = before.ready_endpoints
    while time.monotonic() < deadline:
        current = snapshot_workload(client, before.component)
        minimum_ready = min(minimum_ready, current.ready)
        if current.ready_endpoints is not None:
            minimum_endpoints = (
                current.ready_endpoints
                if minimum_endpoints is None
                else min(minimum_endpoints, current.ready_endpoints)
            )
        if current.ready < before.failover_floor:
            raise SmokeError(f"{before.component} dropped below failover readiness floor")
        if current.ready_endpoints is not None and current.ready_endpoints < before.failover_floor:
            raise SmokeError(f"{before.component} Service dropped below endpoint floor")
        current_uids = {uid for _, uid in current.ready_pods}
        replacement_seen = deleted_uid not in current_uids and len(current_uids) >= before.desired
        if replacement_seen and current.ready >= before.desired:
            current.validate()
            return current, minimum_ready, minimum_endpoints
        sleeper(2.0)
    raise SmokeError(f"{before.component} did not replace the disrupted Pod before the deadline")


def dry_run_plan(context: str, namespace: str, timeout_seconds: int) -> dict[str, Any]:
    return {
        "schema_version": "releasefoundry.a1.kubernetes_failover_plan.v1",
        "mode": "plan",
        "context": context,
        "namespace": namespace,
        "components": list(COMPONENTS),
        "preconditions": [
            "each deployment has at least two desired and ready replicas",
            "each PodDisruptionBudget allows one disruption",
            "API and identity-delivery Services have one ready endpoint per replica",
            "only one Pod is deleted at a time",
        ],
        "disruption_confirmation": CONFIRMATION,
        "timeout_seconds_per_component": timeout_seconds,
    }


def live_smoke(client: Kubectl, timeout_seconds: int) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "schema_version": "releasefoundry.a1.kubernetes_failover_smoke.v1",
        "mode": "live",
        "started_at": utc_now(),
        "context": client.context,
        "namespace": client.namespace,
        "components": [],
        "status": "running",
    }
    for component in COMPONENTS:
        before = snapshot_workload(client, component)
        pod_name, pod_uid = choose_candidate(before)
        component_evidence: dict[str, Any] = {
            "component": component,
            "before": snapshot_public(before),
            "deleted_pod": pod_name,
            "deleted_pod_uid": pod_uid,
            "started_at": utc_now(),
        }
        client.delete_pod(pod_name, pod_uid)
        after, minimum_ready, minimum_endpoints = wait_for_replacement(
            client, before, pod_uid, timeout_seconds
        )
        component_evidence.update(
            {
                "after": snapshot_public(after),
                "minimum_ready_observed": minimum_ready,
                "minimum_service_endpoints_observed": minimum_endpoints,
                "completed_at": utc_now(),
                "status": "passed",
            }
        )
        evidence["components"].append(component_evidence)
    evidence["status"] = "passed"
    evidence["completed_at"] = utc_now()
    return evidence


def write_json(payload: Mapping[str, Any], output: Path | None) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(encoded)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(encoded, encoding="utf-8", newline="\n")
    temporary.replace(output)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "live"), default="plan")
    parser.add_argument("--kubectl", default="kubectl")
    parser.add_argument("--context", required=True, help="Explicit kubeconfig context name")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--confirm-disruption", default="")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.timeout_seconds < 30 or args.timeout_seconds > 1800:
        raise SmokeError("timeout-seconds must be between 30 and 1800")
    if args.mode == "plan":
        write_json(dry_run_plan(args.context, args.namespace, args.timeout_seconds), args.output)
        return 0
    if args.confirm_disruption != CONFIRMATION:
        raise SmokeError(f"live mode requires --confirm-disruption {CONFIRMATION}")
    client = Kubectl(args.kubectl, args.context, args.namespace, min(args.timeout_seconds, 60))
    write_json(live_smoke(client, args.timeout_seconds), args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeError, subprocess.TimeoutExpired) as exc:
        print(f"failover smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
