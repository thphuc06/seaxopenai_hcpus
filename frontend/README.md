# Product Truth Passport — frontend

Phase 1 buyer and Operator UI. Requires Node 24 and npm; exact dependency versions are in package.json and package-lock.json.

From this directory, use `npm.cmd ci`, `npm.cmd test` and `npm.cmd run build` on Windows. The human starts the repository's **frontend** Action. Open [the buyer preview](http://localhost:5173/buyer/DEMO-PROD-01).

Development defaults to `VITE_USE_MOCK=1` through .env.development. For a real backend, set `VITE_USE_MOCK=0` in the process environment or .env.development.local and restart the Action. Requests remain under `/api`, proxied by Vite to `http://localhost:8000`. The production build defaults to the real API; a preview build can be created with `$env:VITE_USE_MOCK='1'` before `npm.cmd run build`.

Routes: `/` operator, `/buyer/:productId` buyer, `/reviewer`, `/observe`, `/orders/:orderId`. Role selection is stored in localStorage and sent as `X-Demo-Role` and `X-Demo-Actor`; backend authorization remains authoritative. Product selection opens the chosen buyer route. An unknown product shows an error. The operator catalog is only requested with the Operator role.

The buyer shows five independent fields, checked times and available origin/mode badges. Passport polling runs every 2 seconds while stale or updating, otherwise every 10 seconds, and pauses in hidden tabs. Evidence opens the full stored passages with the exact excerpt highlighted, allowing whitespace/NFC differences. Within-source passages share a source heading and appear side by side on desktop. Buyer evidence omits PRIVATE text and shows only its count. Why, receipt, reviewer and observability work remain for later phases.

Operator v1 provides event buttons, outcome/reason/stale-field messages, counters, runs and trace steps, and a reset confirmation. API errors show route and HTTP status. The mock has an explicit interactive scenario transport; its counters and runs last only for the current page session and reset on a full reload. It is a UI simulation, not pipeline execution. Product copy, passages and authored outcomes stay under src/mock; no PRIVATE source text is bundled.

`npm.cmd run types` exports the checked-out backend's `/openapi.json` through FastAPI TestClient and regenerates src/api/schema.d.ts using pinned openapi-typescript. It requires backend/.venv with P4's requirements; it starts no server and does not enter the application's startup lifespan. S1 wire types consume that schema; `PassportView` keeps pending display rows separate. Product presentation and passport metadata may be null. The composite mock is projected to the exact PassportResponse before transport. Contract tests validate all S1 mock responses against P1's Pydantic DTOs.

At contract-1 (a558fc9), all eleven S1 business routes have schemas and ACLs but return 501. The real transport and production build are ready; keep the development mock enabled until P1's implementation is integrated. There is no automatic mock fallback after an API failure. Actual Milestone 1 backend behavior remains pending the shared integration gate. API keys belong only in backend/.env, never in a VITE variable or frontend file.

Tests use Node's runner and offline Playwright route interception. They create no listening server or model call. Existing label, transport, guard and lifecycle assertions remain intact; Phase 1 adds evidence, dynamic polling, events, reset, error recovery and read-only buyer checks. Browser tests require Chromium already installed for P4's pinned Python Playwright. From this directory:

```powershell
npm.cmd test
..\backend\.venv\Scripts\python.exe -m pytest -c ../backend/pytest.ini -q tests/test_backend_contract.py tests/test_s1_contract.py
$env:VITE_USE_MOCK='1'
npm.cmd run build -- --outDir node_modules/.cache/p3-mock-build
..\backend\.venv\Scripts\python.exe -m pytest -q tests/test_phase1_browser.py
$env:VITE_USE_MOCK='0'
npm.cmd run build
..\backend\.venv\Scripts\python.exe -m pytest -q tests/test_phase1_api_browser.py
Remove-Item Env:VITE_USE_MOCK
```

The API browser suite intercepts contract-shaped responses and checks three full buyer reloads, null presentation, stale/running/failed states, late evidence responses, 501 retry and event double-click protection. It does not certify the backend implementation. The wording scan reads the canonical pattern from backend/tests/test_guards.py.

Library references: [React](https://react.dev/reference/react/useEffect), [React Router](https://reactrouter.com/start/declarative/routing), [Vite](https://vite.dev/guide/), [openapi-typescript](https://openapi-ts.dev/introduction), [Playwright interception](https://playwright.dev/python/docs/network).
