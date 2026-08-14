"""Genesis OS — Enterprise Decision Intelligence API.

Run:  .venv/bin/uvicorn app.main:app --port 8030
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings

app = FastAPI(title="Genesis OS — Enterprise Decision Intelligence", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/healthz")
@app.get("/status")
def health() -> dict:  # /status alias: Cloud Run's GFE reserves /healthz
    return {"ok": True, "banner": settings.banner()}


@app.on_event("startup")
def startup() -> None:
    from app.observability.tracing import setup_tracing
    from app.workflows.runtime import get_runtime

    from app.models.enterprise import DecisionProposal

    setup_tracing(settings, "genesis-enterprise-api")
    runtime = get_runtime()
    print(f"[api] {settings.banner()}")
    engine = runtime.policy_engine
    probe = DecisionProposal(title="__probe__", description="", category="capex")
    policy_ids = [f.policy_id for f in engine.evaluate(probe)]
    if runtime.datahub.register_policy_pack(engine.version, policy_ids):
        print(f"[api] DataHub: policy pack '{engine.version}' registered ({len(policy_ids)} policies)")
