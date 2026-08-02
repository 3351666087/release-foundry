# A2 Endgame Acceptance Checklist

> Status snapshot: 2026-08-01
>
> Owner lane: A2
>
> Working branch: `agent/a2-readiness-hardening`

This file is the durable acceptance source for A2. It is intentionally stricter
than a progress report: an item is checked only when reproducible code, tests,
real service receipts, and human evidence (when required) prove the whole item.

A2's end state is not "more reports." The target is a closed learning and
release-control loop:

1. generate multiple candidate answers and tool-execution trajectories for the
   same task;
2. ask ReleaseFoundry to score actions, the final answer, and the overall candidate
   ranking;
3. turn higher- and lower-ranked candidates into `chosen` / `rejected`
   preference pairs;
4. preserve the input, native multimodal evidence, execution trace, final
   answer, ReleaseFoundry reward, failure location, failure class, and rationale;
5. create human-adjudicated gold labels when ReleaseFoundry and other teachers disagree;
6. train local specialist Reward Models and a multimodal fusion judge;
7. use DPO-like preference optimization for the execution model;
8. train an action-value model for tool choice, arguments, ordering, recovery,
   and stopping;
9. let local models handle ordinary cases and escalate uncertain, high-risk, or
   disputed cases;
10. send the largest local/ReleaseFoundry disagreements back through active learning;
11. add production retry, abandonment, correction, complaint, and successful
    completion behavior to the reward system and permanent regression set.

## 2026-07-29 meeting summary

- **Paid-call safety is enforced.** `create_run` is a single-attempt mutation.
  Across the six decision-boundary repeats, all `48/48` calls succeeded with
  zero mutation retries and zero errors. Read-only recovery may retry, but a
  paid mutation is never silently resubmitted.
- **Real ReleaseFoundry calibration is receipt-bound.** The same `35` tasks and `8`
  strategies were run for `6` repeats, producing `1,680/1,680` paid
  evaluations, structure grades, final-answer grades, and independently
  verified per-test receipts. A global aggregate marker is not used as
  completion authority.
- **The useful signal and the instability are both preserved.** Missing-action
  severity was monotonic in `210/210` observations. Redundant-call count was
  monotonic in `208/210`, and final-answer defect severity in `207/210`.
  However, exact ranking was stable for only `7/35` tasks, pair status for
  `19/35`, and pair choice for `14/35`; unstable cases remain review and
  active-learning targets rather than being converted into training labels.
- **A2 now has explicit A1 and A3 integration contracts.** Commit `49d2d1b1`
  bridges hash-verified A2 release evidence into durable A1 SDK events. Commit
  `632293b2` publishes a deterministic, hash-bound A3 judge-consumer contract
  for all `23` A2 failure classes and the closed six-action release vocabulary.
- **The C3-C5 readiness and release path now fails closed at content and type
  boundaries.**
  Commit `b716820c` requires canonical owner-review provenance before an
  incident candidate can enter replay. Commit `0e81bcf7` binds case-book and
  replay output to case-book and calibration-matrix content hashes. Commit
  `0fc67ec4` rejects truthy strings, booleans masquerading as numbers, invalid
  ratios/confidence/cost values, and malformed counts in commercial readiness.
  Commit `88535d34` requires explicit preflight evidence gates. Commit
  `231dbe33` self-hashes evidence-readiness output and binds it to the exact
  calibration matrix, batch plan, semantic harness, and case map. Commits
  `4a028b03` and `d7ced3c4` make both the release gate and its downstream
  unblock checklist reject malformed counts, nested objects, and top-level
  inputs without crashing or treating unknown values as zero evidence. Commit
  `803773a8` additionally makes readiness reconstruct C5 replay from the
  current calibration matrix and case book instead of trusting replay-declared
  status, counts, or case membership. Commit `1b85c457` additionally prevents
  C5 from treating case-book metadata as receipt authority: it revalidates the
  retained C3 ReleaseFoundry terminal receipt and C4 semantic human-review receipt from
  the calibration matrix, binds each reviewed source to its canonical content
  hash, and rejects missing, replaced, or rewrapped evidence. Commit `8359baed`
  then binds the C6 release gate to the current case book and rejects a
  re-sealed `mature` replay unless deterministic reconstruction from the
  current calibration matrix and case book produces the exact same artifact.
  The complete A2 test suite passed with `1,410 passed, 2 skipped`; all `57`
  generated A2 fixtures match committed output.
- **Truth boundary:** these `1,680` evaluations are real ReleaseFoundry teacher calls but
  remain text-projected and human-unreviewed. There is no trained Reward Model,
  DPO/PPO run, action-value model, human gold set, native-media acceptance
  result, authorized preference pair, or commercial-release authority yet.
  C3, C4, C5, and C6 therefore remain `partial`.
- **Provider smoke update (2026-08-01):** the compensated free-plan key now has
  independently retained, byte-verified generated-artifact receipts for image,
  audio, and file workflows. Video was team-tested as unreliable and remains
  `provider_unverified`; it must fail closed to unsupported/uncertain. These
  generated-artifact receipts do not change native-input acceptance, training
  eligibility, or release authority.
- **Independent generated-artifact receipt boundary (2026-08-01):** the reused
  combined `text/image/audio/file` request returned verified image and file
  artifacts but no audio artifact, so its receipt is explicitly `partial` and
  cannot prove the combined modality scope. Three independent content-bound
  requests now provide complete receipts for image, audio, and file
  respectively. The new image and file requests were each created exactly once
  with `create_request_retry_count=0`; the audio request safely reused its exact
  prior binding. Readiness recomputes modality coverage from the underlying
  artifact receipts and does not trust self-declared receipt status or coverage
  flags. These receipts prove only that ReleaseFoundry generated and returned those
  dataset artifacts. They do **not** prove that callers can upload native image,
  audio, or file inputs, and they are not grading evidence.
  `accepted_modalities` therefore remains `["text"]`,
  `native_media_uploaded=false`, `media_upload_api_observed=false`,
  `caller_native_input_support_proven=false`, and `c3_grading_ready=false`.
  C3 remains below `met`, and video remains `provider_unverified`. Public
  evidence is `docs/evidence/a2_multimodal_real_api_smoke.json`,
  `docs/evidence/a2_multimodal_image_real_api_smoke.json`,
  `docs/evidence/a2_multimodal_audio_real_api_smoke.json`,
  `docs/evidence/a2_multimodal_file_real_api_smoke.json`, and
  `docs/evidence/a2_releasefoundry_native_media_surface.json`.
- **Pinned native-media surface audit (2026-07-29):** A2 audited the exact
  `releasefoundry==0.3.1` wheel, bound the result to the wheel SHA-256 and SDK
  surface fingerprint, and used the real compensated free-plan key for one
  read-only `client.init()` session check. The receipt records exactly one API
  call and zero mutation attempts. The audited SDK surface exposes no verified
  caller upload method, dataset-ingestion method, or immutable media-URL
  parameter. Readiness therefore reports caller-native image/audio/file as
  `provider_surface_missing`, video as `provider_unverified`,
  `caller_native_input_support_proven=false`, and `c3_grading_ready=false`.
  Any SDK drift, upload signal, mutation, malformed field, or private material
  fails closed for manual review. Public evidence is
  `docs/evidence/a2_releasefoundry_native_media_surface.json`.
- **Current compensated free-plan capability report (2026-08-01):** image,
  audio, and file are verified only as generated-artifact capabilities, each by
  an independent complete receipt. The combined request remains partial, the
  pinned SDK still exposes no verified caller upload/ingestion surface, and
  video is not currently reliable. A2 therefore keeps video
  `provider_unverified` and degrades it to an explicit unsupported/uncertain
  path rather than presenting it as working. Commit `c2c13f79` binds each
  capability to its own request content hash and makes readiness reject partial,
  shared, or self-asserted coverage. The complete A2 suite passed `1,416 passed,
  2 skipped, 19 warnings`; all `57` generated fixtures matched committed output.
- **Multimodal release-boundary hardening (2026-07-30):** commit `a230faa9`
  makes the release gate reject duplicate and non-canonical modality scopes.
  `audio` and `file` are recorded as verified generated-artifact capabilities
  but remain non-qualifying without caller-native evidence; `video` remains
  provider-unverified and requires retest or human review. The targeted
  multimodal suite passed `20/20`, the adjacent readiness/authority regression
  suite passed `102/102`, and all `57` generated A2 fixtures remained pinned.
  This hardening does not advance C3: it remains `partial`, and the release gate
  remains blocked.
- **Live receipt and cross-lane refresh (2026-07-31):** commit `8925af48`
  refreshed the public-safe ReleaseFoundry-generated image, audio, and file receipts
  without creating a new paid mutation; all remain generated-artifact evidence,
  with `native_media_uploaded=false`,
  `caller_native_input_support_proven=false`, and
  `c3_grading_ready=false`. Video remains `provider_unverified`. Commit
  `dc9037ff` then bound A2's A1 route-scope input to its SHA-256, verified its
  public-safe source policy, checked declared route counts against observed
  Go/Python/TypeScript routes, and required exact tenancy-route parity. Any
  drift now fails closed instead of silently qualifying A1 security context.
  Commit `f2307fd9` also binds the A3 Auth/RBAC document and OpenAPI by SHA-256
  and requires exact HTTP-method-plus-path parity; missing, extra, or
  wrong-method auth operations now fail closed. The targeted contract suite
  passed `86/86`; the complete A2 suite passed `1,386 passed, 2 skipped`; all
  `57` generated fixtures remained reproducible.
- **C3 public receipt binding hardening (2026-07-31):** commit `cd13311`
  requires strict ReleaseFoundry imports to retain one independently validated,
  public-safe run terminal receipt and binds every one of the six observations
  to that exact artifact by canonical SHA-256, run-level fields, and per-test
  fields. Matching self-declared hashes or booleans without the receipt no
  longer qualify. Missing, duplicate, extra, malformed, nonterminal, or
  field-mismatched tests fail closed. The importer schema is now
  `a2.releasefoundry_grading_import.v2`; the matrix and C3 readiness gate preserve and
  revalidate the receipt instead of trusting observation metadata alone.
  The targeted suite passed `206/206`; the complete A2 suite passed
  `1,394 passed, 2 skipped`. This is engineering readiness only:
  acceptance-authorized six-case grading, human review, and authentic
  server-observed receipts are still missing, so C3 remains `partial`.
- **C4 independent human-review receipt hardening (2026-07-31):** commit
  `f64abbac` upgrades the semantic import envelope to
  `a2.semantic_judge_import.v2` and requires strict imports and merges to retain
  one public-safe `a2.semantic_human_review_receipt.v1` artifact. The verifier
  rejects missing, duplicate, extra, malformed, or field-mismatched review
  cases, verifies each rationale hash, and requires every reviewed observation
  to bind the exact receipt hash and verification fields. Readiness independently
  revalidates the retained receipt rather than trusting self-declared
  `review_status`, reviewer hashes, or timestamps. The targeted suite passed
  `172/172`; the complete A2 suite passed `1,400 passed, 2 skipped, 19
  warnings`. This closes an evidence-forgery path but does not fabricate human
  review: reviewed live semantic observations remain `0/6`, so C4 remains
  `partial`.
