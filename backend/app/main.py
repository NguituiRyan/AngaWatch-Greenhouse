"""FastAPI application entrypoint.

uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("api.startup", environment=settings.environment)
    yield
    log.info("api.shutdown")


app = FastAPI(
    title="AngaWatch Greenhouse API",
    version="0.1.0",
    description="Smart greenhouse crop-loss prevention platform for Kenya.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"service": "angawatch-greenhouse", "version": "0.1.0", "docs": "/docs"}
