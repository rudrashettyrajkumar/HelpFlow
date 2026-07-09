---
name: helpflow-rag
description: HelpFlow RAG + web-crawl patterns — tenant-filtered Qdrant multi-tenancy, website crawling & main-content extraction, url-tracked chunking, batched embeddings, RRF fusion, and the relevance-threshold → escalation rule. Use when working on ingestion, retrieval, or anything touching Qdrant.
---

# HelpFlow RAG & crawl patterns

Ported from DocChat's qdrant-rag skill; swaps PDF-upload for website-crawl and session for
tenant, and adds the "low relevance → escalate, don't guess" rule that is this project's soul.

## Multi-tenant Qdrant (the isolation invariant)
```
Collection: helpflow_chunks   (768 dims, cosine)
Payload:    tenant_id (keyword, indexed)  ← MANDATORY filter on EVERY search
            source_id (keyword, indexed)  ← per-source delete / re-crawl
            source_url, page_title, chunk_index, text, created_at
```
- ONE collection, `must=[FieldCondition(key="tenant_id", match=tenant_id)]` on every search,
  applied at the ONE choke point in `retrieval_agent.py` — never at call sites, so it can't be
  forgotten. A test asserts every search call includes it AND that tenant A can't read
  tenant B's chunks. Per-tenant collections are an anti-pattern (free-tier limits) — don't.
- Point id = `UUID5(source_id, chunk_index)` so re-crawl overwrites cleanly.
- Delete/refresh a source = delete points by `source_id` filter, then re-ingest. No ghosts.

## Website crawl (the new part vs DocChat)
- **Discover**: sitemap `<loc>` list if given, else bounded same-registrable-domain BFS.
  Honor `robots.txt`; skip asset extensions (pdf/jpg/png/zip/css/js…) and mailto/tel/anchors;
  dedupe URLs; hard cap at `MAX_PAGES`. Never crawl off-domain or unbounded.
- **Extract**: `httpx` GET (timeout, 1 retry, real UA), concurrency-limited (semaphore ~5) →
  `trafilatura` main-content extraction. If < 200 chars (JS-heavy), fall back ONCE to Jina
  Reader `https://r.jina.ai/{url}`. Still < 200 → skip + record a `sources` row `status='error'`.
  One failed page never aborts the crawl (degrade, continue).
- The citation unit is the **URL**, not a page number. Carry `source_url` + `page_title`.

## Chunking (ported DocChat chunker)
- 450 tokens, 80 overlap (tiktoken `cl100k_base`), prefer paragraph boundaries, hard-split
  oversized paragraphs. Track `source_url`/`page_title`/`chunk_index` through splits and
  overlaps. Golden-test it — it's the most bug-prone code. Constants live in config.

## Embeddings (ported)
- `gemini-embedding-001` @ 768, batches of 100. Failed batch retries once then aborts the
  crawl cleanly (SSE error) and deletes points already upserted for that crawl. Async
  semaphore respected. Query embeds: all rewritten queries in ONE batched call.

## Retrieval + RRF + the escalation threshold
- Multi-query (1–3 rewritten queries) → one batched embed → parallel filtered searches top-8
  → `reciprocal_rank_fusion(k=60)` (ported verbatim from DocChat `utils/rrf.py`) → dedup →
  top 6. Label each `[n] {page_title} — {source_url}`. No cross-encoder reranker (RRF over
  multi-query captures the recall benefit at zero latency/cost — same call as DocChat).
- **`low_relevance = best raw cosine < RELEVANCE_THRESHOLD` (env, default 0.30).** This flag
  is NOT just for the prompt — it feeds `escalation.py`: low relevance means the docs don't
  cover the question, so **escalate to a human instead of answering**. Calibrate the threshold
  with `eval_retrieval.py` (include a deliberately-unanswerable question to observe its score).
- Grounding is the product's soul: if the chunks don't contain the answer, the model says so
  and offers a human — it never fills the gap. Clients fear hallucinating bots more than they
  value clever answers; the README showcases this.
