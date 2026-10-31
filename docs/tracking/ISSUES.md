# Integration issues

| Item | Owner | State | Next action |
|---|---|---|---|
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
