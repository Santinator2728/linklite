"""Link service: creates and reads short links (see docs/adr/ADR-001)."""

import os

from fastapi import FastAPI, HTTPException, status
from prometheus_client import CollectorRegistry
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from pydantic import BaseModel

from link_service.store import LinkStore
from link_service.validation import InvalidURLError, validate_url

# Request time buckets in seconds, fine enough to see the few milliseconds of an internal call.
LATENCY_BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)


class CreateLinkRequest(BaseModel):
    url: str


class LinkResponse(BaseModel):
    code: str
    url: str


def create_app(store: LinkStore | None = None) -> FastAPI:
    store = store or LinkStore(os.environ.get("LINK_DB_PATH", "links.db"))
    app = FastAPI(title="LinkLite link service")
    # Prometheus metrics at /metrics (request count and time per endpoint), see XP-45.
    # Registered before the routes so that /metrics is not taken by a catch-all route.
    metrics_registry = CollectorRegistry()
    Instrumentator(excluded_handlers=["^/metrics$", "^/health$"], registry=metrics_registry).add(
        metrics.default(latency_lowr_buckets=LATENCY_BUCKETS, registry=metrics_registry)
    ).instrument(app).expose(app, include_in_schema=False)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/links", status_code=status.HTTP_201_CREATED)
    def create_link(request: CreateLinkRequest) -> LinkResponse:
        try:
            url = validate_url(request.url)
        except InvalidURLError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
        link = store.create(url)
        return LinkResponse(code=link.code, url=link.url)

    @app.get("/links/{code}")
    def get_link(code: str) -> LinkResponse:
        link = store.get(code)
        if link is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
        return LinkResponse(code=link.code, url=link.url)

    return app
