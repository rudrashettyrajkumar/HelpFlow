"""The one 4xx error shape for every pre-stream ingestion check (spec E2 Req 1).

Ported from DocChat `ingestion/errors.py`. `POST /admin/sources` rejects a bad
submission — invalid url, over-cap `max_pages`, a tenant over its crawl-job
rate limit — before opening the SSE stream. Every one of those checks
(`admin_sources.py`, `middleware/rate_limit.py`) raises this ONE exception
type so the API layer can catch it in a single place and return the exact
`{error, detail}` JSON body the admin UI renders directly.
"""

from __future__ import annotations


class IngestValidationError(Exception):
    """A pre-stream submission check failed. `error` is a stable machine code
    for the UI to branch on; `detail` is the human-readable message it can
    show verbatim."""

    def __init__(self, error: str, detail: str, *, status_code: int) -> None:
        self.error = error
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)