- **C6 source-authority hardening (2026-08-01):** commit `8359baed` adds the
  case-book source hash to the release artifact and requires every claimed
  `mature` C5 replay to pass the existing deterministic
  matrix-plus-case-book replay verifier. A forged replay and matching forged
  commercial `C5=met` field remain blocked even after both artifacts are
  re-sealed. The targeted contract/release suite passed `125/125`; the complete
  A2 suite passed `1,410 passed, 2 skipped, 19 warnings`; all `57` generated
  fixtures remained reproducible. This closes a C5-to-C6 promotion path but
  does not create reviewed evidence: C5 remains `seed` (`1/3` replay,
  `0/3` reviewed external evidence) and C6 remains `partial`.

## Status rules

- `[x]`: the complete acceptance condition is proved by reproducible evidence.
- `[ ] Active`: implementation is currently being completed.
- `[ ] Framework`: useful code or schema exists, but real evidence, scale, or
  acceptance metrics are still missing.
- `[ ] External`: completion needs paid ReleaseFoundry/strong-model calls and/or a
  qualified human reviewer.
- `[ ] Not started`: no acceptance-grade implementation exists yet.
- `machine-observed`: produced automatically; it is not human-reviewed evidence.
- `reviewed`: explicitly approved by a recorded human review step.

Do not change a status to `[x]` by editing a generated report or gate field.
The status must be derived from the authoritative evidence and its verifier.
Text descriptions of media never count as native image, audio, video, or file
evidence.

## Current verified boundary

| Area | Verified state | Acceptance implication |
| --- | --- | --- |
| Real ReleaseFoundry credential | Present in the environment without exposing its value | Paid calls are possible |
| Redacted real-API smoke | `6/6` read-only calls succeeded at `2026-07-27T13:30:37Z` (`init`, health, datasets, runs, requests, agents) | Proves current connectivity only; does not prove C3 grading |
| ReleaseFoundry-generated artifact smoke | The default request completed with exact request/dataset binding and verified a PNG image (`1,265,233` bytes) plus PDF file (`16,676` bytes). A separate audio-only request completed and verified an MP3 (`383,938` bytes); its follow-up reused the exact request without a new mutation. `video` was excluded | Proves ReleaseFoundry-generated image/audio/file artifact retrieval only. It does not prove caller-native media upload, native grading, human review, or C3 readiness; video remains `provider_unverified` |
| C3 public receipt binding | Strict reviewed/complete imports require one retained public-safe run receipt whose canonical hash, exact six-case set, run fields, and per-test fields match every ReleaseFoundry observation; readiness revalidates the artifact independently | Self-declared observation hashes or flags cannot advance C3. Real acceptance grading and human review are still required |
| C3 ReleaseFoundry grading | `partial`; reviewed ReleaseFoundry observations `0/6` | C3 must remain below `met` |
| C4 human-review receipt binding | Strict reviewed/complete semantic imports require one retained public-safe receipt whose exact six-case set, review fields, judgment fields, rationale hashes, and artifact hash match every semantic observation; readiness revalidates it independently | Self-declared `review_status`, reviewer hashes, timestamps, or receipt flags cannot advance C4 |
| C4 semantic judging | commercial gate `partial`; evidence lane `offline_reference_only`; reviewed live observations `0/6` | Offline references and synthetic receipts cannot be represented as live or human-reviewed evidence |
| C5 case-book replay | maturity `seed`; replay `1/3`; reviewed external evidence `0/3` | Release gate remains blocked |
| Commercial readiness | current gate `C2`; `ready_for_commercial_gate=false` | No commercial-readiness claim |
| Calibration matrix | local expectations `300/300`; exploratory ReleaseFoundry outcomes `300/300`; machine agreement `265/300`; media-case disagreements `35/50` | This is an unreviewed machine comparison, not the acceptance confusion matrix or human gold |
| Paid live-calibration harness | Exploratory ReleaseFoundry grading completed for `300/300` variants in six batches of `50`; all tests had server-side grading markers; six non-retried `create_run` calls completed with no HTTP error | The execution proves the fenced harness, but the unverified machine mapping grants no training, release, item-4, item-5, item-6, or C3 authority |
| Exact-ID disagreement repeats | All `35` exploratory disagreements were rerun three times (`105/105` evaluations) with dataset-bound test IDs preserved; final-answer grading and numeric scores were observed for `105/105`; three non-retried `create_run` calls completed with no error | All `35/35` disagreements persisted, but this is still text-projected machine evidence pending human review; it grants no training, release, native-multimodal, or C3 authority |
| Corrected multi-candidate order probe | The positional `a2-releasefoundry-live-v5` harness ran the same `35` tasks with `8` candidate strategies across `3` independent repeats: `840/840` paid evaluations, `24` successful non-retried `create_run` calls, `840/840` structure grades, `840/840` final-answer grades, and per-test receipt verification throughout | The pre-v5 tool-order normalization flaw is removed. The corrected runs did **not** confirm the earlier order-blindness claim; only `3/105` task-repeat pairs formed provisional preferences and `102/105` remained blocked. All results remain text-projected, human-unreviewed, and training-ineligible |
| Action-value teacher probe | The same positional harness completed `35` tasks, `8` action-value strategies, and `3` independent repeats: `840/840` paid evaluations, `24/24` successful non-retried `create_run` calls, `840/840` per-test receipts, and `840/840` structure/final-answer grades | Mean ordering was stable at the strategy level, but exact per-task ranking was stable for only `18/35` tasks and pair status flipped for `8/35`. ReleaseFoundry applied only a `12.5667` mean reward penalty to a redundant post-success call and a `18.9143` penalty to premature stopping. These are active-learning findings, not training labels; authorized pairs remain `0` |
| Decision-boundary gradient probe | Six independent repeats covered the same `35` tasks with `8` defect-count/severity strategies: `1,680/1,680` paid evaluations, `48/48` successful non-retried `create_run` calls, `1,680/1,680` verified receipts, and `1,680/1,680` structure/final-answer grades | Missing-action severity was monotonic for `210/210` task observations. Redundant-call count was monotonic for `208/210`, final-answer defect severity for `207/210`, and all three families together for `205/210`. Exact ranking was stable for only `7/35` tasks, pair status for `19/35`, and pair choice for `14/35`. This remains text-projected, human-unreviewed, training-ineligible teacher evidence |
| Fixed-six dataset acquisition | Real request completed; exact request binding and exact server dataset name passed; server returned `6` official `multi_run_storyboard` runs; fixed case markers and semantic-contract hashes were absent; a unique six-way semantic mapping is now machine-proposed | Exact identity and human adjudication remain unverified, `paid_create_run_allowed=false`, and the proposal grants no training, release, or C3 authority |
| Governed preference export | Private RM/DPO/action-value export contract implemented and tested; real training-eligible pairs `0` | Export is ready for verified human-gold or explicitly allowed teacher-consensus pairs, but no real ReleaseFoundry/human training corpus is claimed |
| Governed preference review | Dedicated tenant-scoped review cases, reviewer events, resolutions, and learning-candidate tables are implemented and tested | No pair becomes authoritative or training-eligible until a complete human review or independent arbitration; current real training-eligible count remains `0` |
| Active-learning teacher path | Durable teacher queue, verified public-receipt settlement, and verified-receipt-to-human-review dispatch are implemented and tested | Dispatch opens a fenced review only; it grants no human-gold status or training authority, and real training-eligible pairs remain `0` |
| Production feedback loop | Tenant-scoped ingestion, canonical review receipts, and reviewed-feedback-to-regression-candidate persistence are implemented and tested | Accepted feedback can create only a `pending_owner_review` candidate; it cannot grant human gold, training eligibility, permanent-regression status, or C5 maturity |
| Incident-to-replay promotion integrity | Promotion now requires `source=incident_candidate`, `decision=approved`, `replay_input_approved=true`, a canonical reviewer receipt, and a positive review timestamp | Missing, malformed, or self-declared provenance fails closed; owner approval still does not create human gold or reviewed external evidence |
| Case-book/replay content integrity | Case-book and replay artifacts are sealed with canonical SHA-256 hashes; readiness and the release gate bind the current case book and calibration matrix and deterministically reconstruct every replay that claims `mature` before trusting C5 status, counts, or case membership | Reusing IDs after changing source content, or rehashing a replay and matching commercial report after changing declared readiness, maturity, counts, or case set, cannot advance C5 or C6 |
| Commercial-readiness input integrity | Gate booleans require exact JSON booleans; counts, ratios, confidence, and cost require correctly typed finite values in valid ranges | Strings such as `"false"`, numeric strings, boolean confidence, and malformed counts cannot advance C0-C5 |
| Evidence-readiness source integrity | The report carries a canonical self-hash plus exact content hashes for the calibration matrix, batch plan, semantic harness, and case map | A stale, edited, or source-mismatched readiness report cannot authorize C3/C4 or commercial readiness |
| Release/unblock input integrity | Release-gate and C3/C4/C5 unblock-checklist inputs normalize nested objects, strictly validate authority counts, and default malformed or unknown evidence to a blocker | Corrupt JSON values cannot crash the reporting path or be interpreted as zero missing evidence |
| Blind version comparison | Anonymous paired-run scoring, immutable post-score role binding, exact holdout identity checks, paired deltas, and regression blockers are implemented and tested | Engineering gate exists, but no real incumbent/challenger student-model comparison receipt exists yet |
| A2 to A1 durable evidence events | Hash-verified release evidence is projected into stable `releasefoundry.event.v1` envelopes with scoped identifiers, retry-stable idempotency, tamper rejection, and secret-bearing metadata rejection | A1 can durably ingest A2 release evidence without raw private inputs or retry-induced event drift |
| A2 to A3 judge-consumer contract | A deterministic, hash-bound public contract exports all `23` A2 failure classes and exactly six release actions, with legacy aliases normalized and unknown actions rejected | A3 can consume A2 judgments without private evidence and cannot invent an out-of-vocabulary release decision |

Public-safe connectivity evidence:
`docs/evidence/a2_real_api_smoke.json`.

Public-safe ReleaseFoundry-generated artifact evidence:
`docs/evidence/a2_multimodal_real_api_smoke.json` and
`docs/evidence/a2_multimodal_audio_real_api_smoke.json`.

Public-safe fixed-six acquisition evidence:
`docs/evidence/a2_releasefoundry_dataset_acquisition_receipt.json`.

Public-safe fixed-six mapping proposal:
`docs/evidence/a2_releasefoundry_dataset_mapping_receipt.json`.

Public-safe 300-point exploratory calibration evidence:
`docs/evidence/a2_releasefoundry_exploratory_calibration.json`.

Public-safe exact-ID disagreement-repeat evidence:
`docs/evidence/a2_releasefoundry_exploratory_disagreement_repeat_stability.json`.

Public-safe corrected multi-candidate order-probe evidence:
`docs/evidence/a2_releasefoundry_sensitivity_probe_corrected_order_repeat_1.json`,
`docs/evidence/a2_releasefoundry_sensitivity_probe_corrected_order_repeat_2.json`,
`docs/evidence/a2_releasefoundry_sensitivity_probe_corrected_order_repeat_3.json`, and
`docs/evidence/a2_releasefoundry_sensitivity_probe_corrected_order_stability.json`.

