"""Import deployment from Docker-declared Python files, without repository leakage."""
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]


def runtime_python_tree(destination: Path) -> None:
    runtime = False
    workdir = PurePosixPath("/")
    for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if not line.startswith(("FROM ", "WORKDIR ", "COPY ")):
            continue
        words = shlex.split(line, comments=True)
        if not words:
            continue
        if words[0] == "FROM":
            runtime = words[-1] == "runtime"
        elif runtime and words[0] == "WORKDIR":
            workdir = PurePosixPath(words[1])
        elif runtime and words[0] == "COPY" and not words[1].startswith("--"):
            source = ROOT / words[1]
            target = PurePosixPath(words[2])
            target = target if target.is_absolute() else workdir / target
            target_dir = destination / str(target).lstrip("/")
            files = source.rglob("*") if source.is_dir() else [source]
            for file in files:
                # Import-only check: Python modules and their packaged JSON data.
                if file.suffix not in {".py", ".json"} or any(part in {"gold", "blind", "__pycache__"} for part in file.parts):
                    continue
                output = target_dir / file.relative_to(source) if source.is_dir() else target_dir
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, output)


@pytest.mark.parametrize("web", ["off", "on"])
def test_runtime_imports_without_source_checkout(tmp_path: Path, web: str) -> None:
    runtime_python_tree(tmp_path)
    app_root = tmp_path / "app"
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import sys\nfrom pathlib import Path\n"
        "root = Path(sys.argv[1])\n"
        "sys.path[:0] = [str(root), str(root / 'backend')]\n"
        "from scripts.dev.render.server import create_hosted_app\n"
        "from app.pipeline.web_sources import discover\n"
        "from scripts.capture_page import clean_html\n"
        "from fastapi.testclient import TestClient\n"
        "dist = root / 'frontend/dist'\n"
        "dist.mkdir(parents=True, exist_ok=True)\n"
        "(dist / 'index.html').write_text('<p>Packaged preview</p>', encoding='utf-8')\n"
        "with TestClient(create_hosted_app(dist)) as client:\n"
        "    assert client.get('/api/health').json()['llm_mode'] == 'fallback'\n"
        "    assert client.get('/').status_code == 200\n",
        encoding="utf-8",
    )
    env = {**os.environ, "LLM_MODE": "fallback", "OPENAI_API_KEY": "", "WORKER_INLINE": "1",
           "DB_PATH": str(tmp_path / "packaged.db"), "OCR_ENABLED": "0", "WEB_SEARCH": web,
           "FIXTURES_DIR": str(tmp_path / "no-fixtures"), "AGENTS_TRACING": "0",
           "OPENAI_AGENTS_DISABLE_TRACING": "1", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, "-I", str(probe), str(app_root)], cwd=tmp_path,
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert result.returncode == 0, result.stderr
