"""Check that the observability layer works on the running system (XP-45).

Prometheus must scrape the three services, and after the smoke test it must have
the redirect's request times and the times of its calls to the other services.

Usage: python tests/system/observability_check.py  (run after tests/system/smoke_test.py)
"""

import os
import sys
import time

import httpx

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")
SERVICES = {"link", "redirect", "analytics"}
WAIT_SECONDS = 60


def query(http: httpx.Client, expr: str) -> list:
    response = http.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr})
    response.raise_for_status()
    return response.json()["data"]["result"]


def wait_for(description: str, condition) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            if condition():
                print(f"ok:   {description}")
                return
        except httpx.HTTPError:
            pass  # Prometheus or Grafana still starting
        time.sleep(2)
    print(f"FAIL: {description} (waited {WAIT_SECONDS}s)")
    sys.exit(1)


def main() -> None:
    with httpx.Client(timeout=5.0) as http:
        wait_for(
            "Prometheus scrapes link, redirect and analytics",
            lambda: {r["metric"]["job"] for r in query(http, "up == 1")} >= SERVICES,
        )
        wait_for(
            "redirect request times are recorded",
            lambda: query(http, 'http_request_duration_seconds_count{handler="/{code}"}'),
        )
        wait_for(
            "times of the calls to link-service and analytics-service are recorded",
            lambda: (
                {
                    r["metric"]["dependency"]
                    for r in query(http, "linklite_dependency_call_seconds_count")
                }
                >= {"link", "analytics"}
            ),
        )
        wait_for(
            "Grafana has loaded the LinkLite dashboard",
            lambda: (
                http.get(f"{GRAFANA_URL}/api/dashboards/uid/linklite-overview").status_code == 200
            ),
        )
    print("Observability check passed")


if __name__ == "__main__":
    main()
