# Local environment setup (Windows)

Sources checked 31 Oct 2026:
[worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) and
[local environments](https://learn.chatgpt.com/docs/environments/local-environment).
Use Python 3.11/3.12 for pinned RapidOCR compatibility.

Already configured in `.codex/environments/environment.toml` at the user's request.
Schema checked against installed Codex 26.1027.3384.0: version/name, setup.script,
setup.win32.script and actions with name/icon/command/platform. The app discovers
`environment.toml` as the default successful config. The UI display remains to be
confirmed by the human; the computer-use skill prohibits automating Codex itself.
The instructions below also let teammates recreate or edit the same settings.

In the app Settings → Local environments, save the following Windows setup script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\setup_worktree.ps1
```

Add these four Actions, run from the repo root. The human starts servers from the
Local chat only. App-generated configuration is saved under `.codex/`; commit it
after saving. Setup does not start servers or create an API key.

**backend**

```powershell
cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**frontend** (after P3 is merged)

```powershell
cd frontend; npm run dev
```

**tests** (reads the current checkpoint phase)

```powershell
$env:CONTEST_PHASE = (Get-Content backend\tests\PHASE -Raw).Trim(); $env:LLM_MODE = 'fallback'; $env:WORKER_INLINE = '1'; cd backend; .\.venv\Scripts\python.exe -m pytest -q
```

**sync_check** (available from Phase 1)

```powershell
$phase = (Get-Content backend\tests\PHASE -Raw).Trim(); $env:LLM_MODE = 'fallback'; $env:WORKER_INLINE = '1'; cd backend; .\.venv\Scripts\python.exe ..\scripts\sync_check.py $phase
```

Keep `backend/.env` local and ignored. `.worktreeinclude` copies that ignored file
into app-managed worktrees. P2 supplies model settings after the smoke checks.