Public-safe action-value teacher-probe evidence:
`docs/evidence/a2_releasefoundry_action_value_probe_repeat_1.json`,
`docs/evidence/a2_releasefoundry_action_value_probe_repeat_2.json`,
`docs/evidence/a2_releasefoundry_action_value_probe_repeat_3.json`, and
`docs/evidence/a2_releasefoundry_action_value_probe_stability.json`.

Public-safe decision-boundary gradient evidence:
`docs/evidence/a2_releasefoundry_decision_boundary_probe_repeat_1.json`,
`docs/evidence/a2_releasefoundry_decision_boundary_probe_repeat_2.json`,
`docs/evidence/a2_releasefoundry_decision_boundary_probe_repeat_3.json`,
`docs/evidence/a2_releasefoundry_decision_boundary_probe_repeat_4.json`,
`docs/evidence/a2_releasefoundry_decision_boundary_probe_repeat_5.json`,
`docs/evidence/a2_releasefoundry_decision_boundary_probe_repeat_6.json`, and
`docs/evidence/a2_releasefoundry_decision_boundary_probe_stability.json`.

## Current execution ledger

This section is the short durable handoff for the next Agent session. The
forty-item checklist below remains the acceptance authority.

- Latest corrected-order code/evidence commits:
  `a93b59c7 fix(a2): preserve tool call order in ReleaseFoundry payloads`,
  `e60a30ac docs(a2): correct historical ReleaseFoundry order probe methodology`,
  `43a26ccb`, `3f4f94f9`, and `8e53cd37` for the three independent real-call
  repeats, and
  `fea21888 fix(a2): aggregate corrected ReleaseFoundry order probes`.
- Latest action-value code/evidence commits:
  `5b866265 feat(a2): add ReleaseFoundry action value probe`,
  `4bb2cbf2`, `377a6b3a`, and `2dd99ec4` for the three independent paid
  repeats,
  `42ea8fb9 feat(a2): aggregate ReleaseFoundry action value stability`, and
  `3f2170cc fix(a2): validate provisional ReleaseFoundry pair authority`.
- Latest decision-boundary code/evidence commits:
  `dec7fc06 feat(a2): add ReleaseFoundry decision boundary probe`,
  `08b2c420 fix(a2): compact long ReleaseFoundry journal paths`,
  `95c0b91c`, `5fe0a1d7`, and `bab89199` for the three independent paid
  repeats,
  `040e17f1 feat(a2): aggregate ReleaseFoundry decision boundary stability`, and
  `977ed555 test(a2): record ReleaseFoundry decision boundary stability`,
  `b9b6e99a`, `2add8340`, and `a6b81c76` for paid repeats four through six,
  `25dda1c5 feat(a2): aggregate six ReleaseFoundry boundary repeats`, and
  `3969a3b3 test(a2): record six-repeat ReleaseFoundry boundary stability`.
- Latest multimodal smoke hardening:
  `79246aff fix(a2): fence multimodal ReleaseFoundry smoke` and
  `f714d7e7 fix(a2): record terminal multimodal request status`.
  The targeted and complete A2 suites passed after the latter commit:
  `1,294 passed, 2 skipped`; all `57` generated A2 fixtures match committed
  output. The real smoke remains a terminal failure receipt, not a capability
  acceptance result.
- Latest live-media receipt refresh:
  `491a7827 evidence(a2): refresh real multimodal ReleaseFoundry receipts`,
  `a4949859 docs(a2): record multimodal release boundary`, and
  `8925af48 test(a2): refresh live ReleaseFoundry media receipts`.
  The 2026-07-31 refresh reused exact content-bound requests with zero new
  mutation attempts. It verifies ReleaseFoundry-generated image, audio, and file
  artifacts only; it does not prove caller-native uploads or advance C3.
- Latest cross-lane route-scope hardening:
  `dc9037ff fix(a2): bind A1 route scope security contract`.
  A2 now binds the exact public A1 snapshot by SHA-256 and rejects source-policy,
  route-count, or tenancy-parity drift. The current snapshot declares and
  observes `114` Go, `35` Python, and `38` TypeScript routes.
- Latest A3 Auth/RBAC contract hardening:
  `f2307fd9 fix(a2): bind A3 auth operations contract`.
  A2 now binds the A3 Auth/RBAC document, OpenAPI, fail-closed write-path
  contract, and event-outbox contract by SHA-256. Auth readiness additionally
  requires exact documented/OpenAPI HTTP operation parity.
- Latest C3 receipt-binding hardening:
  `cd13311 fix(a2): bind C3 observations to public run receipt`.
  Strict imports and readiness now require an independently retained
  public-safe run receipt with exact hash, six-case coverage, run-field, and
  per-test-field bindings.
- Latest C4 receipt-binding hardening:
  `f64abbac fix(a2): bind C4 observations to human review receipt`.
  Strict semantic imports and readiness now require an independently retained
  public-safe human-review receipt with exact artifact, case, judgment,
  rationale-hash, and observation-metadata bindings.
- Latest cross-component integration commits:
  `49d2d1b1 feat(a2): bridge release evidence to durable SDK events` and
  `632293b2 feat(a2): publish judge consumer contract`.
- Latest fail-closed evidence-chain commits:
  `b716820c fix(a2): verify replay promotion provenance`,
  `0e81bcf7 fix(a2): bind regression replay to case-book content`,
  `803773a8 fix(a2): bind C5 replay to current sources`,
  `0fc67ec4 fix(a2): require typed commercial readiness evidence`,
  `88535d34 fix(a2): require explicit preflight evidence gates`,
  `231dbe33 fix(a2): bind readiness evidence to source artifacts`,
  `4a028b03 fix(a2): fail closed on malformed release evidence`, and
  `d7ced3c4 fix(a2): harden release unblock checklist inputs`.
- Verified by:
  `python -m pytest tests/a2/test_releasefoundry_sensitivity_probe_report.py
  tests/a2/test_releasefoundry_preference_calibration.py
  tests/a2/test_releasefoundry_live_calibration.py -q` (`54 passed`) on 2026-07-28,
  `python -m pytest
  tests/a2/test_releasefoundry_action_value_stability_report.py -q` (`4 passed`) on
  2026-07-28,
  `python -m pytest
  tests/a2/test_releasefoundry_decision_boundary_stability_report.py
  tests/a2/test_releasefoundry_preference_calibration.py -q` (`21 passed`) on
  2026-07-28,
  `python -m pytest tests/a2/test_release_gate_safety.py -q`
  (`20 passed`) on 2026-07-28,
  `python -m pytest tests/a2 -q` (`1,207 passed, 2 skipped`) on 2026-07-28,
  `python scripts/a2_regenerate_fixtures.py --check`
  (`all 57 A2 generated fixture files match committed output`) on 2026-07-28,
  `python -m pytest tests/a2/test_cross_lane_security.py
  tests/a2/test_a2_saas_control_plane.py tests/a2/test_contracts.py -q`
  (`86 passed`) on 2026-07-31,
  `python -m pytest tests/a2 -q`
  (`1,386 passed, 2 skipped, 19 warnings`) on 2026-07-31,
  `python -m pytest tests/a2/test_evidence_readiness_safety.py
  tests/a2/test_calibration_import_safety.py
  tests/a2/test_releasefoundry_test_receipts.py tests/a2/test_readiness_safety.py
  tests/a2/test_contracts.py -q` (`206 passed`) on 2026-07-31,
  `python -m pytest tests/a2 -q`
  (`1,394 passed, 2 skipped, 19 warnings`) on 2026-07-31,
  `python -m pytest tests/a2/test_calibration_import_safety.py
  tests/a2/test_evidence_readiness_safety.py tests/a2/test_readiness_safety.py
  tests/a2/test_contracts.py -q` (`172 passed`) on 2026-07-31,
  `python -m pytest tests/a2 -q`
  (`1,400 passed, 2 skipped, 19 warnings`) on 2026-07-31,
  `python -B scripts/a2_regenerate_fixtures.py --check`
  (`all 57 A2 generated fixture files match committed output`) on 2026-07-31,
  artifact self-hash checks, public-receipt secret/private-identifier scans,
  and exact staging before every commit.
- Completed real ReleaseFoundry execution:
  the `exploratory_unverified_mapping` lane graded all `300` deterministic
  prompt/reference perturbations in six batches of `50`. The private journal
  confirms six successful `create_run` operations, zero mutation retries, zero
  HTTP errors, no duplicate terminal outcomes, and an individual server-side
  grading marker for every submitted test. The public receipt remains
  `training_eligible=false`, `acceptance_authority=false`,
  `release_authority=false`, and `c3_transition_allowed=false`.
- Completed exact-ID repeat execution:
  all `35` disagreements were evaluated three more times in three independent
  runs, for `105/105` planned observations. The private journals confirm three
  successful `create_run` operations, zero mutation retries, zero HTTP errors,
  `105/105` individually attributable server-grading markers, `105/105`
  final-answer grading signals, and `105/105` numeric scores. A completed run is
  no longer accepted from an aggregate marker alone; every test must expose both
  its structural marker and its asynchronous final-answer marker.
- Machine-observed result:
  five text-defined cases agreed with the local expected outcome for all
  `250/250` variants. The media-pipeline case disagreed on `35/50` variants:
  ReleaseFoundry passed `35` candidates that the local fixture expected to fail. This is
  the primary active-learning and human-review pool; it is an observation about
  the current text-projected experiment, not a gold-label conclusion about
  native multimodal behavior.
- Repeat-observed result:
  ReleaseFoundry passed all `105/105` repeated evaluations and all `35/35` source
  disagreements remained `persistent_disagreement`. Numeric scores had mean
  `93.29`, minimum `65.0`, maximum `95.0`, and population standard deviation
  `4.46`. This measures ReleaseFoundry stability on the existing projections only; it does
  not resolve whether the local fixture or ReleaseFoundry judgment is correct.
- Corrected multi-candidate result:
  payload construction now consumes actual calls positionally instead of
  searching by expected tool name. Three independent corrected repeats covered
  `35` tasks and `8` candidate strategies for `840` receipt-bound evaluations.
  The three reports share one source-queue hash and exact task set; all `24`
  `create_run` calls succeeded with zero retry, and all `840` tests expose both
  structure and final-answer grades. The corrected stability report found an
  `absolute_gap_at_most_2_rate` of `0.0` for both `wrong_tool_order` and
  `reverse_tool_order`, so the historical order-blindness conclusion is not
  supported by the corrected payloads. This is an ReleaseFoundry behavior observation,
  not human gold or training authority.
- Action-value result:
  three independent positional repeats covered `35` tasks and `8` strategies
  for another `840` receipt-bound evaluations. All `24` mutation attempts
  succeeded with zero retry or error, and all `840` tests expose independent
  structure and final-answer grading. The aggregate mean reward order was
  `reference_aligned` (`97.7857`) >
  `redundant_post_success_call` (`85.2190`) >
  `premature_stop` (`78.8714`) >
  `contradictory_final_answer_after_tools` (`70.5381`) >
  `recovered_argument_error` (`47.8429`) >
  `recovered_wrong_tool` (`47.7143`) >
  `hallucinated_without_tools` (`42.7286`) >
  `severe_control` (`12.5762`). Exact task-level ranking was stable for
  `18/35` tasks, while `8/35` tasks changed between blocked and provisional
  pair status. Across all repeats, `17/105` task observations formed an
  ReleaseFoundry-provisional direction and `88/105` remained blocked. Human-reviewed and
  training-eligible pair counts remain `0`.
