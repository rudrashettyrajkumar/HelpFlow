# SPEC E2 — Ingestion: website crawl → extract → chunk → embed → upsert

**Epic:** E2 · **Depends on:** E1 · **Architecture refs:** §3.1, §5.1, §7 (admin)

## Objective
An owner submits their website URL (or sitemap) and HelpFlow crawls it, extracts clean text,
chunks it, embeds it, and upserts to Qdrant under their `tenant_id`, streaming SSE progress.
Plus list/refresh/delete of sources. After this epic, a real site can be ingested via curl
and its chunks verified in Qdrant with correct tenant + source_url payloads.

## Port, don't reinvent
The chunker, batched embeddings, and Qdrant upsert come from DocChat
(`/mnt/d/PortfolioProjects/DocChat/backend/ingestion/chunker.py`, `utils/embeddings.py`,
`utils/qdrant_client.py`). Read them first. The ONLY genuinely new code is the crawler
(discover + fetch + main-content extraction) — DocChat parsed an uploaded PDF; here we
fetch and clean web pages. Everything downstream of "clean text per source_url" is a port.

## Deliverables
```
backend/ingestion/crawler.py          # discover: sitemap <loc> OR same-domain BFS; robots.txt; MAX_PAGES cap
backend/ingestion/extractor.py        # httpx fetch → trafilatura main-content; Jina Reader fallback; boilerplate strip
backend/ingestion/chunker.py          # ported DocChat chunker, url/title-tracked instead of page-tracked
backend/ingestion/ingest_service.py   # orchestrates the 5 steps, yields SSE progress, records sources rows
backend/api/admin_sources.py          # POST (SSE) / GET / POST refresh / DELETE
backend/middleware/rate_limit.py      # Redis counters: crawl jobs/tenant/day, plus chat limits stub for E3
backend/scripts/seed_demo_tenant.py   # creates a demo tenant + crawls a chosen public site (for the demo)
backend/tests/ (crawler, extractor, chunker golden, ingest_service, admin API)
```

## Requirements
1. **Auth + validation before any work**: admin bearer token; `url`/`sitemap_url` is a valid
   http(s) URL; `max_pages ≤ MAX_PAGES`; tenant crawl-job rate limit. Each failure →
   structured 4xx JSON `{error, detail}` the admin UI renders directly.
2. **Discover** (`crawler.py`): if a sitemap is given, read its `<loc>` entries; else BFS
   from the URL, **same registrable domain only**, honoring `robots.txt` (skip disallowed),
   skipping binary/asset extensions (pdf/jpg/zip/…) and mailto/tel/anchor links, deduping
   URLs, capped at `max_pages`. Bounded queue; never crawl the whole internet.
3. **Extract** (`extractor.py`): `httpx` GET (timeout, 1 retry, realistic UA), concurrency
   limited (semaphore, default 5); main-content extraction via `trafilatura`; if that yields
   < 200 chars (JS-heavy page), fall back once to Jina Reader `https://r.jina.ai/{url}`.
   Strip nav/footer boilerplate. A page still < 200 chars of real text → skipped, recorded
   as a source row with `status='error'`, `error='no extractable text'`. One failed page
   never aborts the crawl (degrade, continue).
4. **Chunk** (ported): CHUNK_TOKENS/CHUNK_OVERLAP (tiktoken cl100k_base), prefer paragraph
   boundaries, hard-split oversized paragraphs, carry `source_url`/`page_title`/`chunk_index`
   through splits. No page numbers — the citation unit is the URL.
5. **Embed** in batches of 100 via `utils/embeddings.py`; failed batch retries once then the
   crawl aborts cleanly with an SSE error event and **deletes any points already upserted for
   this crawl** (no half-ingested tenant). Async semaphore respected.
6. **Upsert**: point id = UUID5(source_id, chunk_index); payload EXACTLY per §5.1
   `{tenant_id, source_id, source_url, page_title, chunk_index, text, created_at}`.
7. **Sources rows** (Supabase): one row per crawled page with `status` (crawling→ready|error),
   `chunk_count`, `crawled_at`. GET `/admin/sources` lists them tenant-scoped. **Refresh**:
   delete that source's Qdrant points by `source_id` filter, re-ingest. **Delete**: remove
   points + row (tenant-ownership checked — a tenant can't touch another's sources).
8. **Progress SSE**: events `{stage:"discovering"}`, `{stage:"fetching", done:N, total:M}`,
   `{stage:"embedding", pct:60}`, terminal `{stage:"ready", pages:N, chunks:N}` or
   `{stage:"error", detail}`. The admin UI (E6) binds to these exact shapes.

## Acceptance criteria
- `curl` submitting a small real docs site (or the seeded demo site) streams progress and
  lands N chunks in Qdrant with correct `tenant_id` + `source_url` payloads (spot-check 3).
- A JS-heavy page that trafilatura can't parse is recovered via the Jina fallback (or cleanly
  skipped + recorded) — the crawl still finishes.
- Refresh re-crawls without leaving stale points (count before == count after for an
  unchanged page; old points gone for a removed page). Delete removes every point for a source.
- A crawl exceeding `max_pages` stops at the cap; a disallowed-by-robots path is skipped.

## Required tests
- chunker: golden test — fixed input text → exact chunk boundaries, overlap correctness,
  url/title mapping across a chunk boundary. (Ported DocChat golden test, adapted.)
- crawler: same-domain restriction, robots disallow respected, asset URLs skipped, page cap
  honored (mock the fetch layer).
- extractor: trafilatura-empty → Jina fallback invoked; still-empty → skipped + error row.
- ingest_service: mocked embed+qdrant — progress event sequence; mid-embed failure → rollback
  deletes prior points for the crawl.
- API: rejection cases (bad url, over cap, rate-limited); ownership check on refresh/delete.
