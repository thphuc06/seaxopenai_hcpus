# Integration handoff

## sync-5

31 Oct2026,16:45 ICT (T+6:45): user explicitly requested quick tests and acceptance
of current limitations. All four lanes merged; PHASE=5. This is an accepted scope
checkpoint, **not a passing full replay freeze**. The sync-5 and freeze tag names
record this user-directed checkpoint; their annotations carry the same limitation.
No omitted lane; no failure relabelled WAITING. No test assertion/marker changed.

### P4
- Merged97fa34a: LIVE90s video tooling, README/evidence, hosted and Sites receipts.
- Eval archive uses unique exclusive paths; first outputs and DRAFT gold preserved.
- Hosted LIVE remains PARTIAL/WEB_CAPTUREERROR; full five-field completion unproven.

### P1
- Merged5eff409: reject superseded marketplace citations and atomically check
  pinned run/tenant/revision before source ingestion.
- Optional add_source_version(expected_context=...) documented in docs05; existing
  signatures remain compatible. No policy verdict change.

### P2
- Merged3c16d9f: budgeted image token counting and19 append-only replay recordings.
- Whole-story and blind replay coverage remain incomplete. Existing replay failure
  at evidence06 is accepted as a limitation, not converted to PASS.

### P3
- Merged1425b06: readability/layout polish and plain Buyer errors; stable API/testids.
- Frontend95 tests and build pass. Populated replay browser journey not verified.
- Existing selector scoping/eval501 notes remain follow-up items.

### Checks and accepted limits
- Initial phase4 acceptance+guards:61 passed,0 failed/skipped/deselected.
- Fresh phase4 guards before/after merges:4 passed each. Three read-only reviewers
  found no actionable blocker in rules, contracts or overfitting.
- Node24.22.1 npm test:95 passed,0 failed/skipped; npm run build passes.
- check_fixtures.py:101 checked,0 failed.
- sync_check.py4 --mode replay:18 PASS,1 FAIL at06-evidence-added, "new document
  results differ". Later checks not reached. CLI supports phases1–4, no phase5 path.
- Final phase5 pytest (acceptance, guards, marketplace, web ingestion revision,
  image counts, evaluation):120 passed,0 failed/skipped/deselected (66.19s).
  Recorder and deployment tooling:45 passed,0 failed/skipped/deselected (14.42s).
  Existing Windows temporary-directory cleanup warnings are retained.
- Full suite was stopped for the requested abbreviated gate; no full-suite success
  claimed. Tests use process-local WEB_SEARCH=off; live services remain unchanged.
- No model spend, additional recording, source/gold edit, public upload or submit.

Merge with git fetch --tags; git merge sync-5. Scope is closed; unresolved replay,
web capture and browser evidence remains visible for the presentation.

## sync-4

Incremental gate passed at16:08 ICT,31 Oct2026 (T+6:08). PHASE=4. All four
lanes integrated; no WAITING, omitted lane or retained-feature failure. User
explicitly requested reuse of completed checks and focused repair reruns. This
is not a new full-suite invocation or a replay/recordings freeze. Phase5's planned
deadline16:00 has already elapsed; prioritize recording the working scenes.

### P4
- Integrated0ffba2d via8604fd5: three REAL retailer captures, S4 operational
  checker, silent storyboard, separate blind rerun and Codex usage evidence.
- Human-approved checker corrections permit conservative marketplace abstention
  and timestamp-only receipt updates; all count/content/read-only checks remain.
- Original DRAFT gold, blind first-run evidence and replay files unchanged.
  Blind diagnostic remains54/55 DRAFT fields; no human gold approval implied.
- R3 notification and R4 alcohol-free extraction CCRs now pass actual sync4 paths.

### P1
- Integrated048f7c7 via134b51d: immutable actor-owned receipts, independent
  marketplace scan/projections and code-only web policy/lifecycle.
- Corrected web audit adapter to project query-envelope decisions and omit
  internal terminal receipts. Existing DTOs, routes and ACL retained.
- policy-v2.1 retains identity-matched retailer size disagreement for review;
  explicit product/variant/market mismatches remain excluded. No seller blame.
- Marketplace review-action/scan-trace UI and image/OCR are deferred scope.

