"""Deployment composition: existing API plus built frontend on one origin."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import uvicorn

from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]


def create_hosted_app(dist_dir: Path | None = None) -> FastAPI:
    """Keep API behavior in its owning modules; serve only the frontend build."""
    dist = (dist_dir if dist_dir is not None else REPO_ROOT / "frontend/dist").resolve()
    if not (dist / "index.html").is_file():
        raise RuntimeError("Frontend build missing; run the deployment build first")
    app = create_app()

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False, response_model=None)
    def frontend(path: str) -> FileResponse:
        relative = Path(path)
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        if any(part.startswith(".") for part in relative.parts):
            raise HTTPException(status_code=404, detail="Not found")
        target = (dist / relative).resolve()
        if not target.is_relative_to(dist):
            raise HTTPException(status_code=404, detail="Not found")
        if target.is_file():
            return FileResponse(target)
        if relative.suffix or path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def main() -> None:
    port = int(os.environ.get("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    uvicorn.run(create_hosted_app(), host="0.0.0.0", port=port, workers=1)


if __name__ == "__main__":
    main()
