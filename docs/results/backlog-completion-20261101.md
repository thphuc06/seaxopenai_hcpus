# Post-contest backlog repair — 1 November 2026

The user requested actual bugs/backlog to be fixed across P1–P4, after the earlier repository closeout. Work starts from721a721 on `codex/backlog-completion`. Five public fields, policy-v2.1, PHASE5, original fixtures/gold/replay and shared Local data remain intact.

Delivery: implementation commit `a6e66bd` pushed in [PR20](https://github.com/thphuc06/seaxopenai_hcpus/pull/20), based on PR19's closeout. Current-head hosted checks are attached to that PR. This report does not imply a merge or deployment.

## Implemented

| Area | Before | Delivered |
|---|---|---|
| Evidence image | Registered GET returned501 | PNG/JPEG/WebP bytes, PRIVATE role checks, resolved storage boundary, bounded reads, full image decode and no-store headers. |
| Fresh uploads | Image stored with empty text; OCR stub | Local OCR transcript and geometry stored before source hashing/claim extraction. Empty/disabled OCR stays unreadable. Package errors become controlled503; invalid images422. Duplicate submission does not repeat OCR. |
| Offline evaluation | Cached-report API501, metrics CLI absent | `scripts/metrics.py` summarizes an existing offline evaluation archive; validated cached GET returns it or available:false. UI shows mode, fallback reason, versions and limitations. |
| OTLP | Run export API501 | Read-only deterministic OTLP/JSON from stored trace, with content capture excluded; no collector side effect. |
| Buyer | Generic Why; public citations dropped; pending count ignored | Three explanation fragments plus quoted passages; only public evidence; ingredient pending count from backend metadata. |
| Reviewer | No origin/mode or attribution; scans all products for evidence | Additive queue metadata binds product and producing/confirming run, shows provenance and exact seller-attribution flag; older queue compatibility preserved. |
| Canon learning | Helper not called by worker | Existing grounded/provenance-checked learning runs before policy, uses the same Budget, and retains cached mappings on missing recording/budget failure while marking PARTIAL. |
| Agent effect probe | Accepted records without checking actor | Only error-free code records count. Model/human/error variants are rejected. |

Three independent read-only reviews found and prompted fixes for lost cached mappings during unrelated learning failures, uncaught RapidOCR exception classes and discarded scorecard provenance. Reproductions are in `test_backlog_runtime.py`, `test_ocr.py` and `frontend/tests/backlog.test.mjs`. No existing assertion was weakened.

## Evidence and limits

- Final full Phase5 regression after reviewer fixes:1699 passed +2 subtests;0 failures/errors/skips/deselections in253.06s. Includes backend, all P3 wire contracts and Render wrapper tests; local Python3.12.13. JUnit: `backend/.venv/backlog-final.xml` (ignored). Earlier regression1683+2 also passed before reviewer additions.
- Focused final canon/OCR/worker regressions:29 passed. Frontend99 passed,0 failed/skipped; TypeScript/API build PASS.
- Offline `scripts/sync_check.py 4 --mode fallback`:36 PASS,0 FAIL/SKIP; current CONTEST_PHASE stays5. This is the script's supported story1–4, not a provider replay gate. All three reviewers rechecked their fixes and reported no remaining P0/P1/P2 finding.
- Actual local RapidOCR1.4.4 smoke: generated800×200 English label yielded “Volume: 83 ml” and “For dry skin.” with bounded boxes in4.14s. This verifies installed-engine integration, not general accuracy on Vietnamese/blurred photographs.
- Browser: production build + real FastAPI responses in a fresh FALLBACK DB;12 GETs,0 HTTP errors,0 JavaScript errors, unchanged DB,0 provider calls. Source events01 and11 ran only in that temporary DB. Screens: [Buyer Why](screens/backlog-20261101/buyer-why.png), [Reviewer provenance](screens/backlog-20261101/reviewer-provenance.png), [Observe scorecard](screens/backlog-20261101/scorecard.png). These do not claim a complete provider replay or an agent-caused verdict change.
- Fresh offline evaluation: [source archive](backlog-eval-20261101.json), [scorecard](metrics.json). Candidate61/65 under DRAFT labels, FALLBACK,0 provider calls;0 human-reviewed fields. Do not present this as reviewed quality. The report exposes missing preconditions/diagnostic limitations; no gold was edited.
- Replay diagnosis rerun after changes:01 completes,05 waits for evidence,06 becomes PARTIAL at extract-v1/REPLAY_MISS before policy. The missing provider output cannot be repaired by inventing evidence or switching replay to fallback. Ignored diagnostic artifacts retain DB/report under `frontend/node_modules/.cache/backlog-replay-dc98c69ab8`.
- Hosted38e785b found one additional startup-independent OCR lookup bug on a clean Linux DB. Fresh-storage and reviewer byte-invariance regressions failed before the repair; the fix uses SQLite mode=ro and returns no cached boxes without creating a DB/schema or changing journal mode, while a corrupt-DB regression still raises. All50 OCR/skeleton/guard checks now pass locally. Hosted validation of the repair is tracked on PR20; the earlier full local receipt alone did not detect this difference.

## Remaining work requiring separate evidence or decisions

1. **Recordings:** append-only provider pass and whole-story/agent-effect verification. A dry plan with30-request/$2 caps was prepared, web off; this does not guarantee full-story completion. No paid execution approved or performed in this task so far.
2. **Gold and domain decisions:** human review of DRAFT labels; resolve R3 ingredient-versus-concentration projection and blind case10 missing metadata. Existing labels/fixtures stay intact.
3. **Legacy history:** old unchained databases need a deliberate archive/migration or authorized reset. No silent rehash that implies historical integrity; no Local reset.
4. **Optional extensions:** provider hybrid retrieval/quality measurements and OCR image overlays. Context-bound helpers and stored OCR boxes exist; the ordinary expert GET remains read-only BM25, and evidence UI currently shows transcript excerpts.
5. **Release:** review/merge the PR and validate deployment against its real database. This task does not deploy or claim hosted runtime validation.
6. **Development dependencies:** fresh npm audit still reports3 moderate advisories (0 high/critical) through openapi-typescript7.13.0 → Redocly1.34.22 → minimatch5.1.9. [The advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249) lists11.0.1 as patched, but its named export is incompatible with Redocly's callable CommonJS import. Latest generator remains7.13.0; no forced override or downgrade applied. Use a compatible upstream update or a separately validated generator migration; this is not a clean audit claim.

## Reproduce the scorecard

From repository root, with the offline settings in README and PHASE read from `backend/tests/PHASE`:

```powershell
backend/.venv/Scripts/python.exe scripts/eval.py --mode fallback --output-dir frontend/node_modules/.cache/new-eval
backend/.venv/Scripts/python.exe scripts/metrics.py --input frontend/node_modules/.cache/new-eval/eval-latest.json --output-dir docs/results
```

The second command archives each scorecard and atomically updates metrics.json. It never runs the app pipeline. The first command uses a temporary database and blocks provider calls. Application GETs never read gold.
