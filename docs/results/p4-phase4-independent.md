# Phase4 independent evidence — before mini-sync

Baseline e0a8e3b (sync-3 included), isolated worktree `p4-phase4-independent`. This report is separate from first-run evidence and from the concurrent Local contract gate. No S4 completion claim.

## Blind diagnostic

Fallback rerun `8f9c683e34bd46abae5f7b316e5f13d1` completed on 31 October 2026, 15:07 ICT. Candidate DRAFT 54/55 fields, B0 8/55, false seller attribution 0/52; zero model calls. REVIEWED remains 0/0. See [rerun report](blind-set1-rerun-8f9c683e34bd46abae5f7b316e5f13d1.md).

The ingredient field miss remains CONSISTENT expected versus SINGLE_SOURCE actual, with `mapping_unavailable` probe: a validated mapping is a planned precondition that fallback does not supply. Separately, case08's concentration claim is scored and misses: expected SINGLE_SOURCE, actual UNCERTAIN. Case09's concentration claim is unscored pending reviewed applicable regulatory data. The54/55 metric covers fields, not claim accuracy. None of these outcomes authorizes altering labels or app rules. Registry corpus is intentionally empty and does not test discovery coverage. Existing gold, freeze manifest, first JSON/Markdown report and first-run summary remain unchanged. Only baseline_b1 replay is present in this checkout, so whole-set replay is NOT VERIFIED and was not attempted as though recordings existed.

## R5 capture review, before any scan

Nine public retailer URLs were attempted with the existing HTTPX fetch/clean/identity pipeline. Three REAL LISTING snapshots are retained. This is short of the planned four-to-five usable pages; do not manufacture missing sellers or count blocked pages as evidence. No marketplace scan has run. New captures are outside the case in `fixtures/marketplace/REAL-PROD-R1/`; they are not new gold or claims about product quality.

| Retailer | Capture result | Stated size and skin type / locator |
|---|---|---|
| [Picare](https://picare.vn/san-pham/sua-rua-mat-danh-cho-da-thuong-den-da-kho-cerave-hydrating-cleanser-236ml) | `listing-09bc033ec583.v1.json`, REAL | title: 236ml and normal-to-dry; description#p2 explicitly states 236ml |
| [Insidefresh](https://insidefresh.net/products/sua-rua-mat-cerave-cho-da-kho-den-da-thuong-cerave-hydrating-facial-cleanser-236ml) | `listing-aa533c797bc7.v1.json`, REAL | title: 236ml, dry and normal; full page can mention other variants and must be scope-checked |
| [Mint](https://mint07.com/shop/skin-care-san-pham-duong-da/lam-sach-da/sua-rua-mat-cleansers/sua-rua-mat-cerave-hydrating-cleanser-normal-dry/) | `listing-e13e06b174d7.v1.json`, REAL | title says Normal to Dry; usage#4 lists 87/355/473ml whereas usage#16 lists 20/88/236/355/473ml. Multi-size page with differing size lists, not assumed exclusively 236ml |
| Long Châu | HTTP403 | No snapshot; no value inferred from search snippets |
| Guardian | HTTP403 | No snapshot |
| Watsons | HTTP403 | No snapshot |
| Hasaki | NO_PRODUCT_TEXT: no product h1 | No snapshot; browser/search text was not substituted |
| Greennino | IDENTITY_MISMATCH in h1 | No snapshot; existing alias rules retained |
| AB Beauty World | IDENTITY_MISMATCH in h1 | No snapshot; existing alias rules retained |

Each retained snapshot contains final/requested URL, captured_at, raw_sha256, cleaned_sha256, cleaner version, seller-domain family and stored passage locators. Family values identify domains; independent copy clusters are still for P1's scan to determine. REAL source marketing/support text remains quoted source data, never our system claim. No synthetic marketplace sellers existed to retain, and none were invented for this report. Scope/independence and actual S4 scan remain NOT VERIFIED.

## Storyboard and Codex evidence

The 160-second silent storyboard now has exact fixture order and source-backed selectors for S3, with explicit S4 and replay holds. Narration remains `{}`. CCR P4→P3 requests stable `review-reason` and `review-decision` selectors; web/receipt controls and E2E/recorder scripts remain pending. No recording or server was started.

`scripts/codex_stats.py` produces [codex-usage.md](codex-usage.md): receipts by lane/outcome, reachable S-prefix commits, application-path commit times and traceable review/plan evidence. It explicitly marks true session counts, skill invocations and unique findings unknown; it does not sum test results or infer model spend. Rerun after integration for final submission evidence.

## Resume after user reports mini-sync complete

Validation: focused stats/capture/blind/guards47 passed (guards4 included); after the runtime-history accounting refinement, stats4 passed. These overlap and are not unique totals. Phase3 acceptance/fixture checks81 passed/5 unchanged phase4 skips; all final invocations0 failed/errors/deselected. Fixture validator101/101. All139 pre-existing protected files byte-identical; original full ExecPlan/Sites history retained. Initial new-test setup failure and correction are disclosed in P4's ExecPlan; no assertion was weakened.

Inspect Local gate status first; integrate only this worktree's intended changes while preserving the complete Local ExecPlan (Stage A, Sites, probe and gate receipts). Fetch/merge contract-4 in the correct lane checkout only after its owner gate is finished. Then implement P4 sync_check4 against actual owner DTOs, reconcile S4 storyboard/E2E, and report remaining source/replay limits. Do not automatically run sync-gate or push p4 from this detached worktree.