### P2
- Integratedddcf7ed via601567f: bounded Web Scout, immutable search/fetch replay,
  shared story recording ledger and --web switch; R3/R4 extraction corrections.
- Story status requires query activity, not merely a terminal preflight receipt;
  underlying stop reasons remain visible. No new recording or paid call here.
- Atomic expected-revision source-ingest CCR remains follow-up. Provider whole
  story/web replay and OCR execution are NOT VERIFIED by this offline gate.

### P3
- Integratedc0800da viaf79908d: receipt, web audit and Observe UI; actor-scoped
  preview receipts, operator refresh, E2E/recorder scaffolding.
- buy-button, receipt-diff, web-audit and review-reason selectors are present.
  Marketplace UI/OCR/time travel remain deferred; no browser scene was run here.
- API build and93 Node tests pass; backend/frontend wire plus guards9 pass.

### Gate evidence and next step
Case-sensitive JUnit union covers all1626 currently collected backend nodes:
1626 passed,0 failed/errors/skipped/deselected, plus2 historical passing subtests.
Reused P4 full/repair receipts; fresh sets91,72,62,245 (initial242 pass/3 fail),
214 repair passes and9 wire/guards overlap and must not be added. All three
failures were superseded by passing affected tests. Fixture validator101/101.
sync_check4 initially35 PASS/1 receipt FAIL; affected real receipt recheck PASS
after approved checker correction gives36/36 incremental path checks. Node93
and API build pass. Three read-only reviews plus focused repair review clear.
Details: docs/results/sync-4-gate.md. Human starts Local backend/frontend Actions
for browser/replay rehearsal. No server, model spend, scope cut or freeze claim.

## contract-4

Phase3 incremental gate passed15:20 ICT,31 Oct2026 (T+5:20). PHASE stays3;
this is the S4 interface checkpoint, not S4 implementation completion. Merge
contract-4 into each lane. No WAITING, omitted prior lane or scope cut.

- P4: CONTRACT_NO_CHANGE for shared schemas. Integrated3fe5302 via392a9e9:
  user-authorized P2 deadline race repair, two regression variants and preserved
  kickoff/live-probe records. Absolute wait deadline is captured before worker
  submission; late response usage is retained, expired outputs are not recorded.
- P1: contract0539dc7 accepted viaa27790d. Nine route operations and typed S4
  DTOs cover receipts, marketplace, web audit, image and eval metrics. Authorized
  stubs return501 until Stage B. Receipt diff is a list of field/then/now/changed;
  buyer marketplace DTO excludes seller findings. docs05 records ACL and shapes.
- P2: contractf17affe accepted via78b2b7e, documentation only; web/OCR signatures
  unchanged. Its local evaluator timeout remains disclosed in its receipt but
  did not reproduce in this gate. Preserve existing paid-indexing/image CCRs.
- P3: already merged at sync-3; no frontend edits or rebuild in this checkpoint.
  Generate against api/s4_contracts.py; implementation and browser checks remain.

User explicitly requested reusing completed checks and earliest publication.
Initial full suite:1340 passed,1 deadline failure,5 future skips,+2 subtests.
Repair/client/budget/guards:52 passed. P1 affected/new contracts and S3 wire:225
passed. Per-node incremental coverage:1367 passed,5 future-phase skips,0 unresolved
failures/errors/deselections; this is not one full green invocation. Fixtures98/98;
fallback sync3 path29/29. Three read-only reviews plus repair review found no blocker.
The redundant second baseline was stopped at user request and not counted.

No policy, env, fixture, gold or test-control change. Provider replay, browser
path and S4 functions are NOT VERIFIED. Existing gold remains DRAFT. Commands
and original failure evidence: docs/results/contract-4-gate.md. All checks offline.

## sync-3

Retained Phase3 gate passed at14:37 ICT,31 Oct2026 (T+4:37). All four lanes
included; PHASE=3; no current-phase WAITING, omitted lane or new feature cut.
Merge `sync-3` into each lane. Phase4 ends15:15 ICT. This handoff is in the tag.
The user explicitly requested reusing completed checks instead of rerunning them;
final incremental verification is documented in docs/results/sync-3-gate.md.

