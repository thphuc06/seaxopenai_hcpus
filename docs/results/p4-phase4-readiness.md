# P4 Phase4 handoff after contract-4

Local branch `p4`, base `9f55d9e` (`contract-4`), 31 October 2026. This is P4's handoff, not a sync-4 gate or a claim that all S4 implementations are integrated. No sync-gate or phase-control change was made in this task.

## Integration and preserved evidence

Fetched origin/tags and confirmed Local already contains contract-4 and origin/p4 repair `3fe5302`. Reviewed the P2 absolute wait-deadline correction and its two late-response usage/no-recording regression variants. Those files are unchanged in this task. Integrated the independent worktree's scoped patch/new files and appended its complete milestone to Local's existing ExecPlan. Stage A, mini-sync, live-probe and Sites history remain intact. The worktree remains an unmodified recovery copy of its handed-off work.

All139 original protected files match the Stage-A SHA256 manifest byte-for-byte, including gold DRAFT, blind inputs/freeze/first reports and Sites. The independent blind rerun remains separate: field metric54/55 DRAFT, false blame0/52, zero model calls. Case08 has a scored concentration-claim miss; case09 remains unscored. No human gold approval or model-output-derived label change.

## Delivered P4 work

- `scripts/sync_check.py 4 --mode fallback|replay` retains S1–S3 and checks captured cases14–17, fresh receipt-before-revoke, actual stored snapshot hash/public content/immutability, then/now diff, duplicate/read-only behavior, marketplace buyer/expert projections and cluster/value coverage. Explicit zero-evidence fields are allowed without invented values. Web audit reads are typed/role-filtered/read-only; WEB_SEARCH=off means discovery is NOT VERIFIED by that read.
- New offline HTTP transport tests cover bad run linkage/mode/status, wrong product, rewritten/lying receipt data, hash mismatch, collateral/omitted/wrong diffs, duplicate work, buyer leaks, omitted/duplicate marketplace field/value tallies and valid unavailable fields. The user explicitly approved changing only the old unsupported-phase test input4→5; exit-code2 assertion is retained.
- `scripts/codex_stats.py` and report count logged receipts/commits with explicit limitations; true session counts, skill invocations and unique findings remain unknown. Runtime/script chronology excludes setup, tests and phase-control-only commits.
- Capture supports optional `--output-dir` without bypassing identity or immutable writes. Generic review/comment DOM blocks are excluded by cleaner-v2, covered by unrelated fixtures. Nine attempted URLs yielded three retailer sources; four-to-five target remains incomplete. Current Mint input is `fixtures/marketplace/REAL-PROD-R1/listing-e13e06b174d7.v2.json` (36 passages). Original v1 (78 passages, including reviews) is byte-preserved in `docs/results/capture-archive/mint-listing-e13e06b174d7.v1.json`, outside scan inputs. Mint contains multiple/differing size lists; Insidefresh includes another formula section. P1 must scope individual evidence; do not treat whole-page text as exclusively the target variant.
- Silent storyboard has exact fixture sequence and source-backed S3 selectors, with S4 insertions explicitly pending. The live-probe report confirms an actual provider scope effect, but does not supply a whole-story replay recording. Narration stays `{}`.

## Validation

Focused helper/guards gate before review:108 passed. Review corrections:127 passed. Final zero-evidence-field positive variant plus affected capture/guard checks:87 passed. These overlap and must not be summed. All final focused checks0 failed/errors/skipped/deselected. Fixture validator101/101; diff/filename-only secret scans clear. Frontend untouched, so no build is required.

Full effective-phase4 suite: **1409 passed,2 failed,3 errors,+2 passing subtests,0 skipped/deselected**,446.84s. All five nonpassing nodes are the retained `needs(P1,P2)` S4 owner dependencies listed below. No P4 failure is relabelled as WAITING. This suite started before final review corrections; the127/87 focused receipts verify those later changes and are reported separately. Original logs/JUnit are under `.git/p4-s4-full.*`, final affected-code receipt under `.git/p4-s4-review-addendum.xml`. Three read-only self-reviewers checked rules, contracts and generalization; all reported P4 findings are resolved and rechecked. No claim of one all-green S4 invocation.

