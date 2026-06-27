# Changelog

All notable changes to Scrutator Academic will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-06-27 — Security Hardening (Phase 2)

### Security (Critical Fixes)
- **SSRF**: Rewrote `core/scraper.py` with `httpx`-native `SSRFSafeTransport` / `SSRFSafeAsyncTransport`; blocks all private/reserved IPv4 **and IPv6** ranges including IPv4-mapped IPv6; DNS-resolves hostnames before connecting to prevent DNS-rebinding attacks.
- **Non-root Docker**: Dockerfile now uses a multi-stage build and runs as `appuser` (non-root). A CI step verifies `whoami != root`.
- **Auth enforcement**: `api/web_ui.py` now **exits with a fatal error** if `SCRUTATOR_WEB_UI_BIND=0.0.0.0` is set without credentials — no more auto-generated throwaway passwords.
- **Docker secrets**: API keys are now passed via Docker secrets mounted at `/run/secrets/`; `KeyManager.read_secret()` reads them before env vars. Keys no longer appear in `docker inspect` or `/proc/self/environ`.
- **Memory integrity**: `memory/storage.py` HMAC-SHA256 signs saved JSON and verifies on load; detects tampered files; sets `chmod 600`.
- **Rate limit 429**: Middleware now returns `JSONResponse(429)` with a `Retry-After: 60` header instead of raising `HTTPException` (which was swallowed by ASGI).
- **httpx-only**: Removed `requests` from `model_provider.py` (Ollama now uses httpx streaming). Strict `Timeout(connect=5.0, ...)` applied to all httpx clients.
- **SQLite WAL**: `core/cache.py` enables WAL mode and checks `PRAGMA integrity_check` on startup.

### Changed
- `requirements.txt`: Removed `requests`; moved test/lint tools to `requirements-dev.txt`.
- `pyproject.toml`: Bumped to `1.0.1`, added `[dev]` extras, ruff/mypy/black config sections.
- `docker-compose.yml`: Port bindings now localhost-only (`127.0.0.1:`), named volumes, `read_only: true`, `no-new-privileges`.
- `.gitignore`: Added `secrets/` directory exclusion.

### Added
- `requirements-dev.txt`: Separate dev/test dependencies.
- `.github/workflows/ci.yml`: GitHub Actions CI (lint, test matrix Python 3.10–3.13, bandit, pip-audit, Docker build + non-root check).
- `.github/dependabot.yml`: Weekly automated dependency updates.
- `secrets/`: Template directory for Docker secret files (git-ignored).

### Removed
- `setup.py`: Replaced by `pyproject.toml` exclusively.
- `.coverage` binary file (was leaking local filesystem paths).

## [1.0.0] - 2026-06-27

### Added
- **Academic Search Engine**: Dynamic integration with ArXiv, PubMed, and OpenAlex.
- **Parallel Queries**: Concurrent search execution using `asyncio.gather` for minimal latency.
- **SQLite Caching**: 7-day TTL cache for query-source results to reduce API requests.
- **Progress & Cancellation**: Real-time thread-safe progress callbacks and `anyio`-based cancel scope task interruption.
- **Full-Text Analysis**: Unpaywall OA checks, CORE API fallback retrieval, and PyMuPDF full-text scorer parsing.
- **Citation Network Builder**: Semantic Scholar graph mapper, network centrality, and common-reference contradiction mapping.
- **Security Hardening**: SSRF IP blacklisting schema checks, DNS pinning HTTPAdapter, and REST API rate-limiting middleware.
- **Inclusion/Exclusion Filters**: Filter papers by publication year, journal impact factor, study designs, and keywords.
- **Hygiene & Compliance**: Added MIT LICENSE, .env.example, structured logging, health checks, and Swagger/OpenAPI support.
