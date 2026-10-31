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
