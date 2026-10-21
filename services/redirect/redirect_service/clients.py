"""HTTP clients for the services the redirect service depends on (see ADR-001)."""

import logging

import httpx

logger = logging.getLogger(__name__)


class LinkServiceError(RuntimeError):
    """Raised when the link service cannot be reached or answers unexpectedly."""


class LinkClient:
    def __init__(
        self, base_url: str, timeout: float = 2.0, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def resolve(self, code: str) -> str | None:
        """Return the target URL for a code, or None if the code does not exist."""
        try:
            response = self._http.get(f"/links/{code}")
        except httpx.HTTPError as exc:
            raise LinkServiceError(f"link service unreachable: {exc}") from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            raise LinkServiceError(f"link service returned {response.status_code}")
        return response.json()["url"]


class AnalyticsClient:
    def __init__(
        self, base_url: str, timeout: float = 0.5, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def record_click(self, code: str, referrer: str | None) -> None:
        """Best effort: a failure here must never block the redirect."""
        try:
            self._http.post("/clicks", json={"code": code, "referrer": referrer})
        except httpx.HTTPError as exc:
            logger.warning("Click for %s not recorded: %s", code, exc)
