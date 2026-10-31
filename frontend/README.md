# Product Truth Passport — frontend

Phase 0 local preview. Requires Node 24 and npm; exact dependency versions are in package.json and package-lock.json.

From this directory, use `npm.cmd ci`, `npm.cmd test` and `npm.cmd run build` on Windows. The human starts the repository's **frontend** Action. Open [the buyer preview](http://localhost:5173/buyer/DEMO-PROD-01).

Development defaults to `VITE_USE_MOCK=1` through .env.development. For a real backend, set `VITE_USE_MOCK=0` in the process environment or .env.development.local and restart the Action. Requests remain under `/api`, proxied by Vite to `http://localhost:8000`. The production build defaults to the real API; a preview build can be created with `$env:VITE_USE_MOCK='1'` before `npm.cmd run build`.

Routes: `/` operator, `/buyer/:productId` buyer, `/reviewer`, `/observe`, `/orders/:orderId`. Role selection is stored in localStorage and sent as `X-Demo-Role` and `X-Demo-Actor`; backend authorization remains authoritative. Product selection opens the chosen buyer route. An unknown product shows an error. The operator catalog is only requested with the Operator role.

The buyer preview shows five independent fields and a count of hidden documents. Its composite mock is a UI example, not pipeline output. Product copy and source excerpts live only in src/mock. No PRIVATE passage content is bundled. Evidence, Why and event buttons are disabled placeholders for the later phases. Receipt, reviewer and observability pages are shells.

Tests use Node's runner with a TypeScript loader for offline React rendering; they create no server, network calls or timed waits. They cover labels and their precedence, API methods and headers, data isolation, poll visibility/cleanup, route rendering, product variants and the authored-text rule.

The wire types mirror the merged S0 backend models, including the full ClaimFinding/FieldDecision shape. `PassportView` is a separate display type. The composite preview in src/mock/passport.json is projected to the exact PassportResponse at the mock transport boundary; its mode and private-document count travel separately as local product presentation metadata. The raw preview file is not sent as an API response. A contract test validates the actual mock response using the backend Pydantic model. From backend, run `../frontend/.venv/Scripts/python.exe -m pytest -q -rs tests ../frontend/tests/test_backend_contract.py` in this checkout, or use a configured backend venv instead. Node 24 is also needed for that contract check.

Actual business API and replay behavior remain unverified: S0 only exposes health and empty business routers. Product/evidence/run/metrics response shapes are provisional until S1. The live source for mode and hidden counts remains a CCR for P1/P4; no backend contract was changed. Existing Node tests include the authored-text scan, sourcing its canonical pattern from backend/tests/test_guards.py rather than keeping a separate vocabulary.

Library references: [React TypeScript](https://react.dev/learn/typescript), [React Router v7 routing](https://reactrouter.com/7.9.6/start/declarative/routing), [Vite](https://vite.dev/guide/), [TypeScript strict mode](https://www.typescriptlang.org/tsconfig/strict.html).
