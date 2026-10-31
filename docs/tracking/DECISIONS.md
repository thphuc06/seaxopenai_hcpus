# Contest decisions

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
