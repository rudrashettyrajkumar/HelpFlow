"""Crawler safety tests (spec E2 Required tests, written FIRST per the build
prompt's priority order): same-domain restriction, robots.txt disallow,
asset-URL skipping, and the page cap. All exercised against a fake in-memory
site graph via the injectable `FetchFn` — no real network in unit tests.
"""

from backend.ingestion.crawler import discover


def _site(pages: dict[str, str], *, robots: str = "") -> "list[str] | None":
    """Build a `FetchFn` serving `pages` (url -> html) and a `robots.txt`."""

    async def fetch(url: str) -> str | None:
        if url.endswith("/robots.txt"):
            return robots
        return pages.get(url)

    return fetch


def _link(href: str) -> str:
    return f'<a href="{href}">link</a>'


async def test_same_domain_restriction_excludes_other_hosts():
    start = "https://example.com/"
    pages = {
        start: f"<html><body>{_link('https://example.com/about')}"
        f"{_link('https://other-site.com/steal-me')}</body></html>",
        "https://example.com/about": "<html><body>no links here</body></html>",
    }
    fetch = _site(pages)

    urls = await discover(start, max_pages=10, fetch=fetch)

    assert "https://example.com/about" in urls
    assert all("other-site.com" not in u for u in urls)


async def test_www_prefix_is_treated_as_same_domain():
    start = "https://example.com/"
    pages = {
        start: f"<html><body>{_link('https://www.example.com/blog')}</body></html>",
        "https://www.example.com/blog": "<html><body>ok</body></html>",
    }
    fetch = _site(pages)

    urls = await discover(start, max_pages=10, fetch=fetch)

    assert "https://www.example.com/blog" in urls


async def test_robots_disallow_is_respected():
    start = "https://example.com/"
    pages = {
        start: f"<html><body>{_link('https://example.com/public')}"
        f"{_link('https://example.com/private/secret')}</body></html>",
        "https://example.com/public": "<html><body>ok</body></html>",
        "https://example.com/private/secret": "<html><body>should never be fetched</body></html>",
    }
    robots = "User-agent: *\nDisallow: /private/\n"
    fetch = _site(pages, robots=robots)

    urls = await discover(start, max_pages=10, fetch=fetch)

    assert "https://example.com/public" in urls
    assert "https://example.com/private/secret" not in urls


async def test_asset_and_non_http_links_are_skipped():
    start = "https://example.com/"
    pages = {
        start: (
            "<html><body>"
            f"{_link('https://example.com/report.pdf')}"
            f"{_link('https://example.com/logo.png')}"
            f"{_link('mailto:hello@example.com')}"
            f"{_link('tel:+1234567890')}"
            f"{_link('javascript:void(0)')}"
            f"{_link('#top')}"
            f"{_link('https://example.com/real-page')}"
            "</body></html>"
        ),
        "https://example.com/real-page": "<html><body>ok</body></html>",
    }
    fetch = _site(pages)

    urls = await discover(start, max_pages=10, fetch=fetch)

    assert urls == [start, "https://example.com/real-page"]


async def test_page_cap_is_honored():
    start = "https://example.com/"
    # A chain of 10 pages, each linking only to the next.
    pages = {}
    for i in range(10):
        this_url = start if i == 0 else f"https://example.com/p{i}"
        next_url = f"https://example.com/p{i + 1}"
        pages[this_url] = f"<html><body>{_link(next_url)}</body></html>"
    fetch = _site(pages)

    urls = await discover(start, max_pages=3, fetch=fetch)

    assert len(urls) == 3


async def test_duplicate_links_are_deduped():
    start = "https://example.com/"
    pages = {
        start: f"<html><body>{_link('https://example.com/a')}"
        f"{_link('https://example.com/a')}</body></html>",
        "https://example.com/a": "<html><body>ok</body></html>",
    }
    fetch = _site(pages)

    urls = await discover(start, max_pages=10, fetch=fetch)

    assert urls.count("https://example.com/a") == 1


async def test_sitemap_reads_loc_entries_directly():
    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://example.com/a</loc></url>"
        "<url><loc>https://example.com/b</loc></url>"
        "</urlset>"
    )

    async def fetch(url: str) -> str | None:
        assert url == "https://example.com/sitemap.xml"
        return sitemap_xml

    urls = await discover(
        "https://example.com/", sitemap_url="https://example.com/sitemap.xml",
        max_pages=10, fetch=fetch,
    )

    assert urls == ["https://example.com/a", "https://example.com/b"]


async def test_sitemap_respects_max_pages_cap():
    sitemap_xml = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>https://example.com/{i}</loc></url>" for i in range(20))
        + "</urlset>"
    )

    async def fetch(url: str) -> str | None:
        return sitemap_xml

    urls = await discover(
        "https://example.com/", sitemap_url="https://example.com/sitemap.xml",
        max_pages=5, fetch=fetch,
    )

    assert len(urls) == 5


async def test_unreachable_robots_txt_defaults_to_allow_everything():
    start = "https://example.com/"
    pages = {
        start: f"<html><body>{_link('https://example.com/a')}</body></html>",
        "https://example.com/a": "<html><body>ok</body></html>",
    }

    async def fetch(url: str) -> str | None:
        if url.endswith("/robots.txt"):
            return None  # unreachable
        return pages.get(url)

    urls = await discover(start, max_pages=10, fetch=fetch)

    assert "https://example.com/a" in urls