- Decision-boundary result:
  six independent positional repeats covered `35` tasks and `8` strategies for
  `1,680` receipt-bound evaluations. All `48` mutation attempts succeeded with
  zero retry or error, and all `1,680` tests expose independent
  structure and final-answer grading. The aggregate mean reward order was
  `reference_aligned` (`97.8548`) >
  `minor_final_answer_after_tools` (`86.6143`) >
  `redundant_post_success_call` (`85.1476`) >
  `premature_stop` (`79.2119`) >
  `redundant_post_success_calls_2` (`77.6548`) >
  `redundant_post_success_calls_3` (`72.6786`) >
  `contradictory_final_answer_after_tools` (`70.9833`) >
  `premature_stop_two_actions` (`61.6881`). Missing one versus two required
  actions produced a strict monotonic penalty in `210/210` observations.
  Redundant-call count was monotonic in `208/210`, and final-answer defect
  severity in `207/210`. The five violation observations belong to two unique
  tasks and are explicit active-learning priorities. Exact ranking was stable
  for `7/35` tasks, pair status for `19/35`, pair choice for `14/35`, and
  all-family monotonicity held for `205/210` observations. Across all repeats,
  `165/210` observations formed an ReleaseFoundry-provisional direction and `45/210`
  remained blocked. Human-reviewed, authorized, and training-eligible pair
  counts remain `0`.
- External critical-path blocker:
  item 2 has advanced from an unmapped generated dataset to a unique machine
  proposal, but remains blocked by `human_adjudicated_mapping_required`.
  Therefore C3 remains `partial`; exploratory paid calls may continue only in
  their fenced, non-authoritative lane, and no result from that lane may be
  promoted into training or release evidence without review.
- Completed local framework:
  item 29 now has tenant-scoped ingestion, canonical human review records, and
  automated creation of pending case-book candidates. Automation may not
  invent human gold, training eligibility, permanent-regression status, or
  bypass owner review and the external-evidence gate. Incident promotion now
  verifies canonical approval provenance before replay, and case-book/replay
  artifacts are bound to exact content hashes instead of trusting IDs alone.
  Commercial readiness now accepts only exact booleans and valid typed
  numeric evidence, so malformed artifacts cannot promote C0-C5. Item 30 has a
  fail-closed blind incumbent/challenger comparison gate with paired metrics and
  immutable version bindings. Item 26 now has a strict probability-calibration
  qualification report, and item 27 has a fail-closed three-tier uncertainty
  and escalation router using the six-action release vocabulary.
- Active local work:
  send the two non-monotonic decision-boundary tasks, the `16` pair-status-flip
  tasks, the `21` pair-choice-unstable tasks, and the `28` ranking-unstable
  tasks through independent-teacher and
  human review. Extend the redundant-call probe with measured latency and
  monetary cost. Also obtain a recorded human decision on the private six-case
  mapping. In parallel, start native-media acquisition rather than treating
  OCR/vision descriptions as media bytes.
- Real-key rule:
  use the configured credential aggressively through a governed lane. Formal
  acceptance calls require the verified identity gate. Exploratory calls
  require the explicit exploration fence, a non-retrying `create_run`, exact
  mapping/hash revalidation before mutation, resumable private journaling,
  per-test terminal verification, and public redaction. Never print, hash into
  public artifacts, or commit the key.

## Paid-call safety gates

Before a paid `create_run` batch is allowed:

1. `create_run` must be non-retrying or protected by a verifiable idempotency
   key;
2. the calibration dataset must match an explicit dataset ID, exact name, and
   canonical content SHA-256;
3. any missing or mismatched identity field must fail closed;
4. every submitted test must reach an individually verified terminal grading
   state;
5. public artifacts must contain no API key, authorization header, signed URL,
   private payload, or private evidence.

## Phase 1 -- Connect ReleaseFoundry safely

### 1. Eliminate duplicate charging from `create_run`

- [x] Real `create_run` execution is rejected unless automatic retries are
  disabled.
  - Python guard:
    `packages/sdk/releasefoundry/api_client.py::_require_zero_retries_for_mutation`.
  - TypeScript parity guard:
    `packages/ts/releasefoundry/src/api-client.ts::requireZeroRetriesForMutation`.
  - Verification:
    `python -m pytest tests/a1/test_api_client.py -k "create_run_requires_zero_retries" -q`
    passed (`1 passed`) on 2026-07-26.
  - Residual improvement: add a dedicated TypeScript regression test; the
    current acceptance condition is satisfied by fail-closed runtime guards in
    both SDKs and the Python behavioral test.
  - Paid calibration path:
    `scripts/a2_releasefoundry_live_calibration.py` requires dual explicit authorization,
    calls the verified-identity `create_run` wrapper exactly once, records the
    single mutation attempt, and never retries an ambiguous create response.
    Commit `5da678a` verifies this path together with the dataset gate.

### 2. Bind the calibration dataset by immutable identity

- [ ] External Bind a fixed dataset ID, exact dataset name, and canonical
  content SHA-256. Reject list-first selection, missing identity, and every
  mismatch.
  - Implemented:
    `services/judge/releasefoundry_dataset_identity.py` binds an explicit positive
    dataset ID, exact case-sensitive name, and canonical hash of
    `dataset_source`; mismatches, missing fields, duplicate IDs, and
    list-position fallback fail closed.
  - Live entry point:
    `scripts/a2_verify_releasefoundry_dataset_identity.py` fetches one explicit dataset
    ID directly through the official SDK. The private pin must remain under
    `docs/evidence/private_refs/`.
  - Fixed-six acquisition:
    `services/judge/releasefoundry_dataset_acquisition.py` now derives a deterministic
    request from the authoritative case map, scenario pack, and six run
    fixtures. Each case carries one stable ReleaseFoundry marker and a SHA-256 semantic
    contract; raw candidate answers are not copied into the request.
  - Mutation safety:
    `scripts/a2_acquire_releasefoundry_calibration_dataset.py` defaults to a zero-network
    dry run. A new request requires both `--execute` and `--allow-mutate`, calls
    official `create_request` once without retry, atomically stores the request
    ID only under `docs/evidence/private_refs/`, and supports read-only
    `--resume` after an interrupted collection.
  - Request binding:
    completed request polling uses a monotonic deadline; failed, timed-out, or
    unknown states block. Dataset discovery paginates with
    `include_signed_urls=false`, selects exactly one matching `request_id`, then
    fetches that explicit dataset ID and verifies exact name, six unique
    markers, six semantic contracts, source-run shape, and canonical content
    SHA-256.
  - Paid-run gate:
    `create_run_once_with_verified_identity` performs no paid mutation unless a
    current private verified manifest matches the deterministic request and a
    freshly fetched live dataset. It calls `create_run` once and never retries
    an ambiguous failure.
  - Live calibration consumer:
    `scripts/a2_releasefoundry_live_calibration.py` no longer reads
    `list_datasets.datasets[0]`. It requires the public acquisition receipt and
    private verified manifest to agree on request, dataset, content, contracts,
    case count, and canonicalization identity before the SDK client is created.
    A blocked, unreadable, malformed, stale, or mismatched receipt prevents
    network and paid execution. A non-empty legacy journal without an immutable
    dataset binding also fails closed.
  - Verification:
    `python -m pytest tests/a2/test_releasefoundry_dataset_identity.py
    tests/a2/test_releasefoundry_dataset_acquisition.py
    tests/a2/test_releasefoundry_live_calibration.py -q` (`89 passed` on 2026-07-27).
  - Real-API structure probe: all three currently visible datasets were fetched
    by ID with `include_signed_urls=false` on 2026-07-26; their stable content
    is under `dataset_source` with `dataset_type`, `runs`, and `total_runs`.
    Only field shapes and hashed identifiers were inspected.
  - Real request result on 2026-07-26:
    the existing paid request was resumed read-only, reached its completed
    server state, matched the exact bound request, matched the exact expected
    server dataset name, and returned exactly six runs using the official
    `multi_run_storyboard` type.
  - Fail-closed identity result:
    none of the six server runs retained the fixed A2 case marker or the
    semantic-contract SHA-256. The verifier therefore emitted
    `dataset_run_case_marker_missing`, kept
    `paid_create_run_allowed=false`, and did not call `create_run`.
  - Machine mapping result on 2026-07-27:
    `services/judge/releasefoundry_dataset_mapping.py` compared every fixed local
    semantic contract with every server run, then exhaustively evaluated all
    `720` one-to-one assignments. The best global assignment was unique. Every
    selected pair had at least two matched anchors and beat its case-level
    runner-up; the six proposed pairs also reproduce the expected scenario
    semantics.
  - Authority boundary:
    the mapping is only `machine_proposal_only` and
    `pending_human_review`. It explicitly sets
    `exact_identity_verified=false`, `human_adjudicated=false`,
    `paid_create_run_allowed=false`, `training_authority=false`, and
    `release_authority=false`. A unique machine assignment is useful evidence
    for a reviewer, but it is not human review and cannot complete item 2.
  - Public receipts:
    `docs/evidence/a2_releasefoundry_dataset_acquisition_receipt.json`.
    `docs/evidence/a2_releasefoundry_dataset_mapping_receipt.json`.
  - Official SDK boundary:
    the inspected `releasefoundry` `0.3.1` distribution exposes `get_dataset`,
    `list_datasets`, `create_request`, `generate_dataset`, and `create_run`.
    No API-key `create_dataset`, `import_dataset`, `upload_dataset`, or
    `update_dataset` method was observed in the wheel or current repository
    documentation. No undocumented endpoint was probed.
  - Remaining acceptance gap:
    exact fixed-six content identity cannot be proved from this generated
    server dataset. The immediate blocker is now
    `human_adjudicated_mapping_required`: completion requires a recorded human
    decision on all six proposed pairs, or an official import/upload path that
    preserves immutable case identity.
  - Do not create another generation request merely to replace this blocker,
    and do not weaken marker/hash validation to make the existing dataset pass.
    Acceptance-grade paid `create_run` batches remain blocked until exact
    identity is genuinely verified or the governed human-adjudication path is
    explicitly accepted for that purpose.

### 3. Complete the six core ReleaseFoundry cases

- [ ] Framework Complete real ReleaseFoundry scoring, human review, and evidence merge
  for all six core cases.
  - Existing: case map, import/merge validation, public/private evidence
    separation, and an independently retained public run-receipt artifact.
    Strict merge and readiness verify the receipt's canonical hash, exact
    six-case coverage, run-level fields, and per-test fields against every
    observation; observation metadata alone cannot satisfy the gate.
  - Missing: reviewed ReleaseFoundry grading observations `6/6`; current value is `0/6`.
  - Required state per candidate: action scores, final-answer score, total
    reward, rank, failure location, failure reason, receipt, and review decision.

