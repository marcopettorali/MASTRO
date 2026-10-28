"""MASTRO backend: FastAPI server of the agentic modules."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import intent, llm_agent, autonomous, context, mcp_gateway
from .agent.scheduler import scheduler
from .db import mongo

app = FastAPI(title="MASTRO Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup():
    await mongo.init_mongo()
    await scheduler.start()


@app.on_event("shutdown")
async def _on_shutdown():
    await scheduler.stop()
    await mongo.close_mongo()


@app.get("/api/ping")
def ping():
    return {"ok": True}


app.include_router(mcp_gateway.router)
app.include_router(intent.router)
app.include_router(llm_agent.router)
app.include_router(autonomous.router)
app.include_router(context.router)
