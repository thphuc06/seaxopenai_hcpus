# Contest decisions

## D010 — S2 contract checkpoint (11:49 ICT)
Publish contract-2 early on explicit invocation, without advancing PHASE=1 or
claiming S2 completion. P1's four typed S2 routes remain side-effect-free 501
stubs with role/schema validation; docs05 describes the text/image JSON upload.
P4/P2 shared application contracts are unchanged. No scope cut or gold edit.
Retain the prior separate /review waiver and run three automatic read-only
reviews. Record the OPEN/FULFILLED API versus CLOSED storage integration note
for P1 Stage B in ISSUES; gate-time code or test changes are unnecessary.

## D001 — Start authorization
At 09:49 ICT the user confirmed organizers permit implementation now. Start P4-0;
retain the published milestone schedule until the team changes it.

## D002 — Python compatibility
Use Python 3.11/3.12 for the shared environment. RapidOCR 1.4.4 declares Python <3.13;
the initial pip check on 3.13 failed. Local environment uses 3.11.1.

## D003 — Shared contract choices at S0
Settings attributes are snake_case; environment keys are uppercase. Relative paths
resolve against backend/. Reload updates the settings object in place. Model IDs
are empty pending P2 smoke; price absence is reported as `price unknown`.
Health returns `llm_mode`, `models` (extract/agent/cheap/embed), `policy_version`,
`phase`, `demo_run_delay_s`; no secret or database path is returned.
ClaimFinding inherits FieldDecision until S2 specifies any additional expert fields.
RuleStep.detail is text; trace detail remains JSON as specified by README section 7.3.
These decisions make previously unspecified wire details explicit for consumers.

## D004 — Phase boundary
P4-0 publishes skeleton then tooling on main. It does not merge other lanes or tag
sync-0. P4-0c and the S0 gate remain separate tasks.

## D005 — S0 vocabulary and operating configuration (10:32 ICT)
Retain tested budget codes MODEL_CALL_LIMIT / TOOL_CALL_LIMIT / RUN_DEADLINE and
AGENT_MODEL_CALLS / AGENT_TOOL_CALLS / AGENT_DEADLINE. README §7 and P2 prompt now
agree; no runtime behavior or assertion changed. This closes P2's root-code CCR.
Keep existing run/agent caps and WEB_SEARCH=off; use P2's measured model/effort
recommendation in docs07 when configuring live work. No local .env change at this gate.

## D006 — Frontend environment and S1 metadata (10:32 ICT)
VITE_USE_MOCK=1|0 is browser-only, now in shared README §7.5. Frontend tests require
Node >=24; this host's bundled 24.22.1 passes, system 22.15.1 fails TypeScript loading.
Use a process-local PATH selection; no global upgrade or dependency pin change.
S1 collection DTOs and live mode/hidden-count metadata remain P1/P4's CCR from P3.
No scope cut at S0; retain all current tests and DRAFT gold awaiting human review.

## D007 — P4 Stage B support and test boundaries (11:08 ICT)
The authorized CI/Render branch is merged into p4 with both ExecPlan sections
preserved. No deployment or paid persistence is created. Admission data lives in
config.PRODUCER_EVENT_TYPES and config.NON_MATERIAL_FIELDS (docs05 section 1);
P1 continues role checks. Storage is now required at app startup, since S0 merged it.
The sync CLI supports the S1 path in fallback/replay only, uses a temporary DB,
checks observed run mode/status, and rejects unimplemented later-phase paths.
Phase remains 0 until the separate S1 gate.

All AC-01…20 test targets and concrete extended contract targets are authored.
Optional AC-31 vocabulary lifecycle and AC-33 web-image OCR targets await their
Phase-2/4 payload/provider contracts; no existing test or retained feature was cut.
AC-18 API asserts run failure/no invented findings; existing field label precedence
is preserved. P1/P3 must add the run-level update-failure notice or agree a later
precedence change. Record/replay tests restore the same pre-run source IDs; stable
identity across demo reset remains a P1/P2 CCR before stage recordings.

## D008 — S1 integrated policy and resolved contracts (11:33 ICT)
Record P1's implemented policy-v1.1: reference/reference disagreement has locus
ACROSS_SOURCES; listing/reference disagreement remains LISTING_VS_SOURCE, and
within-source disagreement retains precedence after access/validity/scope checks.
This records the already implemented and tested rule (docs06 As built), not a new
gate-time policy edit. P2 remains the normalization owner.

The S1 collection DTOs and live mode/hidden-count metadata are implemented in
P1 api/contracts.py and consumed by P3's generated types. P1 consumes P4's shared
admission constants; these CCRs are closed. P3 implements the failed-update notice.
Keep random source/passage identity across reset as an open recording-stage CCR.

## D009 — S1 scope and review boundary (11:33 ICT)
User requested automatic review and waived the separate /review turn. Three
read-only reviewers cover rules, contracts and overfitting. No Phase 2 kickoff.
No retained S1 feature is cut; AC-01 waits for the already scheduled S2 real capture,
and future-phase tests retain their original markers. All gold remains DRAFT.
The review found a P1 Phase-2 boundary issue: zero-result budget exhaustion selects
FAILED rather than PARTIAL; track it explicitly, preserving the existing phase(2)
deadline assertions. Full run-budget hardening remains scheduled for S2.
