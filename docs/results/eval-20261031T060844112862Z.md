# B0 / candidate evaluation

Generated: 2026-10-31T06:08:44.097242+00:00
Mode: fallback; requested: fallback; gold: DRAFT; labelled by: draft:codex
Models: FALLBACK; prompts: claims-v2-passage-scope, extract-v1; policies: policy-v1.6
Baseline: b0-v1; gold SHA256: d071ab0d0c0ffb6985d1fd75f50459d09043c362d0503876c963c131d28e3871

## Scores by gold review status

| Gold | System | Correct/total | False blame/eligible | Abstentions | Correct/expected abstentions |
|---|---|---:|---:|---:|---:|
| DRAFT | B0 | 16/65 | 2/57 | 2 | 1/4 |
| DRAFT | candidate | 61/65 | 0/57 | 7 | 4/4 |
| REVIEWED | B0 | 0/0 | 0/0 | 0 | 0/0 |
| REVIEWED | candidate | 0/0 | 0/0 | 0 | 0/0 |

## Checkpoints

| Event | Gold | B0 | Candidate | Calls | Tokens in/out | Latency ms | Outcome / stops |
|---|---|---:|---:|---:|---:|---:|---|
| 01-bootstrap-demo | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 516.00 | ADMITTED;  |
| 02-price-change | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 0.00 | NOOP;  |
| 03-duplicate-price-change | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 0.00 | DUPLICATE;  |
| 04-volume-change | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 453.00 | ADMITTED;  |
| 05-revoke-notification | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 359.00 | ADMITTED;  |
| 06-evidence-added | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 469.00 | ADMITTED;  |
| 07-injection-listing | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 453.00 | ADMITTED;  |
| 08-rejected-producer | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 0.00 | REJECTED;  |
| 09-catalogue-published | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 0.00 | event outcome REJECTED, expected ADMITTED;  |
| 10-blurred-label-photo | DRAFT | 1/5 | 5/5 | 0 | 0/0 | 438.00 | ADMITTED;  |
| 11-bootstrap-hydra | DRAFT | 3/5 | 3/5 | 0 | 0/0 | 516.00 | ADMITTED;  |
| 12-bootstrap-sun-fluid | DRAFT | 1/5 | 3/5 | 0 | 0/0 | 391.00 | ADMITTED;  |
| 13-bootstrap-clear-serum | DRAFT | 2/5 | 5/5 | 0 | 0/0 | 547.00 | ADMITTED;  |

## Disagreements and preconditions

- 01-bootstrap-demo / volume: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 01-bootstrap-demo / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 01-bootstrap-demo / notification_number: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 01-bootstrap-demo / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 02-price-change / volume: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 02-price-change / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 02-price-change / notification_number: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 02-price-change / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 03-duplicate-price-change / volume: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 03-duplicate-price-change / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 03-duplicate-price-change / notification_number: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 03-duplicate-price-change / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 04-volume-change / volume: expected CONFLICTING; B0 SINGLE_SOURCE; candidate CONFLICTING.
- 04-volume-change / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 04-volume-change / notification_number: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 04-volume-change / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 05-revoke-notification / volume: expected CONFLICTING; B0 SINGLE_SOURCE; candidate CONFLICTING.
- 05-revoke-notification / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 05-revoke-notification / notification_number: expected INSUFFICIENT; B0 SINGLE_SOURCE; candidate INSUFFICIENT.
- 05-revoke-notification / responsible_company: expected INSUFFICIENT; B0 SINGLE_SOURCE; candidate INSUFFICIENT.
- 06-evidence-added / volume: expected CONFLICTING; B0 SINGLE_SOURCE; candidate CONFLICTING.
- 06-evidence-added / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 06-evidence-added / notification_number: expected CONFLICTING; B0 SINGLE_SOURCE; candidate CONFLICTING.
- 06-evidence-added / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 07-injection-listing / volume: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 07-injection-listing / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 07-injection-listing / notification_number: expected CONFLICTING; B0 SINGLE_SOURCE; candidate CONFLICTING.
- 07-injection-listing / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 08-rejected-producer / volume: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 08-rejected-producer / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 08-rejected-producer / notification_number: expected CONFLICTING; B0 SINGLE_SOURCE; candidate CONFLICTING.
- 08-rejected-producer / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 09-catalogue-published / volume: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 09-catalogue-published / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 09-catalogue-published / notification_number: expected CONFLICTING; B0 SINGLE_SOURCE; candidate CONFLICTING.
- 09-catalogue-published / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 09-catalogue-published precondition: Thực hiện 01–08 theo event_order.
- 09-catalogue-published precondition: Không có placement agent được kiểm chứng.
- 10-blurred-label-photo / volume: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 10-blurred-label-photo / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 10-blurred-label-photo / notification_number: expected CONFLICTING; B0 SINGLE_SOURCE; candidate CONFLICTING.
- 10-blurred-label-photo / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 10-blurred-label-photo precondition: Thực hiện 01–08 theo event_order.
- 10-blurred-label-photo precondition: 09 đã chạy, chưa có placement agent được kiểm chứng.
- 11-bootstrap-hydra / notification_number: expected CONSISTENT; B0 SINGLE_SOURCE; candidate INSUFFICIENT.
- 11-bootstrap-hydra / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate SINGLE_SOURCE.
- 12-bootstrap-sun-fluid / volume: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 12-bootstrap-sun-fluid / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 12-bootstrap-sun-fluid / notification_number: expected CONSISTENT; B0 INSUFFICIENT; candidate INSUFFICIENT.
- 12-bootstrap-sun-fluid / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; candidate INSUFFICIENT.
- 12-bootstrap-sun-fluid precondition: Phase 3 gap controller và mock registry đã triển khai, lookup được phép.
- 13-bootstrap-clear-serum / skin_type: expected SINGLE_SOURCE; B0 CONSISTENT; candidate SINGLE_SOURCE.
- 13-bootstrap-clear-serum / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; candidate CONSISTENT.
- 13-bootstrap-clear-serum / responsible_company: expected INSUFFICIENT; B0 SINGLE_SOURCE; candidate INSUFFICIENT.

## Limits

- DRAFT scores are exploratory diagnostics, not human-reviewed accuracy.
- B0 uses candidate-stored claims; upstream scope/extraction filtering is shared, not an independent extraction baseline.
- B0 adds zero model calls. Usage is counted once per newly observed candidate run; NOOP/DUPLICATE do not reuse prior usage.
- Literal expected labels are scored; preconditions and alternative gold scenarios are not inferred from candidate output.
- Only five public fields are scored; expert claim findings and isolated image scenarios have separate acceptance tests.
- False-blame attribution is unscored for expected conflicts without an explicit attribution invariant.

Candidate totals: 0 calls, 0/0 tokens in/out, 4142.00 ms.