### 4. Run the full 300-point perturbation matrix

- [ ] Framework Run every prompt and reference-answer perturbation point
  against the bound dataset.
  - Implemented:
    `scripts/a2_releasefoundry_live_calibration.py` deterministically generates `300`
    unique variants: `50` variants for each of the six fixed cases. The harness
    records resumable batches, per-attempt request metadata, latency, candidate
    identity, completion state, and a public-safe aggregate without exposing
    the private journal.
  - Safety:
    dry run is the default and performs no network or paid call. Real execution
    in the formal lane requires `--execute --allow-mutate`, the configured
    environment credential, and the complete item-2 identity gate. The separate
    non-authoritative exploration lane additionally requires
    `--allow-unverified-exploration` and revalidates the exact dataset,
    content hash, case-contract set, and unique mapping immediately before each
    batch. Each paid batch uses one non-retried `create_run`.
  - Verification:
    `python -m pytest tests/a2/test_releasefoundry_live_calibration.py
    tests/a2/test_releasefoundry_dataset_mapping.py -q` (`40 passed` on 2026-07-27);
    targeted Ruff also passed.
  - Real exploratory result on 2026-07-27:
    `300/300` unique variants were graded in six batches of `50`.
    All `300` tests reached a terminal outcome with server-side grading
    evidence. Exactly six `create_run` calls were made, with zero retries, zero
    HTTP errors, and zero duplicate terminal outcomes.
  - Acceptance boundary:
    the result is `exploratory_unverified_mapping`, is not human-reviewed, and
    explicitly grants no acceptance, training, release, or C3 authority.
  - Missing: `300` individually attributable terminal outcomes against an
    acceptance-authorized dataset mapping, followed by the required human
    review. Therefore item 4 remains unchecked.
  - Repeated or retried service records do not increase the unique case count.

### 5. Quantify ReleaseFoundry/local-judge agreement and bias

- [ ] Framework Produce the ReleaseFoundry-vs-local confusion matrix, per-failure-class
  agreement, false-pass/false-block rates, score deltas, and systematic bias
  analysis.
  - Existing: calibration matrix generator, offline comparison framework, and a
    preliminary machine-observed comparison from the exploratory `300`-point
    run.
  - Exploratory comparison:
    local expectations and ReleaseFoundry agreed on `265/300` outcomes. Against the local
    fixture labels, the machine confusion counts are `TP=50`, `TN=215`,
    `FP=35`, and `FN=0`; the apparent false-pass rate is `35/250 = 14%` and the
    apparent false-block rate is `0/50 = 0%`.
  - Systematic signal:
    text cases agreed on `250/250`; all `35` disagreements came from
    `sample-a2-s031-media-pipeline-unsupported-output`, including `5` image and
    `30` multimodal-channel variants. This may reflect an incorrect local
    expected label, ReleaseFoundry underweighting the media tool chain, expected-answer
    wording effects, or the fact that the current cases are text projections
    rather than native media.
  - Missing:
    human adjudication and acceptance-authorized ReleaseFoundry labels. The exploratory
    counts are useful for review prioritization but cannot serve as the final
    item-5 confusion matrix or system-bias claim.

### 6. Advance C3 from `partial` to `met`

- [ ] External Let the readiness generator advance C3 only after all required
  reviewed receipts are present.
  - Forbidden: manually changing a report or marker to `met`.
  - Current state: `partial`, reviewed ReleaseFoundry evidence `0/6`.
  - Engineering gate: the calibration matrix must retain
    `releasefoundry_run_terminal_receipt`, and readiness must independently validate its
    canonical hash, exact case set, run fields, and per-test bindings. A missing
    or forged receipt blocks `safe_to_mark_c3_met`.

### 7. Verify every server-side test completion

- [ ] Framework Poll and verify each test/candidate to its own terminal
  scoring state; do not rely only on a run-level aggregate marker.
  - Private receipt requirements: exact run/dataset/test identity, terminal
    lifecycle, ordered timestamps, non-empty response evidence, backend-specific
    grading evidence, and server-observed grader-version provenance.
  - Public receipt requirements: case-level status and evidence-kind counts
    only. Raw ReleaseFoundry identifiers, low-entropy identifier hashes, timestamps, raw
    response/result hashes, signed URLs, absolute local paths, and secrets are
    prohibited.
  - Implemented:
    `services/judge/releasefoundry_test_receipts.py` requires terminal `result.status`,
    treats an optional `grading_status` as a veto, and accepts only independently
    verified `completed` and `failed` tests with ordered timestamps, meaningful
    response evidence, and backend-specific grading structures such as
    `llm_judgment`, complete `argument_comparison`, or complete `coherence`.
    Client-populated `match_status` and `semantic_similarity` cannot prove
    server grading. Missing, duplicate, malformed, running, unexpected, or
    unidentified tests fail closed. Aggregate totals are recorded and a
    contradiction blocks the receipt, but aggregates never grant acceptance.
    Generic candidate `model_version` and operator attestation cannot satisfy
    grader-version provenance; conflicting server version fields also fail
    closed.
  - Strict import hardening on 2026-07-29:
    `scripts/a2_import_releasefoundry_grading.py --require-reviewed` and
    `--require-complete` now require both the fixed private dataset identity
    manifest and its verified public identity receipt, plus exactly one
    acceptance run. The receipt must bind the current manifest bytes, dataset ID
    hash, exact dataset-name hash, canonical content hash, content collection,
    and positive item count. The item count must equal the strict case map.
    Missing, blocked, stale, or mismatched receipts fail closed before
    observations are written. The importer also rejects a dataset-ID mismatch,
    multiple runs, a nonterminal run, missing server-observed grader provenance,
    and any missing, duplicate, unexpected, unidentified, malformed, or
    nonterminal test. Every imported case carries public-safe dataset identity
    provenance, a run receipt, and its own terminal-scoring receipt. A per-test
    summary alone is insufficient, and an aggregate marker is explicitly never
    acceptance authority.
  - Public receipt artifact binding on 2026-07-31:
    strict reviewed/complete imports now emit schema
    `a2.releasefoundry_grading_import.v2`, require the independent public run terminal
    receipt, and preserve it into the calibration matrix. The C3 readiness
    generator revalidates the artifact rather than trusting self-declared
    observation hashes or completion flags. Exact missing, duplicate, extra,
    malformed, nonterminal, run-field, and per-test-field mismatches all block.
  - Real identity acquisition check on 2026-07-29:
    the compensated free-plan key reached the live dataset discovery and
    verification flow through a read-only resume. It stopped at
    `dataset_run_case_marker_missing`; the visible server dataset does not yet
    satisfy the fixed six-case marker contract. No verified identity manifest
    or receipt was fabricated, no paid run was created, and C3 remains
    `partial`.
  - Current strict-import boundary:
    the existing real payloads still do not expose an immutable
    server-observed grader version, so they cannot produce a complete acceptance
    receipt. C3 therefore remains `partial`; this state must change only after a
    new authentic receipt passes the generator, never through a manual report
    edit.
  - Live entry point:
    `scripts/a2_verify_releasefoundry_test_receipts.py` polls one explicit `RELEASEFOUNDRY_RUN_ID`
    with the official SDK, binds it to the private dataset identity pin, writes
    raw identifiers only under `docs/evidence/private_refs/`, and emits a
    public-safe receipt without identifier or raw-payload hashes. It writes a
    blocked `verification_in_progress` receipt before network access so a stale
    verified receipt cannot survive a failed rerun. Polling uses a strict
    monotonic deadline, bounds each request timeout by the remaining budget,
    atomically replaces output files, and records only an exception type on
    read failure.
  - Real-API structure probe on 2026-07-26: ten visible runs were fetched
    read-only. Observed `result.status` values were `completed`,
    `completed_with_failures`, and `failed`; observed per-test terminal values
    were `completed` and `failed`. Backend-added evidence included
    `llm_judgment`, `coherence`, `argument_comparison`, `failed_actions`, and
    `divergence_notes`. `dataset_source.runs` was observed as an object keyed by
    run key, not a list. No mutating API call was made.
  - The hardened verifier was then exercised against the same account using the
    real credential and read-only calls only: `10` runs fetched, `8` runs with
    test records, `257` tests checked (`76` `completed`, `181` `failed`), and
    `8/8` runs satisfied the per-test terminal/scoring-evidence predicate.
    Full receipts remained `0/8` because every run lacked a server-observed
    grader version. No raw identifier or payload was persisted.
  - Exploratory calibration on 2026-07-27:
    all six paid batches were checked test by test. The `300/300` expected tests
    had unique terminal outcomes and backend grading markers; there were no
    missing, duplicate, unexpected, malformed, or nonterminal tests. The
    run-level aggregate was not used as a substitute for those checks.
  - Current API gap: the observed payloads did not expose an immutable grader
    version. An explicit `RELEASEFOUNDRY_JUDGE_VERSION` is labeled
    `operator_attested_not_server_observed` and cannot complete the receipt.
    Per-test terminal grading can therefore be machine-observed, but full
    provenance remains blocked until the service exposes verifiable grader
    identity. Machine observation is not promoted to reviewed evidence.
  - Verification:
    `python -m pytest tests/a2/test_releasefoundry_test_receipts.py -q` (`39 passed` on
    2026-07-26).
  - Remaining acceptance gap:
    the successful `300/300` verification belongs to the
    `exploratory_unverified_mapping` lane, and the service payload still does
    not expose an immutable server-observed grader version. No
    acceptance-authorized six-case run has produced a complete provenance
    receipt, so this item remains unchecked.

## Phase 2 -- Native multimodal evaluation

The current public generated-artifact probes are deliberately non-accepting.
The default `text/image/audio/file` request completed and verified ReleaseFoundry-generated
PNG and PDF bytes; a separate `text/audio` request completed and verified MP3
bytes. The team also reported an unsuccessful or unreliable video smoke on
2026-07-29, but no acceptance-grade receipt was produced; video therefore
remains `provider_unverified`, not proven supported or definitively unsupported.
These are generated dataset artifacts, not caller-uploaded native inputs, so
`accepted_modalities=["text"]`, `native_media_uploaded=false`, and
`media_upload_api_observed=false`. Commit `14f1330e` also prevents media words
in text from being counted as native media evidence. Items 8-21 therefore
remain unchecked.

The pinned `releasefoundry==0.3.1` surface receipt is now bound into evidence
readiness. It verifies one real-key, read-only `client.init()` and the existing
generated PNG/MP3/PDF receipts, but it does not expose a supported caller-native
upload or immutable media-URL path. Image, audio, and file therefore remain
`provider_surface_missing` for caller submission; video remains
`provider_unverified`. This receipt cannot mark items 8-11 complete or advance
C3 to `met`.

### 8. Native image inputs

- [ ] External Upload real images or submit immutable image URLs. Do not
  submit a prose description of what an image might contain.
  - Existing: one ReleaseFoundry-generated PNG has a verified byte receipt.
  - Missing: caller-native image submission and grading with region evidence.

### 9. Native audio inputs

- [ ] External Use real speech, noise, accents, silence, overlap, and
  multi-speaker audio files.
  - Existing: one ReleaseFoundry-generated MP3 has a verified byte receipt.
  - Missing: caller-native audio submission and grading with timestamp evidence.