| Node in backend/tests/test_acceptance.py | Outcome | Missing owner work |
|---|---|---|
| test_receipt_preserves_purchase_then_reports_revoke | failed | P1 POST/orders implementation;501 |
| test_marketplace_clusters_without_changing_passport | failed | P1 marketplace scan implementation;501 |
| test_retailer_disagreement_never_blames_seller | setup error | P2 app.connectors.websearch module and P1 run integration |
| test_web_queries_and_fetches_are_bounded | setup error | Same missing P2 connector/P1 integration |
| test_web_without_identity_is_confirm_only | setup error | Same missing P2 connector/P1 integration |

Actual fallback sync4 returned31 PASS/5 FAIL: S1–S3 all29 pass, real R1/R2 pass; R3 identifier-read and R4 alcohol-free audit fail; receipt/marketplace/web-audit routes return501. This remains a failed operational path, never a passed S4 gate. Whole-story replay is absent and was not replaced by fallback. P3 `scripts/e2e.py`/`record_demo.py` are absent from the integrated checkout, so they were not run.

## Owner dependencies and CCRs

CCR P4→P1/P2: S4 implementation behind contract-4 · need: deliver receipt/marketplace/web workflows and run retained five phase4 acceptance tests · why: authorized S4 routes still501 and provider connector is absent in this checkout · snippet: preserve `api/s4_contracts.py`, implement behind the existing typed responses. Do not classify a green contract check as an implemented workflow.

CCR P4→P2: `backend/app/data/vocab_seed.json` field-label recognition · need: source-noted recognition of the captured notification header family, with unrelated-number variants · why: R3 run `run_ad7db476bff7402b9740d8c75f65c207` reads responsible_company but no notification_number claim; stored listing `specs#25` contains its notification header/value. First divergence is extraction after MATCH scope, not publication. Repro proposal: extract a passage `Số Giấy công bố: 891234/26/CBMP-QLD` and require a cited notification_number claim, without hardcoded identifiers or published verdict. Keep missing-document INSUFFICIENT behavior and the separate ingredient/concentration gold question unchanged.

CCR P4→P2: `claims_audit._outer_negation` / enumerated free-from statements · need: distinguish outer negation from independent list clauses · why: R4 run `run_7998d628840243b7922cdbac7d10a79d` has only treatment audit, no alcohol-free finding. Listing description#p29 carries a list of absent substances. `_outer_negation` removes known free-from phrases then sees negation remaining in the soap/color clauses and rejects the whole sentence. Repro proposal: `Alcohol-free, no soap, no dyes.` should retain the positive alcohol-free proposal; an unrelated negative variant such as `not alcohol-free` must remain rejected. Code policy still decides any finding; no new verdict is requested from the model. The separately excluded 400ml reference is not by itself a defect.

CCR P4→P3: Reviewer reason/decision inputs need `review-reason` / `review-decision` testids. Deliver S4 web-audit/receipt selectors and E2E script before claiming final recording readiness. Keep scene9 cut-first/conditional; do not select by visible text. No other lane's source file was edited for these needs.

## Delivery boundary

**P4 lane publication authorized at15:36 ICT**, with the five explicit owner-WAITING nodes and two real-case CCRs above. Target is origin/p4; publication is confirmed only when its SHA matches the committed checkpoint. Existing unchanged checks are reused. No automatic main merge, tag or sync-gate. Full S4 remains dependent on owner implementations, P3 UI/E2E and R3/R4 diagnostics; do not hide these failures or mark phase complete. Original source/gold/results, deadline repair and complete Sites/ExecPlan histories are retained.
