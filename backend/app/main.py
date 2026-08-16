"""QueryPilot REST API."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import warehouse
from .agent import pilot
from .catalog import schema_as_dict
from .config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Seed the demo warehouse on first boot if it's empty.
    if "orders" not in warehouse.list_tables():
        warehouse.seed()
    yield


app = FastAPI(title="QueryPilot API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "querypilot", "provider": settings.llm_provider}


@app.get("/api/schema")
def schema() -> list[dict]:
    return schema_as_dict()


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    return pilot.ask(req.question).to_dict()


@app.post("/api/approve/{query_id}")
def approve(query_id: str) -> dict:
    try:
        return pilot.approve(query_id).to_dict()
    except KeyError:
        raise HTTPException(404, "no pending query with that id")


@app.post("/api/reject/{query_id}")
def reject(query_id: str) -> dict:
    try:
        return pilot.reject(query_id).to_dict()
    except KeyError:
        raise HTTPException(404, "no pending query with that id")


@app.get("/api/history")
def history(limit: int = 25) -> list[dict]:
    return [s.to_dict() for s in pilot.history(limit)]