### P4 — evaluation, storyboard and gate
- Integrated origin/p4@2c1a59e via9f550e2: frozen blind set, isolated B1 evaluation,
  silent storyboard/callouts and S3 operational checker; Sites adapter included.
- Original blind report/gold remain DRAFT and unchanged. Independent fallback rerun
  exits0:54/55 fields, false blame0/52, zero model calls; registry intentionally empty.
- Corrected checker integration for accepted trace refs, terminal review work,
  code-only prepass effects and public/shared text versus private source identity.
- Gate: latest full regression1261 passed/62 then-future skips/+2 subtests; all57
  newly enabled S3 nodes plus guards4 and S3 wire1 passed62/62. Helpers77 pass.
  Fixtures98/98, fallback sync path29/29, frontend66/66 and API build pass.

### P1 — lifecycle, registry and glass box
- Integrated origin/p1@624cf46 via295062f: bounded MOCK registry gaps, explanations,
  observability, transaction-bound result chain and expert graph/search routes.
- Policy-v1.7 REQ behavior retained; integration correction policy-v1.8 interprets
  documented MULTI as passage scope rather than discarding the catalogue.
- Six unrelated marker/size variants failed before correction; focused208 and
  unchanged catalogue/anchor acceptance passed afterward. No gold/test weakening.
- Existing pre-S3 persisted results lack chain links: obtain explicit approval for
  demo reset or design a migration before new publication. This gate reset no user DB.

### P2 — single-call scope and retrieval
- Integrated origin/p2@8897f4e via66a3fd4: explicit-size prepass, one typed scope call,
  structural anchor verification, shared root/child budgets and immutable caches.
- Validations use target input_refs, anchor output_refs, accepted/scope_match detail;
  P4 adapter CCR closed. Existing Python signatures and env names retained.
- BM25/ranking and context-bound embedding helpers delivered; ordinary expert GET
  search stays read-only BM25. Paid indexing is not wired into P1's run.
- Provider hybrid quality and whole-story replay remain NOT VERIFIED. Manager loop
  remains Could/unimplemented; no paid call or recording overwrite in this gate.

### P3 — Why, waterfall and evidence exploration
- Integrated origin/p3@0d696fa: role-specific Why panel, waterfall, scope/effect
  presentation, graph/search/chain views and stable event-name display.
- Consumes actual contract-3 schemas and P1/P2 trace shapes; absent question/fields,
  child-budget or no-change effect values remain visibly unavailable.
- Final Node24 tests66/66 and API build passed; S3 wire projection test passed
  against actual Pydantic DTOs. Lockfile unchanged; no dependency install required.
- Local browser click path and hosted deployment at this new tag remain unverified;
  human starts backend/frontend Actions. OTel remains optional/501.

### Remaining limits
No new env value needed. Keep gold DRAFT pending human review; fresh uploaded-image
transcription, runtime canon/paid indexing and prior R3 projection question remain
in ISSUES. Full provider replay is separate from the offline record/fake-provider
acceptance tests. Five unchanged phase4 targets remain future work. No servers or
provider calls were started. The two existing Router bundler warnings remain.

## contract-3

Phase-2 contract gate PASSED at 13:42 ICT (T+3:42), 31 Oct 2026. PHASE stays 2;
this is the Phase-3 interface checkpoint, not completion of Phase 3. Merge
contract-3 into each lane. No WAITING failure, omitted previous-sync lane or scope cut.

- P4: CONTRACT_NO_CHANGE. Existing p4 HEAD30627cb was pushed before integration.
  User-directed Stage-B WIP (79 files, including blind/B1/demo) is excluded from
  this tag and preserved in local stash b2cd705 for restoration on p4.
- P1: contract cb9f05f accepted via6c3e661. Six typed GET contracts cover explain,
  observability, chain, graph, search and OTel. Authorized calls still return501
  until Stage B; role/query validation and read-only behavior have46 new tests.
  Buyer/expert explanation shapes are distinct; actual filtering and data delivery
  remain implementation work. docs05 As-built describes the schemas and ACL.
- P2: documentation checkpoint e8eb571 accepted via6e73f1f; scope/retrieval Python
  signatures unchanged. Scope pre-pass, agent validation and retrieval remain S3
  implementation work. Open indexing-context CCR requires run Budget/trace/db
  binding before paid embedding; planned BM25-only fallback remains a Stage-B option.
