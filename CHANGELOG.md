# Changelog

All notable changes to Scrutator Academic will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
