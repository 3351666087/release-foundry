# Incident Response

## Priorities

1. Protect customer data and stop unsafe Agent or release actions.
2. Preserve immutable A1 execution, A2 decision, A3 workflow, identity, audit, and deployment evidence.
3. Restore a known-good service without changing historical decisions.

## Workflow

1. Assign an incident commander, security owner, runtime owner, evaluation owner, and customer-communication owner.
2. Revoke affected sessions, API keys, share links, and Provider credentials through the owning control plane.
3. Quarantine affected tenants, Agents, queues, images, or evidence objects as narrowly as possible.
4. Capture timeline, request/trace/resource references, image digests, Product Release ID, Customer Agent Release ID, and Decision Ledger head hash.
5. Replay through an isolated environment. Never replay private customer payloads into an unapproved Provider.
6. Apply remediation, run regression and release gates, and obtain a new human approval.
7. Publish a sanitized incident report and retain raw evidence under enterprise access controls.

An override may authorize an emergency action, but it must not delete or rewrite the original machine decision.
