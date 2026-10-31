# S4 incremental integration gate — 31 October 2026

Gate passed16:08 ICT (T+6:08), with explicit user direction to reuse completed
checks, fix integration defects and rerun only affected failures. PHASE advances
3→4. All lane heads integrated in order P4→P1→P2→P3; no WAITING or omitted lane.
The redundant initial full baseline was interrupted and is not counted.

| Evidence | Result |
|---|---|
| P4 changed helpers/guards | 91 passed |
| P1 receipt/marketplace/web/guards | 72 passed |
| Marketplace checker correction | 62 passed |
| P2 changed modules + five enabled S4 acceptance nodes | 242 passed,3 failed initially |
| Failed nodes and affected scope/web/checker variants | 214 passed; all three failures resolved |
| Final frontend wire + guards | 9 passed |
| Current backend collection | 1626 nodes; no collection errors |
| Case-sensitive current-node JUnit union | 1626 passed,0 unresolved failures/errors/skips;2 historical passing subtests separate |
| Fixtures | 101 files,0 failures |
| In-process fallback sync4 | 35 PASS/1 receipt FAIL initially; affected receipt recheck PASS;36/36 incremental |
| Frontend Node24.22.1 | 93 passed,0 failed/skipped |
| Frontend API build | Passed |

Fresh executed sets have0 skipped/deselected except the deliberate initial audit
reproduction (2 failed,9 deselected); that reproduction is superseded by the
passing P1 suite. Counts overlap. No claim of a single fresh1626-test invocation.
The union uses .git/p4-s4-full.xml, its review-final/addendum receipts and current
.git/s4-{p4,p1,checker,p2,repairs,final-wire}.xml, matched to s4-collection.log.
No collected node lacks a passing receipt. Windows temporary-directory cleanup
warnings and the two existing React Router build directives are retained.

Repairs: web audit query-envelope projection; identity-matched retailer size
disagreement kept UNKNOWN for policy review (policy-v2.1); requested recording
web paths require actual query activity. Human explicitly approved checker
semantics for zero marketplace findings and receipt timestamp-only rechecks.
No existing acceptance assertion, fixture, gold or replay recording was changed.
New unrelated variants cover rejection boundaries and actual discovery→audit GET.

No paid provider, browser E2E, recording, server or external message was run.
Provider replay, full nine-scene video, OCR and gold approval remain NOT VERIFIED.
No new dependency/API; existing installed Pydantic/FastAPI methods and test seams
were reused. Three skill-required read-only reviews found one audit blocker;
targeted repair review found no remaining blocker. HANDOFF sync-4 is in the gate
commit before tagging; publication is verified separately by remote SHA.
