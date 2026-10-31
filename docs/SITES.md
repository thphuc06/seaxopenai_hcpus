# Sites frontend deployment

P4 hosting task, isolated from P3 application implementation.

## Architecture and source

The Site serves the existing frontend built with VITE_USE_MOCK=0 from sync-2
(c7b413d6dc798fb74b76dd19269913f3008fb7bf). It is not a replacement UI.
Browser /api requests are proxied by a Worker to
https://product-truth-passport-demo.onrender.com, preserving path/query, role/actor,
HTTP method and body. No retries occur for mutations. Source APIs remain responsible
for ACL, budget, idempotency, citations and verdicts.

Site identity: appgprj_6ae586d8cc7081918726e8abf69368a2.
Expected origin: https://product-truth-passport-vn.pointykayak.chatgpt.site .
Registration alone does not establish deployment success; see the publication receipt.
The new Site stays owner-private. Judge access needs a separately requested audience change.
The existing full Render frontend remains available as a fallback.

## Files and build

- scripts/dev/sites/proxy.mts: authoritative proxy and SPA routing implementation.
- scripts/dev/sites/proxy.test.mjs: offline routing/header/body/error tests.
- scripts/dev/sites/prepare.mjs: copies an explicit frontend-source allowlist and its
  built assets into the separate Sites-managed project; includes source provenance.
- sites/passport/: ignored local publishing checkout, with its own Git repository.
  Sites tools own its source commit/push/package lifecycle. Do not add it as a Git submodule.

No backend code, fixtures, gold labels, .env or source Git metadata is copied to Sites.
The source project uses the supplied Vinext starter and sites() plugin. The Worker
serves ASSETS with run_worker_first=true and html_handling=none, with /passport.html
as the SPA entry. The retained frontend build has its original title, styling and testids.

## Updating after a future Sync

1. Merge the desired sync tag in this deployment worktree; preserve the Site identity.
2. Install/test/build frontend with Node 24 and VITE_USE_MOCK=0.
3. Run node --test scripts/dev/sites/proxy.test.mjs.
4. Run node scripts/dev/sites/prepare.mjs.
5. Use the Sites skill's build-site.mjs and source helper from sites/passport.
   Credentials are memory-only and supplied through hidden stdin. Reuse the same project.
6. Package a matching archive, save/deploy using the native operation for the actual audience,
   and record the source commit/version/deployment result here.

GitHub CI checks proxy tests; publishing to Sites remains through the native Sites
workflow. A push to the contest GitHub repo alone does not publish a new Site version.
Keep frontend source from the same accepted Sync as the intended backend version.

## Verification and limits

Local: 51 frontend tests and API build passed; 9 proxy tests passed with unrelated IDs,
revision conflicts, denied requests, missing routes, timeouts and redirects.
Backend suite at sync-2: 1044 passed, 14 future-phase skips, 2 subtests passed;
zero failed/deselected. Existing Windows pytest cleanup warnings remain.
No listening local server is started, respecting the contest Actions-only rule.
Native deployment and read-only hosted checks are recorded after publication.
No live reset, bootstrap, review or model call is performed by this deployment task.

Render health observed during preparation: phase=2, policy-v1.6, fallback.
Render Free still has cold starts and ephemeral SQLite. Sites does not change those
backend properties. Sites login cookies and platform identity headers never go to Render.
The demo role headers remain the application's existing simulated-auth mechanism.

## References

- Sites skill/runtime version 1.1.2, Vinext starter 1.0.0-beta.5, Vite 8.0.13,
  Cloudflare Vite plugin 1.37.1, Wrangler 4.92.0 (locked hosting dependencies).
- https://developers.cloudflare.com/workers/static-assets/binding/
- https://developers.cloudflare.com/workers/static-assets/routing/worker-script/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://github.com/cloudflare/vinext

## Current publication — 31 Oct 2026, 16:31 ICT

The user requested syncing the latest accepted main frontend to the existing Site.
Native get_site confirmed the audience was already public; this refresh preserved it.
This receipt supersedes the initial private/access and sync2 UI status below.

- URL: https://product-truth-passport-vn.pointykayak.chatgpt.site
- Contest source: main2de7c1d25919a9965c19acad42585bd0c654b7f2 (includes sync-4).
- Sites source: adb410f9175d0b811f8d9d0d9332c61ee1126116.
- Version2: appgprj_6ae586d8cc7081918726e8abf69368a2~appgver_1a1afc1d9cf48191b97456de753ec1e4.
- Deployment: appgdep_6ae5b543aed88191b4dcf8e968fcac2a; succeeded16:31:04 ICT.
- Matching archive: SHA256 9f31332521b5272c2a76491c2b7e5aff3eb30642b4592a16b77d0c4369570f51,
  1,372,160 bytes,31 files. Source helper owns commit/push/package; credentials stayed in hidden stdin/memory.
- Validation: Node24 frontend93 tests, proxy9 tests, TypeScript, frontend API build
  and Sites build passed. Existing lockfiles/dependencies reused.
- Hosted asset now index-DFqCMqrn.js, matching Render and containing web-audit,
  receipt-diff and agent-panel. Public /api/health returns live,phase4,policy-v2.1.
- No new model request or reset. Existing hosted run remains PARTIAL/WEB_CAPTUREERROR;
  updating the UI does not make the earlier incomplete data run complete.

## Publication receipt (initial deployment)

Published successfully at 13:30:56 ICT on 31 Oct 2026.

- URL: https://product-truth-passport-vn.pointykayak.chatgpt.site
- Sites source commit: df15f5c2e2d5f6c3d5eb9341acfeca3e0d16c5da
- Version ID: appgprj_6ae586d8cc7081918726e8abf69368a2~appgver_7fb052f731288191b181b2b7005b60e5
- Deployment ID: appgdep_6ae58b12ad9c819187a29d84465e0336
- Native status: succeeded; audience remains owner-private.
- Build: Vinext/Sites build passed; artifact metadata includes ASSETS binding,
  run_worker_first=true and html_handling=none; original frontend JS/CSS are present.
- Anonymous terminal GET /api/health returned 401. Authenticated browser click path
  remains NOT VERIFIED; no bypass token or audience change was requested.
- Open-in-Codex was queued for this chat's panel.

CODEX_LOG: | 13:31 ICT | P4 | Publish sync-2 frontend on Sites | scripts/dev/sites, CI, docs, P4 appendix | accepted | user requested Sites alongside Phase 3 | frontend 51, proxy 9, backend 1044 passed/14 future skips/+2 subtests; native deploy succeeded |
