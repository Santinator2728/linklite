"""Redirect service: the hot path that sends users to the target URL (see ADR-001)."""

import os
import re
from typing import Protocol

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from redirect_service.clients import AnalyticsClient, LinkClient, LinkServiceError

CODE_PATTERN = re.compile(r"^[A-Za-z0-9]{1,32}$")
SAFE_SCHEMES = ("http://", "https://")


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
        # Defence in depth: never redirect to a non-http(s) target, even if one was stored.
        if not url.lower().startswith(SAFE_SCHEMES):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

        analytics.record_click(code, request.headers.get("referer"))
        return RedirectResponse(url, status_code=status.HTTP_302_FOUND)

    return app
