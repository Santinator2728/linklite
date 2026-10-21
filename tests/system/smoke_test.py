"""End-to-end smoke test of the running system (docker compose).

Checks the HTTP contracts between the services described in ADR-001:
link-service creates a link, redirect-service resolves it through link-service
and records the click in analytics-service.

Usage: python tests/system/smoke_test.py  (services must be running)
"""

import os
import sys

import httpx

LINK_URL = os.environ.get("LINK_URL", "http://localhost:8001")
REDIRECT_URL = os.environ.get("REDIRECT_URL", "http://localhost:8000")
ANALYTICS_URL = os.environ.get("ANALYTICS_URL", "http://localhost:8003")
TARGET = "https://example.com/tutorial"


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}")
        sys.exit(1)
    print(f"ok:   {message}")


def main() -> None:
    with httpx.Client(timeout=5.0) as http:
        created = http.post(f"{LINK_URL}/links", json={"url": TARGET})
        check(created.status_code == 201, f"link-service creates a link ({created.status_code})")
        code = created.json()["code"]

        redirect = http.get(f"{REDIRECT_URL}/{code}", follow_redirects=False)
        check(redirect.status_code == 302, f"redirect-service answers 302 ({redirect.status_code})")
        check(redirect.headers.get("location") == TARGET, "redirect points to the original URL")

        stats = http.get(f"{ANALYTICS_URL}/stats/{code}").json()
        check(stats["total_clicks"] == 1, f"analytics-service counted the click ({stats})")

        rejected = http.post(f"{LINK_URL}/links", json={"url": "javascript:alert(1)"})
        check(rejected.status_code == 422, "link-service rejects a javascript: URL")

        unknown = http.get(f"{REDIRECT_URL}/doesNotExist", follow_redirects=False)
        check(unknown.status_code == 404, "redirect-service answers 404 for an unknown code")

    print("Smoke test passed")


if __name__ == "__main__":
    main()
