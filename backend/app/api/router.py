"""Aggregate API router. Sub-routers self-include here as they are implemented.

Wave 0 routers are wired by the api module: auth, orgs, farms, greenhouses,
devices, readings, risk, alerts, recommendations, control, billing, weather.
Roadmap routers (records, invoicing, marketplace, traceability, financing) are
scaffolded as empty routers with TODOs.
"""

from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


def include_feature_routers() -> None:
    """Attach domain routers. Called at import time below; tolerant of WIP modules."""
    import importlib

    modules = [
        "app.api.routers.auth",
        "app.api.routers.organizations",
        "app.api.routers.farms",
        "app.api.routers.greenhouses",
        "app.api.routers.devices",
        "app.api.routers.readings",
        "app.api.routers.risk",
        "app.api.routers.alerts",
        "app.api.routers.recommendations",
        "app.api.routers.control",
        "app.api.routers.billing",
        "app.api.routers.weather",
        "app.api.routers.records",
        "app.api.routers.ussd",
        "app.api.routers.whatsapp",
    ]
    for name in modules:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError:
            continue
        router = getattr(mod, "router", None)
        if router is not None:
            api_router.include_router(router)


include_feature_routers()
