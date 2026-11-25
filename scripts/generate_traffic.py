"""Send some traffic through LinkLite so the Grafana dashboard has data (XP-45).

Creates a few short links and follows them many times through the redirect service.
Usage: python scripts/generate_traffic.py [number_of_redirects]   (services must be running)
"""

import os
import sys
import time

import httpx

LINK_URL = os.environ.get("LINK_URL", "http://localhost:8001")
REDIRECT_URL = os.environ.get("REDIRECT_URL", "http://localhost:8000")
TARGETS = [
    "https://example.com/docs",
    "https://example.com/blog/post",
    "https://example.org/pricing",
]


def main() -> None:
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    with httpx.Client(timeout=5.0) as http:
        codes = [
            http.post(f"{LINK_URL}/links", json={"url": url}).json()["code"] for url in TARGETS
        ]
        statuses: dict[int, int] = {}
        for i in range(total):
            response = http.get(f"{REDIRECT_URL}/{codes[i % len(codes)]}", follow_redirects=False)
            statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
            time.sleep(0.05)
    print(f"Sent {total} redirects, answers by status: {statuses}")


if __name__ == "__main__":
    main()
