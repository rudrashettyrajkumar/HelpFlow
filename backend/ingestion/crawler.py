"""Discover: sitemap `<loc>` list OR same-domain BFS (ARCHITECTURE §3.1 STEP 1,
spec E2 Req 2).

This is the ONE genuinely new module in E2 — DocChat parsed an uploaded PDF, so
there was no crawl-safety surface to design. Everything here exists to answer
one question honestly: "never crawl the whole internet." Same registrable
domain only, `robots.txt` honored, binary/asset URLs and non-http(p) schemes
skipped, deduped, hard-capped at `max_pages`.

`fetch` is injected (`FetchFn`) so tests exercise domain/robots/asset-skip/cap
logic against a fake in-memory site graph — no network in unit tests (spec
Required tests: "mock the fetch layer").
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx

from backend.utils.config import get_settings

_log = logging.getLogger("helpflow.crawler")

# Realistic UA — some sites block the default httpx/python UA outright.
_USER_AGENT = (
    "Mozilla/5.0 (compatible; HelpFlowBot/1.0; +https://helpflow.example/bot)"
)
_FETCH_TIMEOUT_S = 10.0

# Extensions that are never page content — skip without fetching (spec Req 2).
_ASSET_EXTENSIONS = frozenset(
    {
        "pdf", "jpg", "jpeg", "png", "gif", "svg", "webp", "ico", "bmp",
        "zip", "gz", "tar", "rar", "7z",
        "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "css", "js", "json", "xml",
        "mp3", "mp4", "avi", "mov", "wav", "webm",
        "woff", "woff2", "ttf", "eot", "otf",
    }
)

# Fetch a URL's raw text; None signals "could not fetch, skip" (network error,
# non-2xx, non-HTML content-type). Injectable for tests.
FetchFn = Callable[[str], Awaitable[str | None]]


async def _http_fetch(url: str) -> str | None:
    """Default `FetchFn`: one httpx GET, realistic UA, short timeout."""
    try:
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT_S, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "html" not in content_type and "xml" not in content_type:
                return None
            return resp.text
    except httpx.HTTPError as exc:
        _log.warning("crawler fetch failed", extra={"url": url, "error": str(exc)})
        return None


def _registrable_host(url: str) -> str:
    """Simplified same-domain key: lowercased host with a leading `www.`
    stripped. Demo-scale simplification (no public-suffix-list lookup) — good
    enough to keep a BFS crawl from wandering off the submitted site."""
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def _is_asset_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if "." not in path.rsplit("/", 1)[-1]:
        return False
    ext = path.rsplit(".", 1)[-1]
    return ext in _ASSET_EXTENSIONS


def _is_crawlable_link(href: str) -> bool:
    """Reject mailto:/tel:/javascript:/bare-fragment links before they ever
    reach the queue (spec Req 2)."""
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
        return False
    scheme = urlparse(href).scheme
    return scheme in ("", "http", "https")


def _extract_links(base_url: str, html: str) -> list[str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not _is_crawlable_link(href):
            continue
        absolute = urljoin(base_url, href)
        # Drop the fragment — #section links are the same page for crawl purposes.
        absolute = absolute.split("#", 1)[0]
        if absolute:
            links.append(absolute)
    return links


async def _load_robots(start_url: str, fetch: FetchFn) -> RobotFileParser:
    """Best-effort robots.txt: an unreachable/missing robots.txt means "allow
    everything" (errors degrade, never break) — it never blocks a crawl the
    site itself doesn't gate."""
    parsed = urlparse(start_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    body = await fetch(robots_url)
    rp.parse((body or "").splitlines())
    return rp


async def _discover_sitemap(sitemap_url: str, *, max_pages: int, fetch: FetchFn) -> list[str]:
    """Read `<loc>` entries out of a sitemap (or a sitemap index one level
    deep), capped at `max_pages`."""
    body = await fetch(sitemap_url)
    if not body:
        return []
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        _log.warning("sitemap is not valid XML", extra={"url": sitemap_url})
        return []

    locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
    # A sitemap INDEX points at other sitemaps rather than pages; one level of
    # recursion covers the common case without risking unbounded fan-out.
    if root.tag.endswith("sitemapindex"):
        pages: list[str] = []
        for sub_url in locs:
            if len(pages) >= max_pages:
                break
            sub_body = await fetch(sub_url)
            if not sub_body:
                continue
            try:
                sub_root = ElementTree.fromstring(sub_body)
            except ElementTree.ParseError:
                continue
            pages.extend(
                el.text.strip() for el in sub_root.iter() if el.tag.endswith("loc") and el.text
            )
        return pages[:max_pages]
    return locs[:max_pages]


async def discover(
    start_url: str,
    *,
    sitemap_url: str | None = None,
    max_pages: int | None = None,
    fetch: FetchFn = _http_fetch,
) -> list[str]:
    """Return up to `max_pages` crawlable page URLs.

    If `sitemap_url` is given, read its `<loc>` list directly. Otherwise BFS
    from `start_url`: same registrable domain only, `robots.txt`-honoring,
    asset/mailto/tel/anchor links skipped, deduped, bounded queue.
    """
    cap = max_pages if max_pages is not None else get_settings().MAX_PAGES

    if sitemap_url:
        return await _discover_sitemap(sitemap_url, max_pages=cap, fetch=fetch)

    home = _registrable_host(start_url)
    robots = await _load_robots(start_url, fetch)

    seen: set[str] = {start_url}
    queue: deque[str] = deque([start_url])
    pages: list[str] = []

    while queue and len(pages) < cap:
        url = queue.popleft()
        if not robots.can_fetch(_USER_AGENT, url):
            continue
        html = await fetch(url)
        if html is None:
            continue
        pages.append(url)
        if len(pages) >= cap:
            break
        for link in _extract_links(url, html):
            if link in seen or _is_asset_url(link):
                continue
            if _registrable_host(link) != home:
                continue
            seen.add(link)
            queue.append(link)

    return pages
