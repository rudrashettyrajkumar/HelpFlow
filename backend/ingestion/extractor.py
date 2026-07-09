"""Fetch + main-content extraction (ARCHITECTURE §3.1 STEP 2, spec E2 Req 3).

`httpx` GET (timeout, 1 retry, realistic UA) → `trafilatura` main-content
extraction, which already strips nav/footer/boilerplate. JS-heavy pages that
trafilatura can't parse (result < `MIN_EXTRACTABLE_CHARS`) get one fallback
attempt through Jina Reader (`https://r.jina.ai/{url}`), a free service that
renders the page and returns clean markdown/text. A page that is STILL too
short after both attempts is not an error the caller should abort on — it is
recorded by `ingest_service` as a `sources` row with `status='error'` and the
crawl continues (spec Req 3: "one failed page never aborts the crawl").

Concurrency is the CALLER's responsibility (`ingest_service` holds the
semaphore around `extract_page`) so this module stays a pure per-URL function,
easy to unit test in isolation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

_log = logging.getLogger("helpflow.extractor")

MIN_EXTRACTABLE_CHARS = 200
_FETCH_TIMEOUT_S = 10.0
_JINA_TIMEOUT_S = 15.0
_USER_AGENT = (
    "Mozilla/5.0 (compatible; HelpFlowBot/1.0; +https://helpflow.example/bot)"
)
_JINA_READER_BASE = "https://r.jina.ai/"


@dataclass(frozen=True)
class ExtractResult:
    text: str
    title: str


async def _fetch_html(url: str) -> str | None:
    """One GET with one retry on transient failure (spec Req 3)."""
    last_exc: Exception | None = None
    async with httpx.AsyncClient(
        timeout=_FETCH_TIMEOUT_S, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
    ) as client:
        for _attempt in range(2):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPError as exc:
                last_exc = exc
    _log.warning("extractor fetch failed twice", extra={"url": url, "error": str(last_exc)})
    return None


def _trafilatura_extract(html: str, url: str) -> ExtractResult | None:
    import trafilatura

    result = trafilatura.bare_extraction(
        html,
        url=url,
        favor_precision=True,
        include_comments=False,
        include_tables=False,
        with_metadata=True,
    )
    if not result:
        return None
    text = (result.text or "").strip()
    title = (result.title or "").strip() or url
    return ExtractResult(text=text, title=title)


async def _jina_extract(url: str) -> ExtractResult | None:
    """Jina Reader fallback for JS-heavy pages trafilatura can't parse."""
    try:
        async with httpx.AsyncClient(timeout=_JINA_TIMEOUT_S) as client:
            resp = await client.get(f"{_JINA_READER_BASE}{url}")
            resp.raise_for_status()
            body = resp.text
    except httpx.HTTPError as exc:
        _log.warning("jina reader fallback failed", extra={"url": url, "error": str(exc)})
        return None

    title = url
    text = body.strip()
    # Jina's reader prefixes a small metadata header before the content:
    #   Title: ...\nURL Source: ...\nMarkdown Content:\n<content>
    lines = body.splitlines()
    if lines and lines[0].startswith("Title:"):
        title = lines[0].removeprefix("Title:").strip() or url
        marker = "Markdown Content:"
        if marker in body:
            text = body.split(marker, 1)[1].strip()
    return ExtractResult(text=text, title=title)


async def extract_page(url: str) -> ExtractResult | None:
    """Fetch `url` and return its main-content text + title, or `None` if no
    usable text could be extracted (caller records this as a `status='error'`
    source row — spec Req 3)."""
    html = await _fetch_html(url)
    if html is None:
        return None

    result = _trafilatura_extract(html, url)
    if result is not None and len(result.text) >= MIN_EXTRACTABLE_CHARS:
        return result

    # trafilatura came back empty/too-short — likely a JS-heavy page. One
    # fallback attempt through Jina Reader before giving up.
    fallback = await _jina_extract(url)
    if fallback is not None and len(fallback.text) >= MIN_EXTRACTABLE_CHARS:
        return fallback

    return None