### 10. Native video inputs

- [ ] External Use real frame sequences, temporal events, subtitles, audio,
  and audio/visual conflicts.
  - Current provider status: `provider_unverified`; video remains explicit
    opt-in and is not part of the default real-API smoke.

### 11. Native file inputs

- [ ] External Cover PDF, DOCX, XLSX, PPTX, CSV, HTML, archives, and corrupt
  files with native parsers and evidence references.
  - Existing: one ReleaseFoundry-generated PDF has a verified byte receipt.
  - Missing: caller-native document submission, the remaining formats, corrupt
    input behavior, and page/field evidence.

### 12. Five single-modality benchmarks

- [ ] Not started Build independent text, image, audio, video, and file
  benchmarks with at least `1,000` base cases per modality.

### 13. Cross-modal contradiction benchmark

- [ ] Not started Build at least `1,000` cross-modal cases, including
  image/text, audio/subtitle, table/body, and other evidence conflicts.

### 14. Temporal-reasoning benchmark

- [ ] Not started Build at least `500` cases covering video event order,
  audio context order, and cross-frame state changes.

### 15. Multimodal safety benchmark

- [ ] Not started Build at least `500` cases covering image prompt injection,
  subtitle injection, QR codes, hidden text, malicious documents, and metadata
  attacks.

### 16. Abnormal-input benchmark

- [ ] Not started Cover missing, corrupt, oversized, disguised-format,
  duplicate, and misordered inputs with explicit expected behavior.

### 17. Evidence localization

- [ ] Framework Every multimodal conclusion must point to page numbers,
  timestamps, frame numbers, regions/coordinates, or file fields.
  - Existing: signed artifact references and public-safe evidence contracts.
  - Missing: native media corpus and measured localization accuracy.

### 18. Tool-chain ordering

- [ ] Framework Verify required ordering such as acquire -> decode -> observe ->
  judge, including forbidden shortcuts and recovery behavior.
  - Existing: tool-policy/order judges and seed media pipeline cases.
  - Missing: acceptance-scale native-media coverage.

### 19. Repeated stochastic runs

- [ ] Partial Run every multimodal case at least three times and measure
  candidate-model and judge variance.
  - Completed: the `35` text-projected exploratory disagreements were rerun three
    times with exact dataset-bound test IDs (`105/105` observations); all
    `35/35` remained persistent machine disagreements.
  - Missing: three-run coverage for every native multimodal case and separate
    candidate-model variance measurements.

### 20. Five-party adjudication

- [ ] External Compare the same case through ReleaseFoundry, two strong-model judges, a
  local judge, and human gold review.
  - Teacher outputs are observations, not automatically the gold label.

### 21. Media-source train/test isolation

- [ ] Framework Split by original media source and near-duplicate family;
  prevent crops, transcodes, extracted frames, and derivative documents from
  leaking across train/test boundaries.
  - Implemented: every governed media artifact carries both an exact
    `content_hash` and a derivative-family `source_group_hash`. Single-file
    writes and loads reject either identity crossing dataset splits.
  - Corpus boundary: commit `83ee4c9` adds one verified multi-file loader that
    validates every path-free manifest and private JSONL before combining them,
    then reruns content-hash and source-family isolation across the whole
    corpus. Separate train/test files can no longer pass independently while
    leaking the same original media or a crop/transcode/derived member.
    Duplicate corpus paths and record IDs also fail closed.
  - Verification: preference-dataset tests passed `20/20`; the complete A2
    suite passed `1,417 passed, 2 skipped, 19 warnings`; all `57` generated A2
    fixtures match committed output.
  - Missing: populate the acceptance-scale native-media corpus with trustworthy
    source-family IDs and add media-specific near-duplicate discovery
    (perceptual image/frame, audio fingerprint, and document lineage) before
    this item can be checked.

## Phase 3 -- Judge distillation

### 22. Unified judge label

- [ ] Framework Standardize:
  `pass/fail`, failure type, severity, failed action, evidence location,
  confidence, calibrated probability, and release recommendation.
  - Existing local outputs already include pass/fail, failure class, score,
    confidence, rationale, and evidence references in several paths.
  - Preference-learning contract:
    `services/judge/preference_learning.py` now enforces canonical failure
    classes, severity, failed action, structured evidence location, confidence,
    action-level scores, final-answer score, overall reward, rank, immutable
    trace/final-answer hashes, model version, and verified receipt hashes.
  - Governed private training export:
    `services/judge/preference_dataset.py` joins a training-eligible pair to a
    separately governed private source bundle and emits distinct
    `reward_model_training`, `preference_optimization`, and
    `action_value_training` records. Human-gold preference remains authoritative
    when its direction conflicts with ReleaseFoundry reward.
  - Private-data controls:
    prompt/media/trace/answer hashes, content-addressed `cas://` media refs,
    consent/lineage/retention/deletion/authorization hashes, explicit dataset
    split, atomic JSONL persistence, path-free public manifests, and
    train/test source isolation are enforced. Secrets, authorization material,
    signed URLs, and private paths fail closed.
  - Unified cross-modality contract:
    `services/judge/unified_label.py` now emits
    `a2.unified_judge_label.v1` with one canonical binary label, primary and
    secondary failure classes, severity, failed action, typed evidence
    locations, confidence, failure probability, explicit calibration
    provenance, and exactly one of the six final release recommendations.
    Evidence locations cover text spans, image regions, audio intervals, video
    intervals and frames, document pages/fields/cells/slides/selectors/archive
    entries, and tool action/argument paths. Multimodal conclusions require
    evidence from at least two modalities.
  - Fail-closed invariants:
    pass/fail must agree with the 0.5 decision threshold; pass labels cannot
    carry failure metadata; failed labels require a canonical failure class,
    severity, failed action, and evidence. Uncalibrated probabilities cannot
    authorize `allow`; high/critical failures cannot recommend staged rollout;
    critical failures must recommend `human_review` or `block`. Secrets,
    signed URLs, private paths, malformed coordinates/ranges, and tampered
    evidence or label hashes are rejected.
  - Legacy adapter:
    `adapt_grade_result_to_unified_label` maps existing `GradeResult` records
    but deliberately requires the caller to supply evidence locations,
    probability-calibration provenance, release recommendation, and immutable
    input/output hashes instead of inventing them.
  - Verification:
    `python -m pytest tests/a2/test_unified_label.py -q` (`31 passed`),
    `python -m pytest tests/a2 -q` (`1006 passed, 2 skipped`), targeted Ruff,
    `git diff --check`, and fixture check passed on 2026-07-27.
  - Missing:
    all production judge paths still need to emit this schema directly, and
    item 26 must provide a real fitted calibration artifact plus held-out ECE
    evidence before student probabilities may be marked `calibrated`.

### 23. Human-adjudicated gold standard

- [ ] External Never copy ReleaseFoundry output directly into the teacher label. Resolve
  ReleaseFoundry/strong-model/human conflicts through recorded human adjudication.
  - Implemented guard:
    ReleaseFoundry alone can emit only `provisional_preference`;
    a local judge never counts as an independent external teacher; conflicting
    external teachers route to `review_required`; and only a complete reviewed
    human adjudication is labeled `human_gold`.
  - Optional non-gold path:
    a deployment may explicitly permit matching ReleaseFoundry plus an independent
    external strong-model teacher as `teacher_consensus`, but that authority is
    never relabeled as human gold and is disabled for training by default.
  - Dedicated `services/judge/preference_review_store.py` now keeps review cases,
    reviewer events, reviewer leases, independent arbitration, and authoritative
    resolutions separate from `a2_release_decisions`. Pair content hashes,
    tenant scope, lease generations, and `sha256:` reviewer receipts are checked;
    unresolved, conflicting, `abstain`, and `escalate` reviews produce no
    authoritative resolution and no training candidate.
  - A completed review produces `preference_authority = human_gold` and can feed
    `services/judge/preference_learning.py::build_governed_preference_pair`;
    `confirm` preserves the machine direction while `overturn` changes it.
  - Verification: `python -m pytest tests/a2/test_preference_review_store.py
    tests/a2/test_sql_store.py::A2SqlStoreTests::test_sql_schema_file_matches_python_contract -q`
    (`5 passed` on 2026-07-26).
  - Missing:
    real ReleaseFoundry/strong-model observations and recorded human adjudications for
    acceptance-scale samples; the current environment still has `0` such
    training-eligible pairs.

### 24. Six specialist student judges

- [ ] Not started Train and version specialist judges for text, tool calls,
  images, audio, video, and documents.

### 25. Multimodal fusion judge

- [ ] Not started Train a fusion judge for cross-modal consistency, aggregate
  risk, and final release recommendation.

### 26. Calibrated probabilities

- [ ] Framework Require calibrated probabilities in addition to binary
  labels and evaluate reliability diagrams, ECE, and class-conditional
  calibration.
  - Implemented:
    `services/judge/probability_calibration.py` builds and verifies
    `a2.probability_calibration_report.v1` from immutable calibration artifact,
    human-gold holdout, and per-case prediction records.
  - Metrics:
    fixed-bin reliability diagram, overall ECE, maximum calibration error,
    Brier score, negative log loss, class-conditional pass/fail ECE, and
    modality/severity calibration slices.
  - Qualification:
    the default gate requires `ECE <= 0.03`, at least `1,000` source-isolated
    held-out cases, and at least `100` pass and `100` fail cases. Artifact and
    holdout receipts must be verified; fit/holdout source-group overlap,
    incomplete or duplicate observations, binding mismatches, tampering,
    non-human gold, train-split manifests, private paths, and secrets fail
    closed.
  - Promotion boundary:
    a passing report explicitly sets
    `automatic_model_promotion_allowed=false` and
    `requires_blind_version_comparison=true`.
  - Verification:
    `python -m pytest tests/a2/test_probability_calibration.py -q`
    (`18 passed`), `python -m pytest tests/a2 -q`
    (`1024 passed, 2 skipped`), targeted Ruff, `git diff --check`, and fixture
    regeneration check passed on 2026-07-27.
  - Missing:
    a genuinely fitted student calibrator, a real source-isolated
    human-adjudicated holdout, verified fit/gold/isolation receipts, confidence
    intervals, and measured acceptance evidence. Therefore item 26 remains
    framework and item 34 remains external.

### 27. Uncertainty and escalation router

