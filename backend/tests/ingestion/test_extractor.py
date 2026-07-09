"""Extractor tests (spec E2 Required tests): trafilatura-empty -> Jina Reader
fallback invoked; still-empty -> `None` (caller records the skip + error row).
`httpx` is mocked via `respx`-style monkeypatching of the internal fetch
helpers so no real network is used.
"""

from unittest.mock import AsyncMock, patch

from backend.ingestion import extractor


def _good_html() -> str:
    return (
        "<html><head><title>Widgets 101</title></head><body>"
        "<article><h1>Widgets 101</h1>"
        + "<p>" + ("This is a real sentence about widgets. " * 12) + "</p>"
        + "</article></body></html>"
    )


async def test_trafilatura_success_returns_text_and_title_without_jina():
    with (
        patch.object(extractor, "_fetch_html", AsyncMock(return_value=_good_html())),
        patch.object(extractor, "_jina_extract", AsyncMock()) as jina,
    ):
        result = await extractor.extract_page("https://example.com/widgets")

    assert result is not None
    assert "widgets" in result.text.lower()
    assert len(result.text) >= extractor.MIN_EXTRACTABLE_CHARS
    jina.assert_not_awaited()


async def test_trafilatura_too_short_falls_back_to_jina():
    thin_html = "<html><body><p>hi</p></body></html>"  # well under 200 chars
    jina_body = (
        "Title: Widgets 101\n"
        "URL Source: https://example.com/widgets\n"
        "Markdown Content:\n" + ("This is real rendered content. " * 12)
    )

    with (
        patch.object(extractor, "_fetch_html", AsyncMock(return_value=thin_html)),
        patch.object(extractor, "_jina_extract", wraps=extractor._jina_extract) as jina_spy,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.text = jina_body
        mock_resp.raise_for_status = lambda: None
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await extractor.extract_page("https://example.com/widgets")

    jina_spy.assert_awaited_once()
    assert result is not None
    assert result.title == "Widgets 101"
    assert "real rendered content" in result.text


async def test_still_too_short_after_jina_returns_none():
    thin_html = "<html><body><p>hi</p></body></html>"

    with (
        patch.object(extractor, "_fetch_html", AsyncMock(return_value=thin_html)),
        patch.object(
            extractor,
            "_jina_extract",
            AsyncMock(return_value=extractor.ExtractResult(text="still tiny", title="x")),
        ),
    ):
        result = await extractor.extract_page("https://example.com/widgets")

    assert result is None


async def test_unreachable_page_returns_none_without_calling_jina():
    with (
        patch.object(extractor, "_fetch_html", AsyncMock(return_value=None)),
        patch.object(extractor, "_jina_extract", AsyncMock()) as jina,
    ):
        result = await extractor.extract_page("https://example.com/gone")

    assert result is None
    jina.assert_not_awaited()