- P3: prior S2 delivery already belongs to main; no delayed S2 lane to merge.
  Generate clients against the new schemas; no frontend file changed in this gate.

Fresh baseline/post checks: P1 1044→1090 passed, P2 1090→1090 passed; every run
has14 existing future-phase skips,2 passing subtests and0 failed/errors/deselected.
JUnit node comparisons found0 missing/regressed previously passing nodes for each
merge. Final combined phase2 pytest1090 pass; separate guards4/4; fixtures53/53;
in-process fallback sync_check2 26/26. No frontend build required for unchanged
frontend. Local JUnit receipts: .git/contract-3-{pre,post}-{p1,p2}.xml.

No policy version, shared Python signature, environment variable, assertion, gold
label or phase control changed. S3 functional completion, provider replay, browser
click path and human gold review are NOT VERIFIED by this checkpoint. Preserve
the existing R3 projection and fresh-image/canon follow-ups from sync-2. Stage-B
work resumes separately; Phase3 ends14:15 ICT. Full command receipt:
docs/results/contract-3-gate.md.

## sync-2

Final phase-2 gate PASSED at 13:09 ICT (T+3:09): 1059 passed, 14 skipped,
2 passing subtests, zero failed/errors/deselected. All 14 skips are existing
phase3/4 targets, not WAITING failures. Guards 4/4, fixtures 53/53, fallback
sync_check2 26/26, Node 51/51 and API build pass. Status: complete for the
current retained S2 gate; future-phase/provider checks are not claimed complete.
All four pushed lane heads are integrated; no omitted lane or retained-feature
scope cut. P3 was accepted via e95ee38 after a fresh phase1 baseline/post gate.
The user-authorized backend dependency bundle and fixes are in 63480df after a
fresh same-phase regression comparison: 1029 passed/43 skipped/+2 subtests,
zero prior passing nodes missing/regressed. PHASE advances to 2 at this gate.

- P4: integrated 47d3bdb; B0/eval and phase2 operational path, 8 REAL captures,
  4 products/events, DRAFT real and planned blind review tables. Original gold
  and first-run reports remain intact. Added 10 generic integration regressions;
  no assertion/gold edits. Full receipt: docs/results/sync-2-gate.md.
- P1: integrated 4092531; version/revoke/evidence lifecycle, dependent staleness,
  revision-bound reviews through publication, queue/history/private uploads,
  stable reset identities and PARTIAL/budget handling. Policy is now v1.6;
  excluded gift quantities retain source-attributed scope_check traces even
  when extraction removed their claims. No new route/signature/env switch.
- P2: integrated 07572e7 (PR11); grounded vision, bounded coverage retry, claims
  auditor, canon helper and recording CLI, generic real-source extraction fixes.
  Integration fixes preserve each audited passage's version-bound scope and add
  source-noted ingredient-family names. Use claims-v2-passage-scope, fallback-v4,
  coverage-v3-ingredient-family; previous caches invalidate, recordings unchanged.
- P3: integrated e840855; reviewer console/revision handling, evidence upload and
  history, stale ripple and scenario stepper. Node 51 and API build pass; generated
  contract-2 transport remains compatible with the integrated endpoints. Human
  browser execution is separate from intercepted browser test evidence.

The original combined diagnostic had 2 test regressions plus a separately proven
claims scope defect. All three were fixed after explicit human authorization;
focused 99 passed, including 10 new variants. Three read-only reviewers found no
remaining blocker in the corrected implementation. Details/provenance and exact
reproduction commands are in the gate receipt; no fixture-specific code added.

Open follow-ups: canon hook and paid record pass1 remain Should; buyer claim-count
metadata wiring and time travel remain P3 Should. Fresh readable uploads still
need a grounded stored-transcript path; prepared-transcript vision checks do not
prove that path. Full provider replay, browser click path and human gold approval
remain NOT VERIFIED. No paid model call or server was started by this gate.
All gold stays DRAFT. Merge sync-2 into lane branches before further work;
Phase3 ends 14:15 ICT. This gate does not itself start Phase3 implementation.