- [ ] Framework Route low-risk cases locally, uncertain/medium-risk cases to
  ReleaseFoundry, and high-risk or disputed cases to human review.
  - Implemented:
    `services/judge/uncertainty_router.py` emits
    `a2.uncertainty_route.v1` from a verified unified label, optional verified
    probability-calibration report, ReleaseFoundry availability/comparison state,
    external-teacher state, evidence completeness, scope/novelty flags, and
    historical-critical-regression status.
  - Three-tier route:
    qualified and confident low-risk cases use `local_judge`; uncertain,
    medium-risk, uncalibrated, out-of-scope, or novel cases use
    `releasefoundry_teacher` when available; high/critical cases, teacher conflicts,
    local/ReleaseFoundry disagreements, historical critical regressions, and missing
    evidence use `human_review`.
  - Outage boundary:
    ReleaseFoundry unavailability does not stop qualified in-scope local decisions, but
    every case outside that boundary remains `uncertain` and escalates instead
    of fabricating certainty.
  - Calibration safety:
    the router verifies report schema/self-hash, model and calibration artifact
    bindings, human-gold/source-isolation receipts, per-case observation
    coverage, and the original gate facts. Callers cannot qualify a model by
    weakening the minimum `1,000` cases, minimum `100` cases per class, or
    `ECE <= 0.03` threshold.
  - Paid-call boundary:
    an `releasefoundry_teacher` destination is a request for a separate governed
    acquisition path, not authority to spend. Every route explicitly records
    `paid_releasefoundry_call_authorized=false` and
    `requires_external_mutation_gate=true`.
  - Active learning:
    priority and reason codes include probability uncertainty, calibration
    gaps, local/ReleaseFoundry disagreement, teacher conflict, severity, historical
    regressions, evidence gaps, out-of-scope inputs, and novel failure types.
  - Release vocabulary:
    the route uses only `allow`, `staged_rollout`, `restrict_capability`,
    `retest`, `human_review`, and `block`.
  - Verification:
    `python -m pytest tests/a2/test_uncertainty_router.py -q` (`20 passed`),
    `python -m pytest tests/a2 -q` (`1044 passed, 2 skipped`), targeted Ruff,
    `git diff --check`, and fixture regeneration check passed on 2026-07-27.
  - Missing:
    probability thresholds measured from genuinely trained students, real ReleaseFoundry
    escalation receipts, a human-review SLA, cost/coverage measurements,
    release-orchestrator integration, and acceptance evidence that at least
    `80%` of ordinary cases resolve locally without unsafe guessing.

### 28. Active-learning acquisition

- [ ] Framework Prioritize paid labels for the highest local uncertainty,
  largest local/ReleaseFoundry disagreement, novel failure clusters, and high expected
  risk reduction.
  - Implemented:
    deterministic acquisition priority combines local uncertainty, local/ReleaseFoundry
    disagreement, external-teacher conflict, blocked ReleaseFoundry ordering, critical
    severity, and novel failure classes.
  - Verification:
    `tests/a2/test_preference_learning.py` covers provisional pairs,
    teacher consensus, teacher conflict, human override, tie/rank blocking,
    immutable scope enforcement, receipt verification, public-safety rejection,
    active-learning priority, and deterministic output.
  - Durable teacher acquisition queue storage and a dedicated preference-review
    destination are present; the design keeps provisional preference review out
    of `a2_release_decisions`.
  - Real ReleaseFoundry decision-boundary evidence now identifies two non-monotonic tasks,
    `16/35` pair-status-flip tasks, `21/35` pair-choice-unstable tasks, and
    `28/35` exact-ranking-unstable tasks as the next paid/human acquisition
    pool. The public source is
    `docs/evidence/a2_releasefoundry_decision_boundary_probe_stability.json`; it grants no
    training authority by itself.
  - `enqueue_preference_teacher_acquisition` now derives a request hash and
    idempotency material from the governed pair, teacher, and request payload;
    it uses the active-learning score, rejects blocked/training-eligible pairs,
    and never stores the raw request payload.
  - Verified public-receipt settlement binds the queue item, teacher, pair,
    request hash, and receipt hash. Incomplete or blocked receipts fail closed;
    verified replay is idempotent and tenant-isolated.
  - Verified-receipt dispatch opens a fenced human preference review only after
    every expected ReleaseFoundry test has independently reached terminal scoring and the
    public receipt has no missing, duplicate, unexpected, malformed, or
    nonterminal tests. An aggregate marker alone is never sufficient.
  - Dispatch explicitly returns
    `teacher_receipt_training_authority=false`,
    `human_review_required=true`, and
    `training_candidate_created_by_dispatch=false`; it cannot turn ReleaseFoundry output
    into human gold or create a release decision.
  - Verification:
    `python -m pytest tests/a2/test_teacher_review_dispatch.py
    tests/a2/test_preference_review_store.py
    tests/a2/test_releasefoundry_teacher_receipts.py
    tests/a2/test_teacher_acquisition_queue.py
    tests/a2/test_sql_store.py -q` (`32 passed` on 2026-07-27).
  - Missing:
    real paid-label scheduling, the six-case verified ReleaseFoundry receipt corpus,
    recorded human review outcomes, training-eligible human-gold pairs, and
    measured label-efficiency gains from the closed active-learning loop.

### 29. Production case-book feedback

- [ ] Framework Send every misclassification, complaint, and incident into
  the case book and generate a permanent regression case after review.
  - Implemented ingestion:
    `services/judge/production_feedback.py` accepts retry, abandonment,
    correction, complaint, misclassification, incident, and successful
    completion events under the complete five-field tenant scope. Public
    summaries and controlled private evidence references are separated;
    source-event and idempotency conflicts fail closed.
  - Implemented review:
    each feedback item can receive one canonical `accept`, `reject`, `abstain`,
    or `escalate` decision bound to the expected event hash, reviewer identity
    hash, reviewer receipt hash, and ordered timestamp. Review replay is
    idempotent; conflicting or cross-tenant review is rejected.
  - Implemented regression handoff:
    accepted failure feedback with a replayable case/scenario/fixture identity
    can automatically create one persisted `pending_owner_review` candidate.
    The candidate can enter the existing case-book path only after a separate
    canonical owner approval. Promotion verifies
    `source=incident_candidate`, `decision=approved`,
    `replay_input_approved=true`, a canonical reviewer receipt, and a positive
    review timestamp before accepting the candidate.
  - Replay integrity:
    case-book artifacts seal the exact calibration-matrix content, and replay
    seals and verifies the exact source case-book and source-matrix hashes.
    Readiness also deterministically rebuilds replay from the current matrix and
    case book before trusting replay readiness, maturity, counts, or case
    membership. Changing source content while keeping the same matrix or
    dataset ID, or rehashing an altered replay projection, fails closed.
    Reviewed external evidence also requires a newly validated binding to the
    retained C3 ReleaseFoundry terminal receipt or C4 semantic human-review receipt plus
    an exact source-content hash match. Self-declared receipt metadata,
    replaced receipts, replaced sources, and rewrapped artifacts cannot advance
    C5. C5 remains `partial` at maturity `seed`, replay coverage `1/3`, and
    reviewed external evidence `0/3`.
  - Governance boundary:
    ingestion, feedback review, and owner approval do not grant human-gold,
    training-eligible, permanent-regression, or reviewed-external-evidence
    status. A successful-completion event remains reward-only and cannot create
    a regression candidate.
  - Verification:
    `python -m pytest tests/a2/test_production_feedback.py
    tests/a2/test_casebook_safety.py tests/a2/test_sql_store.py -q`,
    `python -m pytest tests/a2/test_casebook_safety.py
    tests/a2/test_regression_replay_safety.py tests/a2/test_contracts.py -q`,
    followed by `python -m pytest tests/a2 -q`
    (`1,409 passed, 2 skipped`) and
    `python -B scripts/a2_regenerate_fixtures.py --check`
    (`all 57 A2 generated fixture files match committed output`) on 2026-08-01.
  - Missing:
    product adapters that continuously deliver real production events, recorded
    owner decisions for live incidents, and the reviewed external evidence
    required before a promoted case may be declared a permanent accepted
    regression.

### 30. Blind model-version comparison

- [ ] Framework Blind-test every student upgrade against the previous
  version and block promotion on regression; do not report only the new
  version's own score.
  - Implemented:
    `services/judge/blind_version_comparison.py` accepts exactly two anonymous
    run payloads and scores them before applying the separate immutable
    incumbent/challenger bindings.
  - Holdout integrity:
    both runs must bind to the same holdout manifest, dataset content hash,
    source-isolation policy hash, case IDs, fixture hashes, original source
    hashes, and prompt version. Missing, duplicate, extra, or mismatched cases
    fail closed.
  - Blindness and provenance:
    scoring inputs reject role and version identity fields; manifest, prediction,
    run, artifact, scoring-input, role-binding, and comparison hashes remain
    independently traceable.
  - Comparison output:
    paired deltas cover pass/fail accuracy, failure-class accuracy, critical
    error recall, erroneous release count/rate, per-failure-class detection and
    classification recall, score/probability movement, and historical critical
    regression detection.
  - Promotion boundary:
    identical versions or artifacts, any critical or per-class regression,
    increased false releases, newly missed critical cases, missing historical
    coverage, or a missed historical critical case block the challenger. A
    non-regressing challenger is only `eligible_for_human_review`;
    `automatic_promotion_allowed` is always `false`.
  - Verification:
    `python -m pytest tests/a2/test_blind_version_comparison.py -q`
    (`21 passed`), followed by `python -m pytest tests/a2 -q`
    (`975 passed, 2 skipped`) and
    `python scripts/a2_regenerate_fixtures.py --check` on 2026-07-27.
  - Missing:
    two genuinely trained immutable student versions, a source-isolated
    human-adjudicated held-out manifest, blind execution receipts from both
    versions, and a recorded human promotion decision. Until those exist, item
    30 remains framework rather than accepted.

## Phase 4 -- Final acceptance

### 31. Critical-error recall

- [ ] External Achieve critical-error recall `>= 98%` on a held-out,
  human-adjudicated benchmark.

### 32. False-release rate

- [ ] External Keep erroneous release/allow decisions `<= 0.5%`.

### 33. Human-gold agreement

- [ ] External Achieve overall agreement with human gold `>= 95%`.

### 34. Probability calibration

- [ ] External Achieve `ECE <= 0.03` on held-out data and report confidence
  intervals.

### 35. Local auto-resolution

- [ ] External Resolve at least `80%` of ordinary cases locally while
  reliably escalating the remainder instead of guessing.

### 36. Evidence-location accuracy

- [ ] External Achieve at least `95%` accuracy for image regions, document
  pages/fields, and audio/video timestamps.

### 37. Historical critical regressions

- [ ] External Maintain `100%` detection of all reviewed historical critical
  incidents.

### 38. End-to-end provenance

- [ ] Framework Trace every result to media hash, prompt version, judge
  version, model version, candidate/trace version, and original evidence.
  - Existing: result hashes, policy hashes, judge versions, signed artifact
    references, evidence snapshots, and append-only decision-ledger contracts.
    The C5 chain additionally verifies canonical owner-review provenance and
    binds case-book and replay artifacts to exact case-book and
    calibration-matrix content hashes. Reviewed evidence authority is derived
    from independently revalidated C3/C4 receipts and exact source-content
    hashes rather than copied case-book metadata.
  - New private training records preserve pair ID, source-bundle hash, media
    content/source-group hashes, dataset split, model version, trace hash,
    answer hash, ReleaseFoundry receipt hash, and governance lineage without exposing raw
    private content in the public manifest.
  - Missing: end-to-end native-media and trained-model lineage validation.

### 39. Closed release-decision vocabulary

- [ ] Framework The final release gate may output only:
  `allow`, `staged_rollout`, `restrict_capability`, `retest`, `human_review`,
  or `block`.
  - Existing: configurable release policy, fail-closed gate framework, and a
    hash-bound A3 consumer contract that exports exactly these six actions,
    normalizes approved legacy aliases, and rejects unknown actions.
  - Missing: enforcement across the remaining live judge, release-orchestrator,
    and product surfaces.

