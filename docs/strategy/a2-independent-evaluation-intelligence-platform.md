# A2 Independent Evaluation Intelligence Platform

Contract anchor: `A2_INDEPENDENT_EVALUATION_INTELLIGENCE_PLATFORM`

## Purpose

A1 produces trusted execution facts. A2 converts those facts into versioned
quality judgments, risk conclusions, and release decisions. A3 turns those
decisions into review, reporting, and operational action.

A2 is the authority for evaluation semantics and release-risk decisions. It
does not take ownership of runtime execution, identity issuance, artifact
storage, or user-interface behavior. This boundary makes the evaluation layer
independently testable, replaceable, and usable by every Agent or Skill that
can produce the shared A1 evidence contract.

The commercial outcome is not a larger prompt collection. It is a dependable
decision system that can answer:

- what evidence was evaluated;
- which judge, model, rubric, and policy versions produced the decision;
- why a release was allowed, blocked, or sent to review;
- whether a provider, parser, or evidence failure affected the result;
- how a human decision changed the operational outcome without erasing the
  original machine decision.

## Current Baseline

The current A2 implementation provides 60 scenarios, 5 rubric classes, 5
deterministic judge modes, 32 golden cases, 12 canonical failure classes,
regression replay, calibration reports, scenario selection, result
persistence, and release-policy evaluation.

The Ashr API authentication path has been validated, but the observed account
quota was exhausted at `5/5` requests with `0` remaining. No credential or raw
response belongs in public evidence. Ashr API is optional: it can be used as a
calibration provider when available, but it is not a runtime dependency of
this platform.

The independent path supports cloud APIs such as Qwen, OpenAI-compatible
providers, and later local inference through vLLM or Ollama. Provider breadth
must follow governance and evidence integrity, not precede them.

## Authority Boundaries

### A1

A1 owns execution and produces immutable run facts: run identity, tenant and
project scope, trace, tool calls, observations, timing, artifact references,
and runtime status. A1 runtime success does not mean evaluation success.

### A2

A2 owns normalization, evidence completeness, scenario selection, judging,
calibration, failure classification, release policy, review routing, decision
provenance, and regression intelligence.

### A3

A3 consumes A2 outputs and owns presentation, reviewer workflow, reporting,
and operational controls. A3 must not recompute A2 grades or release
decisions. It may display a newer decision only when it references a new A2
decision record.

## Trusted Data Flow

```text
A1 run facts
  -> ingestion validation
  -> Evidence Snapshot
  -> scenario and policy selection
  -> deterministic and semantic judges
  -> calibrated failure and confidence analysis
  -> Decision Ledger
  -> release gate and review queue
  -> A3 report, review, and operational action
```

Every stage must be replayable from versioned inputs. Derived summaries never
replace the evidence references from which they were created.

## Evidence Snapshot

An Evidence Snapshot is an immutable manifest for one evaluation unit. It
binds:

- organization, tenant, project, run, case, and scenario identity;
- A1 trace and artifact references with content hashes;
- evidence type: `text`, `image`, `audio`, `file`, or `video`;
- extractor, parser, OCR, transcription, and normalization versions;
- evidence completeness and collection errors;
- data classification, retention class, residency, and access policy;
- creation time and causal parent references.

Raw or private evidence remains in approved private storage. Public A2 reports
contain hashes, safe metadata, and opaque references only. Missing evidence is
represented as `evidence_missing`; it is never converted into a pass.

## Decision Ledger

The Decision Ledger is append-only. Each record binds:

- Evidence Snapshot hash;
- judge, model, prompt, rubric, scenario-pack, and policy versions;
- provider identity and health state;
- individual judge outcomes, abstentions, and disagreement;
- canonical failure classes and hard blockers;
- machine decision, confidence, and release status;
- human review or waiver as a later linked record;
- superseded decision references without mutation or deletion.

No A2 decision record means A3 must not display `release-ready`. Human override
must not delete or rewrite the original machine decision.

## Provider Control Plane

The Provider Control Plane presents one internal interface for deterministic
judges, Qwen and other cloud APIs, OpenAI-compatible endpoints, vLLM, Ollama,
and future local models. Each adapter declares capabilities, supported media,
model revision, region, timeout, cost metadata, and data-handling policy.

Production routing requires:

- health checks separated from evaluation outcomes;
- retry and circuit-breaker policy with bounded work;
- shadow and canary evaluation before promotion;
- pinned model revisions where providers support them;
- drift comparison against golden and incident-regression sets;
- tenant and data-classification routing constraints;
- traceable fallback decisions.

Provider failure must not become pass. A required provider outage results in
`abstain`, `inconclusive`, or a fail-closed release decision according to the
versioned policy.

## Multi-Judge Governance

Five judge slots do not automatically provide five independent opinions.
Independence is recorded across model family, provider, prompt lineage,
evidence projection, and failure mode. Correlated judges cannot create a
false consensus merely by voting.

Each semantic judge can return `pass`, `fail`, or `abstain`. The aggregator
must preserve disagreement and reason codes. Hard policy rules and
deterministic security findings cannot be overridden by an average semantic
score.

Judge promotion requires golden-set accuracy, failure-class recall,
calibration error, disagreement analysis, latency, and stability under
repeated runs. Judge versions are promoted through shadow, canary, active, and
retired states.

## Multimodal Security