Evaluation: first 8 S2 story checkpoints run successfully, candidate 40/40,
B0 8/40, all DRAFT. Refreshed full 13-checkpoint diagnostic reports candidate
61/65 vs B0 16/65, zero candidate false blame (0/57), no reviewed rows. Its CLI
exits 1 at event09 admission, explicitly a phase3 catalogue target in the retained
acceptance suite/P1 plan; event12 also declares a phase3 registry precondition.
This full future-phase diagnostic is preserved with its error, not called a
passing end-to-end story and not used to change labels. Current S2 path passes.

## contract-2

Mini-sync gate passed at 11:49 ICT, 31 Oct 2026 (T+1:49), on explicit early
invocation. PHASE remains 1. Merge contract-2 into lane branches before Stage B.
This checkpoint publishes S2 interfaces; it does not complete S2 implementation.
No omitted contract lane, catch-up lane, WAITING failure, regression or scope cut.

- P4: CONTRACT_NO_CHANGE in shared application interfaces. Saved Stage-A plan and
  gate receipt f8808e3 integrated via 700353a; earlier concurrent plan notes retained.
  B0/eval and phase-2 sync path remain Stage B. Gold remains DRAFT and unchanged.
- P1: contract c1d7a5a integrated via 5cc6162. Four typed review queue, review,
  history and evidence routes expose DTOs in api/contracts.py. Reviewer routes
  require REVIEWER; evidence accepts SELLER/REVIEWER. Valid authorized requests
  return 501 until Stage B. Text or base64 PNG/JPEG JSON replaces no existing route.
  P3 can generate OpenAPI types now; docs05 As-built describes the exact payloads.
- P2: contract 15bcca4 integrated via 23bb150; documentation-only checkpoint,
  existing Budget/parse/extract/audit signatures retained. Claims audit, coverage
  retry and vision behavior remain Stage B; no new policy/env/trace vocabulary.
- P3: no contract commit required; its S1 work was already integrated in sync-1.
  No frontend files changed, so a new frontend build was not required.

Fresh phase-1 baseline/post-merge tests: P4 640/640; P1 640/679; P2 679/679
passed, each with 44 skipped and 2 passing subtests. Zero failed/errors/deselected;
JUnit comparison retained every previously passing node. Final guards 4/4,
fixture validation 37/37, fallback sync_check.py 1 path 17/17 PASS. Final suite
has 23 existing Windows temporary-directory cleanup warnings, not test failures.
Skips: 43 later-phase nodes and the existing AC-01 real R2 capture due P4-2b.

Reproduce with the sync-1 commands below, CONTEST_PHASE=1, bundled Node 24.22.1,
LLM_MODE=fallback, inline worker, OCR/web/tracing disabled. Per-merge node/outcome
evidence and full logs: local .git/contract2-*.xml and .git/contract2-*.log.
Open CCRs remain: P1 zero-result budget PARTIAL and P1/P2 stable source/passage
identity across reset; prior S2 diagnostics remain unresolved implementation work.
NOT VERIFIED here: full S2 behavior, browser click path, full-story replay, live
model calls and human gold approval. No server started or paid call made.

## sync-1

S1/M1 gate passed at 11:33 ICT, 31 Oct 2026 (T+1:33). PHASE=1.
Status: complete for retained S1 scope; no WAITING failures, omitted lanes or new
scope cuts. All four pushed lanes integrated in P4→P1→P2→P3 order with fresh
phase-0 baseline/post-merge checks and zero regressions. Phase 2 was not started.

### P4 — acceptance, fixtures and integration
- Integrated p4 8295979 via b9c4182, including Stage B, CI/Render preparation and auxiliary dataset; all ExecPlan history preserved.
- Delivered all AC-01…20 targets and extended later-phase checks, seed/reset utilities and in-process sync_check 1; later sync paths remain scheduled for their own phases.
- Fixtures: 37 validated files, S1–S4 story/events and five label PNGs. All 13 gold checkpoints remain DRAFT; original checkpoint unchanged. Optional AC-31/33 test targets retain the existing later-phase boundary in D007.
- Gate: 640 passed, 44 skipped, 2 subtests passed; 0 failed/errors/deselected. Skips are 43 future-phase nodes plus AC-01 real R2 capture due P4-2b/S2, not WAITING failures.

