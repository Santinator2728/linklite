"""HTTP clients for the services the redirect service depends on (see ADR-001)."""

import logging
import time

import httpx
from prometheus_client import Histogram

logger = logging.getLogger(__name__)

# How long the redirect waits for each service it depends on (XP-45). Compared with the total
# redirect time, this shows how much of the hot path is spent waiting on other services.
# Not in the global registry: the app adds it to its own registry (see main.py).
DEPENDENCY_CALL_SECONDS = Histogram(
    "linklite_dependency_call_seconds",
    "Time the redirect service waits for another service, by dependency and outcome.",
    ["dependency", "outcome"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    registry=None,
)


class _TimedCall:
    """Measures one outgoing call. The outcome stays "error" unless the caller marks it "ok"."""

    def __init__(self, dependency: str) -> None:
        self.dependency = dependency
        self.outcome = "error"

    def __enter__(self) -> "_TimedCall":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        DEPENDENCY_CALL_SECONDS.labels(dependency=self.dependency, outcome=self.outcome).observe(
            time.perf_counter() - self._start
        )


class LinkServiceError(RuntimeError):
    """Raised when the link service cannot be reached or answers unexpectedly."""


class LinkClient:
    def __init__(
        self, base_url: str, timeout: float = 2.0, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def resolve(self, code: str) -> str | None:
        """Return the target URL for a code, or None if the code does not exist."""
        with _TimedCall("link") as call:
            try:
                response = self._http.get(f"/links/{code}")
            except httpx.HTTPError as exc:
                raise LinkServiceError(f"link service unreachable: {exc}") from exc
            if response.status_code == httpx.codes.NOT_FOUND:
                call.outcome = "ok"
                return None
            if response.status_code != httpx.codes.OK:
                raise LinkServiceError(f"link service returned {response.status_code}")
            call.outcome = "ok"
            return response.json()["url"]


class AnalyticsClient:
    def __init__(
        self, base_url: str, timeout: float = 0.5, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def record_click(self, code: str, referrer: str | None) -> None:
        """Best effort: a failure here must never block the redirect."""
        with _TimedCall("analytics") as call:
            try:
                response = self._http.post("/clicks", json={"code": code, "referrer": referrer})
            except httpx.HTTPError as exc:
                logger.warning("Click for %s not recorded: %s", code, exc)
                return
            if response.is_success:
                call.outcome = "ok"
            else:
                logger.warning("Click for %s not recorded: status %s", code, response.status_code)
