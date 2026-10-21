# LinkLite

URL shortener with click analytics, built as the vehicle for an intelligent CI/CD pipeline with AI-augmented quality gates (X-Ops course project, UBI 2026/27).

Project management: Jira project `XP` (https://guerreroortiz4.atlassian.net).

## Architecture

Three small FastAPI services, each owning its data (see [ADR-001](docs/adr/ADR-001-architectural-style.md)):

| Service | Port (local) | Responsibility |
|---|---|---|
| `link` | 8001 | Validate URLs, create and read short links |
| `redirect` | 8000 | Resolve a short code and redirect (hot path) |
| `analytics` | 8003 | Record clicks and return statistics |

## Run

```bash
docker compose up --build
curl -X POST localhost:8001/links -H 'Content-Type: application/json' -d '{"url": "https://example.com"}'
curl -i localhost:8000/<code>
```

## Develop

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest --cov
```

## Pipeline

Every pull request and push to `main` runs [CI](.github/workflows/ci.yml): lint (ruff) → unit tests with coverage ≥ 80% (pytest) → SAST (Semgrep) → build images and smoke test with Docker Compose.
