"""Analytics service: records clicks and answers statistics queries (see ADR-001)."""

import os

from fastapi import FastAPI, status
from prometheus_client import CollectorRegistry
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from pydantic import BaseModel, Field

from analytics_service.store import ClickStore

# Request time buckets in seconds, fine enough to see the few milliseconds of an internal call.
LATENCY_BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)


class ClickEvent(BaseModel):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    referrer: str | None = None


class LinkStats(BaseModel):
    code: str
    total_clicks: int


def create_app(store: ClickStore | None = None) -> FastAPI:
    store = store or ClickStore(os.environ.get("CLICK_DB_PATH", "clicks.db"))
    app = FastAPI(title="LinkLite analytics service")
    # Prometheus metrics at /metrics (request count and time per endpoint), see XP-45.
    # Registered before the routes so that /metrics is not taken by a catch-all route.
    metrics_registry = CollectorRegistry()
    Instrumentator(excluded_handlers=["^/metrics$", "^/health$"], registry=metrics_registry).add(
        metrics.default(latency_lowr_buckets=LATENCY_BUCKETS, registry=metrics_registry)
    ).instrument(app).expose(app, include_in_schema=False)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/clicks", status_code=status.HTTP_202_ACCEPTED)
    def record_click(event: ClickEvent) -> dict[str, str]:
        store.record(event.code, event.referrer)
        return {"status": "accepted"}

    @app.get("/stats/{code}")
    def stats(code: str) -> LinkStats:
        return LinkStats(code=code, total_clicks=store.total_clicks(code))

    return app
