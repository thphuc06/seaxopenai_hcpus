"""P4 app composition; P1 owns the routers and persistence."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config, db, seed
from app.models import ContractModel
from app.pipeline.policy import POLICY_VERSION


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    seed.seed_if_empty()
    yield


class HealthResponse(ContractModel):
    llm_mode: str
    models: dict[str, str]
    policy_version: str
    phase: int
    demo_run_delay_s: float


def create_app() -> FastAPI:
    app = FastAPI(title="Product Truth Passport", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["http://localhost:5173"],
        allow_methods=["*"], allow_headers=["*"],
    )
    for name in ("passport", "events", "runs", "cases", "observe", "orders"):
        router_module = import_module(f"app.api.{name}")
        app.include_router(router_module.router, prefix="/api")

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        s = config.settings
        return HealthResponse(
            llm_mode=s.llm_mode,
            models={"extract": s.model_extract, "agent": s.model_agent,
                    "cheap": s.model_cheap, "embed": s.embed_model},
            policy_version=POLICY_VERSION, phase=s.contest_phase,
            demo_run_delay_s=s.demo_run_delay_s,
        )

    return app


app = create_app()
