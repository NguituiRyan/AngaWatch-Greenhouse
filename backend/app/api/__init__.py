"""HTTP API (FastAPI). The aggregate router is exposed as ``api_router``."""

from app.api.router import api_router

__all__ = ["api_router"]
