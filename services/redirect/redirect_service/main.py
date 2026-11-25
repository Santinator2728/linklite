"""Redirect service: the hot path that sends users to the target URL (see ADR-001)."""

import os
import re
from typing import Protocol

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from prometheus_client import CollectorRegistry
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from redirect_service.clients import (
    DEPENDENCY_CALL_SECONDS,
    AnalyticsClient,
    LinkClient,
    LinkServiceError,
)

CODE_PATTERN = re.compile(r"^[A-Za-z0-9]{1,32}$")

# Request time buckets in seconds, fine enough to see the few milliseconds of an internal call.
LATENCY_BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)


class Resolver(Protocol):
    def resolve(self, code: str) -> str | None: ...


class ClickRecorder(Protocol):
    def record_click(self, code: str, referrer: str | None) -> None: ...


def create_app(links: Resolver | None = None, analytics: ClickRecorder | None = None) -> FastAPI:
    links = links or LinkClient(os.environ.get("LINK_SERVICE_URL", "http://localhost:8001"))
    analytics = analytics or AnalyticsClient(
        os.environ.get("ANALYTICS_SERVICE_URL", "http://localhost:8003")
    )
    app = FastAPI(title="LinkLite redirect service")
    # Prometheus metrics at /metrics (request count and time per endpoint), see XP-45.
    # Registered before the routes so that /metrics is not taken by a catch-all route.
    metrics_registry = CollectorRegistry()
    Instrumentator(excluded_handlers=["^/metrics$", "^/health$"], registry=metrics_registry).add(
        metrics.default(latency_lowr_buckets=LATENCY_BUCKETS, registry=metrics_registry)
    ).instrument(app).expose(app, include_in_schema=False)
    metrics_registry.register(DEPENDENCY_CALL_SECONDS)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/{code}")
    def follow(code: str, request: Request) -> RedirectResponse:
        if not CODE_PATTERN.fullmatch(code):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
        try:
            url = links.resolve(code)
        except LinkServiceError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Link lookup temporarily unavailable",
            ) from exc
        if url is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

        analytics.record_click(code, request.headers.get("referer"))
        return RedirectResponse(url, status_code=status.HTTP_302_FOUND)

    return app