The same evaluation contract covers `text`, `image`, `audio`, `file`, and
`video`, but each artifact passes through a security pipeline before a model
sees it:

1. type validation, size limits, hashing, and malware scanning;
2. decompression and parser isolation with resource limits;
3. metadata stripping and PII or secret classification;
4. OCR, transcription, frame sampling, or document extraction;
5. prompt-injection labeling and separation of evidence from instructions;
6. immutable extractor provenance and completeness status;
7. policy-controlled retention and deletion.

Extractor failure is distinct from Agent failure. Unsupported, corrupt,
malicious, or incomplete artifacts produce explicit evidence states and
review routing.

## Dataset And Label Governance

Scenario packs are capability and risk templates, not a finite list of all
possible Agent behavior. The 60-scenario pack is a baseline taxonomy.
Per-project selection adds parameterized cases, production incidents,
customer-specific policies, adversarial variants, and multimodal evidence
without inventing incompatible grading semantics.

Golden and regression cases require source provenance, label version,
reviewer identity, disagreement history, and promotion status. New labels
enter a candidate queue before they can affect release gates. Incorrect labels
are superseded, not silently edited.

Active sampling should prioritize judge disagreement, low confidence, new
capabilities, drift, rare failure classes, and high-risk tenants. This is an
evaluation feedback loop, not a current reinforcement-learning or RLHF claim.
It can later produce a governed reward dataset once sufficient real,
human-reviewed outcomes exist.

## Human Review

A3 receives an A2 review queue containing safe evidence references, machine
reasoning summaries, judge disagreement, policy context, and the exact action
requested. Reviewers record identity, role, decision, rationale, timestamp,
and optional expiry.

Waivers are scoped to a tenant, project, release, policy, and time window.
They cannot suppress the underlying finding or alter historical metrics.
High-impact overrides can require two-person approval.

## Release Policy

Release decisions are `allow`, `block`, or `review`. Policy evaluates both
scores and non-negotiable hard blockers, including:

- tenant-boundary or authorization violations;
- secret, PII, or unsafe artifact exposure;
- missing required evidence;
- unresolved high-severity incident regressions;
- invalid decision provenance;
- required judge or provider unavailability;
- policy or model versions outside their approved lifecycle.

The platform fails closed for release-critical uncertainty. Provider,
extractor, or A2 service failure must not be interpreted as an absence of
risk.

## A3 Consumption Contract

A3 consumes, but does not reinterpret:

- Evidence Snapshot summaries and safe artifact references;
- Decision Ledger records and provenance;
- release gate status and hard-block reasons;
- judge disagreement and calibration summaries;
- human review queue and waiver records;
- failure clusters, drift alerts, and incident-regression status.

Schema evolution is additive within a major version. Breaking changes require
a new schema version, fixture migration, A1 producer validation, and A3
consumer tests.

## Delivery Roadmap

### Phase 1: Trusted Spine

- contract schemas for Evidence Snapshot and Decision Ledger;
- append-only local persistence reference implementation;
- completeness states, hard blockers, and fail-closed semantics;
- A1 ingestion adapter and A3 consumption fixtures.

### Phase 2: Governed Providers

- provider interface and Qwen/OpenAI-compatible adapter;
- model registry, health, timeout, retry, circuit breaker, and audit metadata;
- shadow and canary judge comparison;
- deterministic fallback and explicit abstention.

### Phase 3: Multimodal Evidence

- secure artifact manifest;
- isolated image, audio, file, and video extractors;
- injection and PII classification;
- modality-specific completeness and calibration suites.

### Phase 4: Operational Intelligence

- review and waiver lifecycle;
- active-sampling backlog and golden-set promotion;
- failure clustering, drift alerts, and incident replay;
- tenant-aware release dashboards consumed by A3.

### Phase 5: Scale And Learning Readiness

- SQL-backed ledger and regression history;
- queue workers, idempotency, backpressure, and disaster recovery;
- SLOs, cost and capacity controls, and regional policy routing;
- governed reward dataset export after sufficient human-reviewed evidence.

## Commercial Acceptance Metrics

The platform is ready for production expansion when it demonstrates:

- complete provenance for every release decision;
- zero release-ready states without a valid Decision Ledger record;
- measured golden accuracy and failure recall by judge version;
- bounded calibration error and monitored judge correlation;
- replay determinism for deterministic judges and policy;
- explicit coverage and completeness for every required modality;
- audited reviewer and waiver actions;
- tested provider outage, parser failure, queue backlog, and rollback behavior;
- tenant isolation and public/private evidence separation;
- incident-to-regression promotion with measurable recurrence detection.

## Non-Goals

- A2 is not a Dify-style general workflow builder or chat application.
- A2 does not currently claim reinforcement learning or RLHF.
- A2 does not depend on Ashr API availability.
- A2 does not download or promote large models without a measured evaluation
  need, security review, resource plan, and rollback path.
- A2 does not replace A1 execution infrastructure or A3 product experience.

## System Invariants

- A1 runtime success does not equal evaluation success.
- Evidence missing or invalid never becomes pass.
- Provider failure must not become pass.
- A3 must not recompute A2 grade or release decision.
- No Decision Ledger record means no release-ready state.
- Human override preserves the original machine decision.
- Every release decision binds evidence, judge, model, prompt, rubric, and
  policy versions.
- Private evidence and credentials never enter public fixtures or reports.