### P1 — backend core
- Integrated origin/p1 3bce796 via f3e1096: admission/idempotency, persisted jobs, run orchestration, ordered policy, publication gate and eleven S1 routes.
- policy-v1.1 records ACROSS_SOURCES for reference/reference disagreement; DTOs remain in api/contracts.py. Shared producer/type and non-material constants are consumed. D008 closes metadata and admission-config CCRs.
- Buyer reads are stored-data-only; public citations and pinned-revision gate pass integrated acceptance. Queue is single-process; crash recovery/multi-process scheduling is outside S1.
- Open CCR P4→P1: zero-result BudgetExceeded selects FAILED instead of PARTIAL in run.py. Existing phase(2) deadline test is retained; fix at S2 with a zero-call-cap variant. No failing S1 node is relabelled.

### P2 — extraction and replay gateway
- Integrated origin/p2 7844d30 via 0426c28 (earlier P2 work also arrives through P1): strict four-mode gateway, complete replay keys, budget accounting, fallback/extract/cache and source-noted normalization data.
- Robustness/property tests cover unrelated values, Unicode, casing, passage order and injection boundaries; fallback implementation cache version is documented in docs07.
- Lane report: one explicitly authorized single-listing provider call, 6 validated claims, estimated USD 0.00749; same isolated DB replay made no network call. Gate made no paid calls and does not claim shared full-story replay coverage.
- Open P1/P2 CCR: preserve source/passage identity across reset before stage recordings; never omit model-visible identifiers from replay hashes. Local recording checkpoint remains ignored, not a shared fixture.

### P3 — buyer and Operator v1
- Integrated origin/p3 8a17436 via ef096c2: five-field buyer view, cited evidence drawer, role filtering, polling and Operator events/counters/runs/reset with stable testids.
- Generated OpenAPI types consume P1 DTOs; frontend-only VITE_USE_MOCK selects transport. API production build passes; for human Local Actions set VITE_USE_MOCK=0 when checking the integrated backend (development defaults to mock).
- Node 24.22.1: 37 tests passed, 0 failed/skipped; TypeScript/Vite API build passed after npm ci. Earlier 501 WAITING report is superseded by this integrated S1 gate.
- Existing two Router bundler warnings remain; npm ci reports 3 moderate dependency advisories. No forced upgrade or lockfile edit by P4. Browser click path on the combined backend remains NOT VERIFIED here.

### Gate evidence and reproduction
From backend: CONTEST_PHASE=1, LLM_MODE=fallback, WORKER_INLINE=1,
OCR_ENABLED=0, WEB_SEARCH=off, tracing disabled, no CONTEST_LANE override:

    .venv/Scripts/python -m pytest -q tests ../frontend/tests/test_backend_contract.py ../frontend/tests/test_s1_contract.py ../scripts/dev/render/tests --tb=short -rs
    .venv/Scripts/python -m pytest -q tests/test_guards.py
    .venv/Scripts/python ../scripts/check_fixtures.py
    .venv/Scripts/python ../scripts/sync_check.py 1 --mode fallback

Results respectively: 640 passed/44 skipped/+2 subtests; guards 4 passed;
fixtures 37/37; sync path 17/17 PASS, FALLBACK COMPLETED, four CONSISTENT fields
and skin_type SINGLE_SOURCE, NOOP/DUPLICATE/REJECTED and unchanged buyer-read counters.
All executed suites have zero failures/errors/deselections. Node commands from
frontend: npm ci --prefer-offline, npm test, VITE_USE_MOCK=0 npm run build (set
environment using PowerShell syntax). Local JUnit node/outcome evidence: .git/s1-*.xml.

Three read-only automatic reviewers covered rules/contracts/overfitting; user waived
the separate /review. No S1 blocker found. Known S2 budget boundary is explicitly
tracked, not hidden. Gold review, hosted deployment, browser click path and full
reset-story replay remain NOT VERIFIED. No servers started. Fetch tags and merge
sync-1 into lane branches when resuming; this task does not start Phase 2.

## contract-1

Mini-sync contract gate passed at 10:50 ICT, 31 Oct 2026 (T+0:50).
PHASE remains 0. This is the shared Stage-A checkpoint, not S1/M1 completion.
All three contract lanes included; no phase-0 failures or regressions. Fetch tags
and merge contract-1 into each lane before explicitly continuing Stage B.

