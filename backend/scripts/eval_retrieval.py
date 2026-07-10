"""Retrieval quality eval harness (spec E3 deliverable) — NOT a pytest suite.

Run deliberately, against LIVE Qdrant + LIVE OpenRouter embeddings, once `.env` is
filled in and a demo tenant has been seeded (`scripts/seed_demo_tenant.py`):

    python -m backend.scripts.eval_retrieval --tenant-name "HelpFlow Demo"

Runs the 15 hand-written questions in `eval_questions.json` through the real
`retrieval_agent.retrieve()` (bypassing `rewrite_agent` on purpose — this measures
retrieval quality in isolation, the same way DocChat's harness does). The 15
questions default to the docs.python.org/3/tutorial content `seed_demo_tenant.py`
was dry-run against (§ E2 session notes); swap `eval_questions.json` to match
whatever site is actually seeded in a given environment.

Scoring:
- Answerable question (non-null `expected_source_url_substring`) -> HIT if any of
  the top-3 fused chunks' `source_url` contains that substring.
- The one deliberately-unanswerable question (`expected_source_url_substring: null`)
  -> HIT if `low_relevance=True`, i.e. the system correctly recognizes the docs
  don't cover it. This is the signal used to calibrate `RELEVANCE_THRESHOLD`.

Writes `eval_report.md` next to this script and exits non-zero if fewer than
12/15 questions hit (spec E3 acceptance criteria).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from backend.agents.retrieval_agent import RetrievalResult, retrieve
from backend.utils import supabase_client

_QUESTIONS_PATH = Path(__file__).resolve().parent / "eval_questions.json"
_REPORT_PATH = Path(__file__).resolve().parent / "eval_report.md"

_PASS_THRESHOLD = 12
_TOP_N_FOR_SCORING = 3


async def _tenant_id_by_name(name: str) -> str:
    row = await supabase_client.fetchrow("SELECT id FROM tenants WHERE name = $1", name)
    if row is None:
        raise SystemExit(f"No tenant named {name!r} — run scripts/seed_demo_tenant.py first.")
    return str(row["id"])


def _score(question: dict[str, Any], result: RetrievalResult) -> tuple[bool, str]:
    top3 = result.chunks[:_TOP_N_FOR_SCORING]
    expected = question["expected_source_url_substring"]
    if expected:
        hit = any(expected in c.source_url for c in top3)
        reason = (
            "matched expected source_url" if hit else "no top-3 chunk matched expected source_url"
        )
    else:
        hit = result.low_relevance
        reason = (
            "correctly flagged low_relevance"
            if hit
            else "NOT flagged low_relevance (calibrate RELEVANCE_THRESHOLD)"
        )
    return hit, reason


async def _run_questions(tenant_id: str) -> tuple[int, int, list[dict[str, Any]]]:
    questions = json.loads(_QUESTIONS_PATH.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for q in questions:
        result = await retrieve([q["question"]], tenant_id)
        hit, reason = _score(q, result)
        records.append({"question": q, "result": result, "hit": hit, "reason": reason})
    hits = sum(1 for r in records if r["hit"])
    return hits, len(questions), records


def _write_report(hits: int, total: int, records: list[dict[str, Any]]) -> None:
    from backend.utils.config import get_settings

    lines = [
        "# HelpFlow Retrieval Eval Report",
        "",
        f"RELEVANCE_THRESHOLD = {get_settings().RELEVANCE_THRESHOLD}",
        "",
        f"**Result: {hits}/{total} questions hit (pass threshold: {_PASS_THRESHOLD}/{total})**",
        "",
    ]
    for record in records:
        q, result, hit, reason = (
            record["question"],
            record["result"],
            record["hit"],
            record["reason"],
        )
        top3 = result.chunks[:_TOP_N_FOR_SCORING]
        lines.append(f"## Q{q['id']} — {'HIT' if hit else 'MISS'}")
        lines.append(f"**Question:** {q['question']}")
        expected = q["expected_source_url_substring"] or "(none — unanswerable)"
        lines.append(f"**Expected source_url contains:** {expected}")
        lines.append(f"**low_relevance:** {result.low_relevance}  ·  **Reason:** {reason}")
        lines.append("")
        if top3:
            for c in top3:
                snippet = c.text[:160].replace("\n", " ")
                lines.append(f'- [{c.n}] {c.citation_label} — score {c.score:.4f} — "{snippet}..."')
        else:
            lines.append("- (no chunks returned)")
        lines.append("")
    _REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


async def main(tenant_name: str) -> int:
    tenant_id = await _tenant_id_by_name(tenant_name)
    print(f"Running eval questions against tenant {tenant_name!r} ({tenant_id})...")
    hits, total, records = await _run_questions(tenant_id)
    _write_report(hits, total, records)
    print(f"Result: {hits}/{total} — report written to {_REPORT_PATH}")
    return 0 if hits >= _PASS_THRESHOLD else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-name", default="HelpFlow Demo")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.tenant_name)))
