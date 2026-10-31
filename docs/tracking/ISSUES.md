# Integration issues

| Item | Owner | State | Next action |
|---|---|---|---|
| REAL source scope inference | P1/P2 | P4-2b handoff; exposed by local merge | AC-01 returns UNCERTAIN because REAL snapshots omit inferred scope by design. Implement documented primary-size/identity/market inference in owner code; do not add scope to source fixtures or weaken tests. |
| R3 ingredient/concentration projection | P4/P1/P2 + human decision | Open P4-2b CCR | Both sources list the ingredient; only brand states 2%. Preserve AC-04 and DRAFT label until the shared field-versus-claim decision is made. See docs/results/p4-2b-review.md. |
| Shared HTML cleaning helper | P2 | Open P4-2b handoff | Reuse scripts.capture_page.clean_html(html, *, section_end_markers=SECTION_END_MARKERS); P2 retains fetch, ACL, Budget and trace responsibility. No runtime integration in the local merge task. |
| S2 replay mode storage | P1/P2 | Observed by retained phase(2) acceptance | test_record_replay_story_and_model_isolation[offline-record-model] expects REPLAY in runs.llm_mode; current storage is replay (API normalizes). Reconcile documented persistence contract in owner work; no P4 assertion change. |
| S2 diagnostic story | P1/P2 | Owner BUILD not integrated into contract-2 | P4 eval emits execution errors for rejected events06/09/10; sync_check2 fails at revoke after17 S1 passes. Preserve 16 acceptance failures in P4 plan; implement owner lifecycle/review/vision/audit/retry before full S2 gate. |
| B0/candidate preliminary report | P4 human | DRAFT only | Review source-grounded labels independently; report51/65 vs16/65 includes unmet story/Phase3 conditions and shared extraction. No gold changed to match output. |
| S2 evidence-request history status | P1 | Stage B integration CCR, contract-2 review | Existing publish.py stores CLOSED; new EvidenceRequestResponse allows OPEN/FULFILLED. Reconcile explicitly in history implementation and test a closed request; 501 stubs have no current serialization failure. |
| Storage/seed integration | P1 | S0 complete | Actual S1 startup 1 product/1 case/4 sources/4 versions/14 passages |
| Model IDs, prices and budget tuning | P2 | S0 report integrated | Keep measured recommendation/current caps; production client at S1 |
| Initial source dataset and validator | P4-0c | Completed, checks pass | P1 checks seed integration at S0 |
| Story expected labels | P4 human | DRAFT | Review all 13 checkpoints and cited passages in fixtures/gold/dev/demo-story.json; original checkpoint preserved |
| Local environment Actions | P4 | File configured; UI unverified | .codex/environments/environment.toml follows installed app schema; human checks menu |
| Remove missing-storage startup guard | P4 | Closed S1 | P1 modules required at startup |
| Collection DTOs and live mode/hidden-count metadata | P1/P4 (P3 CCR) | Closed S1 | P1 typed DTOs consumed by P3 generated schema and adapters |
| Root budget stop-code names | P4 (P2 CCR) | Closed S0 | Retain existing tested names; README/P2 prompt aligned |
| Frontend mock switch documentation | P4 (P3 CCR) | Closed S0 | VITE_USE_MOCK documented in README §7.5 |
| P2 OCR environment | P2 | Before OCR | Use shared Python 3.11/3.12 instead of 3.14 |
| Local Node selection | P4 | Checks resolved | Use Node >=24; bundled 24.22.1 passed, system 22.15.1 is too old for tests |
| Shared admission constants | P1/P4 | Closed S1 | P1 consumes config.PRODUCER_EVENT_TYPES and NON_MATERIAL_FIELDS |
| Reset/record/replay identity | P1/P2 | Open before stage recordings | Random source/passage IDs after reset change exact replay hashes; preserve identity without omitting model-visible input from the hash |
| Budget exhausted before first result | P1 | Open S2 CCR from automatic S1 review | run.py status selection must return PARTIAL on BudgetExceeded even with zero published fields; retain test_run_deadline_starts_no_model_call and add zero-call-cap variant |
| Frontend dependency audit | P3/P4 | Observed S1 | npm ci reports 3 moderate advisories; no forced upgrade or pin change in gate |