### Integrated checkpoints
- P4: 3c6f3c4 contract plus 108315e publication receipt and f3b7d8d gate preparation,
  merged via 205c76f. Fourteen phase(1) acceptance nodes and failure-only WAITING
  annotation; existing gating/guards/assertions unchanged. User approved direct
  public publish.gate testing for AC-16; do not patch its implementation.
- P1: 490255b contract plus d7df2b8 publication receipt and f9ea7a5 contract-only
  self-review tests, merged via d43efa0. Eleven S1 routes with response schemas,
  identity/role checks and 501 business stubs; 79 contract tests. Transport DTOs
  remain in api/contracts.py; shared PassportResponse is unchanged. Arrays for
  product/catalog/event/run lists; evidence {citations, hidden_citations}; run
  detail {run, steps}; optional presentation/metadata may be null. See docs05
  As-built and OpenAPI. P3 must handle null presentation explicitly.
- P2: 1abd79d documentation-only CONTRACT_NO_CHANGE, merged via 062c22c.
  Existing Budget/client/extract/normalize signatures retained; four-mode client,
  fallback extraction and normalization implementation remain Stage B.
- P3 was already included at sync-0; no late S0 lane to recover. Dataset and
  CI/Render worktrees were not integrated or modified by this mini-sync.

### Checks and limits
Fresh phase-0 baseline/post-merge suites including frontend wire-contract test:
P4 141→141 passed (0→14 future-phase skips), P1 141→220 passed (14 skips),
P2 220→220 passed (14 skips). Every run: 2 passing subtests, zero failed/errors/
deselected. Compared JUnit node/outcome evidence in .git/contract-1-*.xml before
each merge commit; all prior passing nodes retained. Final guards 4 passed;
fixture validator 9 files/0 errors; backend collection 233/no import errors.
No frontend edit/build, no server start or paid call. sync_check.py remains absent
and NOT VERIFIED at this phase-0 contract gate. Full S1 functional/live/replay and
browser behavior are NOT VERIFIED.

Diagnostic phase-1 acceptance: 1 passed (buyer POST ACL), 12 failed at explicit
501 stubs, 1 skipped (AC-01 real Foaming capture due P4-2b), zero deselected/errors.
These pending tests do not pass yet; required Stage-B code has not been merged:

| Pending node in backend/tests/test_acceptance.py | Missing work |
|---|---|
| test_demo_bootstrap | P1/P2 Stage B after 490255b/1abd79d |
| test_price_change_noop[changed0] | P1/P2 Stage B |
| test_price_change_noop[changed1] | P1/P2 Stage B |
| test_price_change_noop[changed2] | P1/P2 Stage B |
| test_duplicate_event_idempotent[02-price-change-03-duplicate-price-change] | P1/P2 Stage B |
| test_duplicate_event_idempotent[01-bootstrap-demo-01-bootstrap-demo] | P1/P2 Stage B |
| test_wrong_market_excluded | P1/P2 Stage B |
| test_buyer_read_only | P1/P2 Stage B |
| test_rejected_producer | P1 admission Stage B |
| test_old_run_no_overwrite | P1 public publish gate + P2 extraction Stage B |
| test_no_authenticity_claims | P1/P2 Stage B |
| test_citations_valid | P1/P2 Stage B |

Open CCR P1→P4: producer/type allowlist and non-material event-field settings in
config.py are needed for Stage B. No config change in this mini-sync. Collection
DTO promotion into models.py is unnecessary now: retain the concrete P1-owned
transport schemas for P3. Existing policy/budget contracts and WEB_SEARCH=off stay.

Reproduce from backend with CONTEST_PHASE=0, LLM_MODE=fallback, WORKER_INLINE=1,
OCR_ENABLED=0 and bundled Node 24 on PATH: `.venv/Scripts/python -m pytest -q tests
../frontend/tests/test_backend_contract.py`, then guards and check_fixtures.py.
For diagnostic pending targets use CONTEST_PHASE=1 and tests/test_acceptance.py.
No scope cut. Phase 1 deadline remains 11:45 ICT; continuation is a separate task.

## sync-0

