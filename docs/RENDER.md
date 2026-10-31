# CI and Render deployment

Owner: P4 deployment workstream. Prepared from sync-0; deploy the complete demo after S1.
The Phase 1 Local chat owns application behavior and acceptance tests. This workstream
owns .github/workflows/ci.yml, Dockerfile, .dockerignore, render.yaml and scripts/dev/render/.

## What runs

GitHub Actions runs on pushes to main, p1–p4 and codex/**, and pull requests to main.
It runs the checked-in backend/tests/PHASE with fallback, inline worker, OCR/web/tracing
disabled; no API key is needed. It does not change phase markers or ignore failures.

Jobs:

1. Backend tests, guards, frontend Python wire-contract check, deployment adapter tests,
   fixture validation and dependency consistency.
2. Node 24 frontend tests and an API-mode production build.
3. Docker build, then an offline in-process startup check inside the image.

Action revisions are pinned to upstream commit SHAs. Python is 3.11 (OCR needs <3.13);
Node is 24.22.1. Docker base tags were checked against the registry on 31 Oct 2026.
OCR stays disabled; enabling it later requires checking Linux system libraries and inference.
CI uploads only JUnit XML and frontend dist, retained seven days.

## Hosting layout

One Docker web service serves both the compiled frontend and existing FastAPI routes.
The frontend retains relative /api requests; no separate API hostname or CORS edit is
needed. scripts/dev/render/server.py composes app.main.create_app and serves the
frontend build with SPA fallback. API paths, missing assets, hidden paths and paths
outside the build directory do not receive index.html. One Uvicorn worker binds
0.0.0.0 and the PORT Render supplies (10000 fallback).

The image excludes local env files, SQLite databases, offline expected labels and
blind evaluation fixtures. Its default mode is FALLBACK; it starts without a model key.
The API and role headers still have the contest's simulated auth. This is a demo
environment, with shared mutable demo state; it is not an authenticated tenant service.

## First deployment, after S1 and green CI

1. Connect the Render GitHub integration to this repository.
2. Merge the reviewed deployment branch into main via P4's integration checkout.
3. Wait for all three CI jobs on the resulting main commit to pass.
4. In Render, create a Blueprint from this repository and main; select render.yaml.
5. Review the proposed free web service before applying. This task creates no remote service.
6. Confirm /api/health and / load, then exercise the S1 Bootstrap → Passport flow.

The Blueprint links main and selects autoDeployTrigger: checksPass. Subsequent main
commits deploy after their CI checks pass. No Render deploy hook, PAT or Render API
secret is needed by the workflow. The initial Blueprint creation can start a build,
so wait for the reviewed S1 commit and green CI before applying it.

GitHub skipped/neutral checks can count as passed to Render. The tests in this workflow
run unconditionally; future-phase pytest skips are the existing contest mechanism,
not proof those future features work. Render health 200 proves startup, not an S1 gate.

## Data persistence and demo mode

The committed Blueprint uses the Free plan and DB_PATH=/tmp/passport.db. That database
is ephemeral: deploy/restart/spin-down loses runs/reviews and startup seeds fixtures
again. Free services also spin down after inactivity. This mode is for a disposable
preview; it does not preserve the evaluation or presentation state.

For persistent SQLite, explicitly approve a paid service and persistent disk first.
Mount the disk at /var/data and set DB_PATH=/var/data/passport.db. Keep one instance
and one Uvicorn worker. Do not move the DB to the disk after a run and expect history
to migrate automatically; migrate or intentionally re-seed under a separate task.
Upload paths also need an explicit persistent location if retained in scope.

After P2 delivers and freezes recordings, switch LLM_MODE to replay and keep
REPLAY_FREEZE=1. Check all demo scenes for replay misses before presentation. Do not
enable paid/live calls as part of this CI setup.

## Local checks and recovery

Use a Python 3.11/3.12 environment with backend/requirements.txt and Node 24 dependencies.
From backend:

    python -m pytest -q tests ../frontend/tests/test_backend_contract.py ../scripts/dev/render/tests
    python ../scripts/check_fixtures.py

From frontend:

    npm ci
    npm test
    npm run build

When a Docker engine is available, from the repository root:

    docker build --tag passport-ci .
    docker run --rm --network none --entrypoint python passport-ci -m scripts.dev.render.check_image

The image check starts no listening server. Only the human starts local servers.
If CI fails, inspect its failing job/artifact; do not bypass it to deploy. To hold
a presentation version, turn off Auto-Deploy in Render and record the deployed SHA.
No sync tag is created by this workstream.

## References and validation

- [Render Blueprint fields](https://render.com/docs/blueprint-spec)
- [Docker on Render](https://render.com/docs/docker)
- [Render CI integration](https://render.com/docs/deploys#integrating-with-ci)
- [Free filesystem limitations](https://render.com/docs/free#local-files-lost-on-redeploy)
- [Persistent disks](https://render.com/docs/disks)
- [GitHub Python workflow](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)
- [GitHub Node workflow](https://docs.github.com/en/actions/tutorials/build-and-test-code/nodejs)
- [Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/)

Local checks at preparation: 153 Python tests + 2 subtests passed, 23 frontend tests
passed, API frontend build passed, fixture validator 9 files/0 errors, actionlint 1.7.11
and the official Render Blueprint JSON schema passed. Existing Windows
pytest cleanup warnings are visible. Docker daemon was unavailable locally; GitHub
[run 41165337846](https://github.com/thphuc06/seaxopenai_hcpus/actions/runs/41165337846)
passed all three jobs on implementation commit a95ee1d on 31 Oct at 10:41 ICT,
including the Linux Docker build and offline image startup check. Render account linkage, live URL,
persistent storage and hosted S1 click path are not verified by local checks.