### 40. ReleaseFoundry outage behavior

- [ ] Framework Local students continue to operate when ReleaseFoundry is unavailable,
  but out-of-distribution, high-risk, or low-confidence cases return
  `uncertain` and escalate; they must never fabricate confidence.
  - Missing: trained local students, calibrated thresholds, outage/failure
    injection, and measured degraded-mode behavior.

## Required structured learning record

Every candidate used for ranking, preference construction, Reward Model
training, or DPO must be representable without losing the following fields:

```json
{
  "sample_id": "stable unique ID",
  "task": {
    "input_hash": "sha256:...",
    "prompt_version": "immutable version",
    "dataset_identity": {
      "dataset_id": 0,
      "dataset_name": "exact name",
      "content_sha256": "sha256:..."
    }
  },
  "evidence": [
    {
      "modality": "text|image|audio|video|file",
      "media_sha256": "sha256:...",
      "locator": {
        "page": null,
        "timestamp_ms": null,
        "frame": null,
        "region": null,
        "field": null
      }
    }
  ],
  "candidate": {
    "candidate_id": "stable unique ID",
    "model_version": "immutable version",
    "trace": [],
    "final_answer": {},
    "trace_hash": "sha256:...",
    "answer_hash": "sha256:..."
  },
  "teacher_observations": {
    "releasefoundry": {
      "action_scores": [],
      "final_answer_score": null,
      "overall_reward": null,
      "rank": null,
      "failure_location": null,
      "failure_reason": null,
      "receipt_hash": null
    },
    "strong_judge_a": {},
    "strong_judge_b": {},
    "local_judge": {},
    "human_gold": {}
  },
  "preference": {
    "chosen_candidate_id": null,
    "rejected_candidate_id": null,
    "adjudication_ref": null
  },
  "release": {
    "calibrated_probability": null,
    "uncertainty": null,
    "decision": "allow|staged_rollout|restrict_capability|retest|human_review|block"
  }
}
```

Raw private media and credentials must not be committed. Public records should
contain immutable hashes, public-safe metadata, and canonical private evidence
references only.

## ReleaseFoundry black-box distillation boundary

A2 may use the official ReleaseFoundry API as a paid teacher to learn its observable
reward behavior:

1. generate multiple candidate answers and tool traces for one bound task;
2. collect action-level scores, final-answer scores, overall rewards, rankings,
   failure locations, and rationales through official responses;
3. form reviewed `chosen` / `rejected` pairs;
4. train local reward, failure-classification, specialist, fusion, and
   action-value models;
5. optimize the execution model with a DPO-like preference objective;
6. route the largest local/ReleaseFoundry disagreements and highest uncertainty back to
   paid teachers and human review.

This is black-box value-function approximation, not a claim that A2 has
recovered ReleaseFoundry's private weights, hidden prompts, proprietary training data, or
internal implementation. ReleaseFoundry output is one teacher observation; when teachers
conflict, recorded human adjudication defines the gold label. Paid-call volume
may scale aggressively only after immutable dataset identity, non-retrying
mutation safety, per-test terminal receipts, privacy controls, and spend
attribution all pass.

## Five required A2 products

- [ ] Native multimodal human-gold dataset.
- [ ] ReleaseFoundry/strong-model teacher calls and evidence system.
- [ ] Local distilled judge ensemble.
- [ ] Uncertainty and escalation router.
- [ ] Release-blocking risk decision engine.

## Immediate execution order

1. [x] Convert the `35` exploratory media disagreements into a redacted,
   non-training human-review queue with stable variant hashes and explicit
   `pending` state.
2. [x] Repeat the highest-disagreement candidates at least three times through the
   fenced real-ReleaseFoundry exploration lane to measure judge variance. Preserve one
   non-retried `create_run` per batch and resume ambiguous outcomes by read-only
   lookup instead of resubmission.
3. [x] Generate multiple candidate answers and tool traces for the same fixed
   tasks, obtain ReleaseFoundry action/final/overall rankings, and store provisional
   `chosen`/`rejected` pairs as `training_eligible=false` until human review.
   - Completed with `35` tasks, `8` strategies, `3` positional repeats,
     `840/840` paid evaluations, `24` non-retried `create_run` calls, and
     `840/840` independently verified structure/final-answer receipts.
   - Outcome: `3` provisional task-repeat pairs and `102` blocked pairs; real
     training-eligible pair count remains `0`.
4. [x] Run the governed `action_value_probe` for tool choice, argument recovery,
   stopping, redundant post-success calls, unsupported answering, and
   trace/final-answer contradiction. Repeat the exact task set three times and
   aggregate only receipt-bound positional results.
   - Completed with `35` tasks, `8` strategies, `3` repeats, `840/840`
     evaluations, `24/24` non-retried mutation successes, and `840/840`
     independently verified structure/final-answer receipts.
   - The aggregate preserves `human_gold=false`, `human_reviewed=false`,
     `training_eligible=false`, `c3_transition_allowed=false`, and
     `release_authority=false`; authorized training pair count remains `0`.
5. [ ] Preserve the item-2 acceptance blocker while obtaining a recorded human
   decision on the private six-case mapping or an official fixed-dataset path
   that retains case markers and semantic contracts.
6. [ ] Finish item 7 against the first acceptance-authorized six-case run,
   including individually attributable terminal receipts and
   server-observed grader provenance.
7. [ ] Human-review and merge the six core cases, regenerate readiness, and allow
   the generator--not a manual edit--to decide whether item 6 can advance.
8. [ ] Start caller-native image, audio, and document inputs first. Keep video
   behind an explicit provider-capability probe until support is verified. The
   completed `300`-point text-projection experiment and the generated-artifact
   receipts must not be counted toward native multimodal scale or
   evidence-location accuracy.
9. [ ] Wire the existing blind comparison, unified labels, calibrated uncertainty
   routing, and production-feedback framework into the real release
   orchestrator and product event adapters before scaling paid labels.
10. [ ] Expand reviewed regression cases from `1/3` to at least `3/3`.

### Completed governed action-value probe

Use the same `35`-task source queue and immutable queue hash. Each repeat must
submit these eight candidate strategies without locally reordering the trace:

1. `reference_aligned`;
2. `premature_stop`;
3. `hallucinated_without_tools`;
4. `redundant_post_success_call`;
5. `recovered_argument_error`;
6. `recovered_wrong_tool`;
7. `contradictory_final_answer_after_tools`;
8. `severe_control`.

Run three independent labels. The planned paid volume is
`35 tasks * 8 strategies * 3 repeats = 840` evaluations through `24`
non-retried `create_run` calls. Read-only polling may retry; mutation may not.
Every source report must prove `a2-releasefoundry-live-v5`, positional alignment, exact
task-set and queue-hash consistency, per-test structure grading, per-test
final-answer grading, and public redaction. The aggregate must remain
`human_gold=false`, `human_reviewed=false`, `training_eligible=false`,
`c3_transition_allowed=false`, and `release_authority=false`. Any
`chosen`/`rejected` direction is provisional until recorded human review.

The completed aggregate confirms the strategy-level ordering above but exposes
two important paid-teacher calibration targets:

1. a redundant call after a correct successful trace loses only `12.5667`
   reward points on average;
2. stopping before the last required action while retaining the reference final
   answer loses only `18.9143` points on average.

The next paid sweeps must vary redundant-call count and cost, missing-action
count and severity, and contradiction severity. Threshold-adjacent cases must
be repeated rather than converted directly into preference labels.

### 2026-08-01 unblock-checklist authority hardening

- [x] Commit `264087bc` closes a release-control integrity gap in which a caller
  could clear a release gate's blockers, change the decision to `pass`, reseal
  the artifact, forge the C3/C4/C5 checklist summaries, and obtain
  `overall_status=ready`.
- [x] A non-blocking (`pass` or `warn`) checklist now requires the current
  commercial-readiness, evidence-readiness, calibration-matrix, case-book,
  regression-replay, scenario-selection, A1 evidence-index, and judge-registry
  sources. The release gate is deterministically rebuilt from those sources
  and its artifact hash must match before the checklist can be ready.
- [x] The fixture generator and internal release-unblock service both supply
  the authoritative source set. Request-provided forged summaries cannot
  replace the service's current source artifacts.
- [x] The attack is preserved by
  `test_unblock_checklist_rejects_resealed_forged_ready_gate`.
- [x] Verification after the patch: `1411 passed, 2 skipped, 19 warnings`;
  all `57` generated A2 fixture files match committed output; `git diff
  --check` passes.
- [ ] This integrity fix does not advance C3, C4, C5, or C6. Their real
  external-evidence and maturity requirements remain unchanged.
- [ ] Team smoke observations currently indicate that the compensated free
  ReleaseFoundry key can reach image, audio, and file paths, while video is unreliable.
  These observations are not independently retained per-test terminal
  receipts, do not prove caller-native media ingestion, and therefore grant no
  multimodal acceptance or release authority. Video remains
  `provider_unverified` / `uncertain`.
- [x] No paid or compensated API call was needed for this deterministic
  authority-boundary patch; making unrelated calls would not test the fixed
  exploit. Real-key calls remain reserved for receipt-producing calibration
  and native-media probes.

### 2026-08-01 C3/C4 acceptance-source reconstruction

- [x] Commit `0fa45d4d` closes a second integrity gap: a caller can no longer
  flip `safe_to_mark_c3_met` or `safe_to_mark_c4_met`, recompute the report
  hash, and have the re-sealed evidence-readiness artifact accepted.
- [x] Every acceptance-ready C3/C4 artifact must now bind the current
  calibration matrix, batch plan, semantic harness, and ReleaseFoundry case map. C4
  additionally requires the exact semantic collection packet.
- [x] The verifier reconstructs the C3 ReleaseFoundry public-merge gate and C4 semantic
  live-merge gate from those authoritative sources and rejects any field-level
  mismatch with the report. A valid wrapper hash is no longer treated as proof
  that the enclosed acceptance decision is true.
- [x] Commit `d53d5db9` passes the same authority set through commercial
  readiness and fixture generation. Eligible C3/C4 evidence can still advance
  only when the deterministic reconstruction succeeds; missing authority
  remains fail-closed rather than silently downgrading verification quality.
- [x] The internal release-unblock service reads the authority files from the
  server's current fixture set. A request cannot substitute a forged batch
  plan, semantic harness, case map, or semantic collection packet.
- [x] The attack regression is preserved by
  `test_artifact_rejects_resealed_forged_acceptance_gates`.
- [x] Verification after both patches: `1412 passed, 2 skipped, 19 warnings`;
  all `57` generated A2 fixture files match committed output; targeted
  authority tests passed `93/93`; secret scan and `git diff --check` pass.
- [ ] This proves only acceptance-source integrity. It does not create a real
  six-case ReleaseFoundry grading receipt, human review, native-media acceptance,
  training-eligible preference pair, or release authority. C3 and C4 remain
  `partial`.

For every independent patch: run targeted tests, run
`python scripts/a2_regenerate_fixtures.py --check`, run `git diff --check`,
scan staged files for secrets/private payloads, commit, and push immediately.