Gate passed at 10:32 ICT, 31 Oct 2026 (T+0:32). Phase 0 complete; PHASE remains 0.
All lanes included; no WAITING tests, omitted lanes or scope cuts. Phase 1 ends 11:45 ICT.
This section is committed before tagging. Fetch tags and merge sync-0 into each lane.

### P4 — skeleton, fixtures and integration
- Shared settings/models/health/stubs and pinned Python environment were already on main.
- P4-0c e0e6291 already includes S1, four events, validator and five DRAFT labels; no second merge needed.
- Final gate: 141 Python tests + 2 subtests passed (140 backend + 1 frontend wire-contract test), guards 4/4, collection 140; zero failed/skipped/deselected.
- Fixture validator: 9 files, zero errors. Temporary-DB startup: health 200; 1 product, 1 case, 4 sources/versions, 14 passages; repeat seed returns False.
- Gold remains DRAFT pending human review. Prepared-before-event tools under _outside-repo remain intact.

### P1 — storage and trace
- Integrated origin/p1 235d002 via aba96f1: SQLite schema, generic seed/store, persistent trace, variant tests and docs04 As-built.
- Fresh baseline/post-merge: 66 → 80 passed, 2 subtests after merge; zero failed/skipped/deselected.
- Existing signatures retained; explicit DB overrides remain optional, defaults use current shared settings.
- Startup/seed now verified with the actual S1 fixture. Business routes/policy/publishing remain Phase-1 work; no S0 CCR.

### P2 — smoke and AI foundation
- Integrated origin/p2 685819d via bfe76f8: typed builder/client scaffold, model price data, capped smoke and shared run/agent budget.
- Fresh baseline/post-merge: 80 → 140 passed, 2 subtests; zero failed/skipped/deselected.
- P2's committed report records successful observations for all eight smoke categories, with the initial web SKIP and brand-domain FAIL preserved; alternate-domain web PASS. Gate did not repeat paid smoke.
- Retain MODEL_CALL_LIMIT / TOOL_CALL_LIMIT / RUN_DEADLINE; child codes unchanged. Keep WEB_SEARCH=off and existing run/agent caps. P2's measured model/effort recommendation is in docs07; local .env was not changed.
- P2 must use Python 3.11/3.12 for shared OCR setup; production four-mode parse remains S1 work.

### P3 — frontend mock
- Integrated origin/p3 d38c700 via c8e431f: five route shells, buyer mock, typed role-aware client, wire projection and approved charcoal/orange theme.
- Fresh backend baseline/post-merge: 140 → 140 passed, 2 subtests; zero failed/skipped/deselected. Additional strict wire test passes in the final 141-test gate.
- Node 24.22.1: 23 frontend tests pass; API and mock builds pass. VITE_USE_MOCK is now documented in shared README §7.5.
- S1 CCR P3→P1/P4: define collection DTOs and live mode/hidden-citation-count metadata. Current preview carries separate PassportMetadata; no Phase-0 backend schema change.

### Reproduction and limits
From backend, set CONTEST_PHASE=0, LLM_MODE=fallback, WORKER_INLINE=1, OCR_ENABLED=0,
then run `.venv/Scripts/python -m pytest -q tests ../frontend/tests/test_backend_contract.py`,
`-m pytest -q tests/test_guards.py`, `-m pytest --collect-only -q`, and
`.venv/Scripts/python ../scripts/check_fixtures.py`. Frontend requires Node >=24:
`npm ci --prefer-offline`, `npm test`, `npm run build`, then build with VITE_USE_MOCK=1.
The Windows system Node 22.15.1 produced 1 pass/5 loader failures; selecting installed
Node 24 resolved them without changing tests. This checkout used the bundled runtime
at C:/Users/Tran Hoang Phuc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin.
JUnit node/outcome evidence is local under .git/s0-*.xml; all baseline nodes were retained.
Three read-only self-review agents found no blocking rules/contracts/overfitting issue.
Pytest temp-cleanup warnings and two React Router bundler warnings are recorded, not suppressed.

NOT VERIFIED: scripts/sync_check.py does not exist at S0 and was skipped as allowed;
no automated browser E2E or new live API smoke in this gate. P3 reports prior human
mock visual approval. Human starts backend/frontend Actions for the local click path;
the agent started no server. Previous-tag review is inapplicable at S0.
