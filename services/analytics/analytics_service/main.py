"""Analytics service: records clicks and answers statistics queries (see ADR-001)."""

import os

from fastapi import FastAPI, status
from pydantic import BaseModel, Field

from analytics_service.store import ClickStore


class ClickEvent(BaseModel):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    referrer: str | None = None


class LinkStats(BaseModel):
    code: str
    total_clicks: int


def create_app(store: ClickStore | None = None) -> FastAPI:
    store = store or ClickStore(os.environ.get("CLICK_DB_PATH", "clicks.db"))
    app = FastAPI(title="LinkLite analytics service")

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
