"""Offline gap clustering (spec E9 Req 4, ARCHITECTURE §5.5) — the analytics
Gap Report's data source.

Batches each tenant's `low_relevance` escalation questions (the same raw rows
`v_gaps`, sql/002, already exposes) through `prompts/gap_cluster.md` on the
demo-chain gateway call (`cfg=DEFAULT` — rides the shared demo chat budget,
same as any other demo-mode call; this is a low-frequency batch job, not a
per-request cost) and writes themed results into `gap_clusters`
(sql/005_gap_clusters.sql), read by the portal through `v_gap_clusters`. A
re-run REPLACES a tenant's prior clustering — this table is a cache of the
latest pass, not a history log.

Degrades per-tenant, never crashes the batch: a malformed LLM response or an
empty question set for one tenant is logged and skipped; every other tenant
still gets clustered.

Run: python -m backend.scripts.cluster_gaps
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.llm import gateway
from backend.llm.runconfig import DEFAULT
from backend.utils import supabase_client

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("helpflow.cluster_gaps")

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "gap_cluster.md"
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")
_MIN_QUESTIONS = 1


async def _tenants_with_gaps() -> list[str]:
    rows = await supabase_client.fetch(
        "SELECT DISTINCT c.tenant_id FROM escalations es "
        "JOIN conversations c ON c.id = es.conversation_id "
        "WHERE es.reason = 'low_relevance'"
    )
    return [str(r["tenant_id"]) for r in rows]


async def _gap_questions(tenant_id: str) -> list[str]:
    """Same shape as `v_gaps` (sql/002) — the latest user message on each
    `low_relevance` escalation for this tenant."""
    rows = await supabase_client.fetch(
        "SELECT ("
        "  SELECT m.body FROM messages m "
        "  WHERE m.conversation_id = c.id AND m.role = 'user' "
        "  ORDER BY m.created_at DESC LIMIT 1"
        ") AS question "
        "FROM escalations es "
        "JOIN conversations c ON c.id = es.conversation_id "
        "WHERE es.reason = 'low_relevance' AND c.tenant_id = $1",
        tenant_id,
    )
    return [r["question"] for r in rows if r["question"]]


def _build_messages(questions: list[str]) -> list[dict[str, Any]]:
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"INPUT QUESTIONS:\n{numbered}"},
    ]


def _parse_themes(raw: str) -> list[dict[str, Any]]:
    text = _FENCE_RE.sub("", (raw or "").strip()).strip()
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array")
    themes = []
    for item in data:
        theme = str(item["theme"]).strip()
        frequency = int(item["frequency"])
        examples = [str(q) for q in item.get("example_questions", [])][:3]
        if not theme or frequency <= 0:
            continue
        themes.append({"theme": theme, "frequency": frequency, "example_questions": examples})
    return themes


async def _replace_clusters(tenant_id: str, themes: list[dict[str, Any]]) -> None:
    await supabase_client.execute("DELETE FROM gap_clusters WHERE tenant_id = $1", tenant_id)
    for theme in themes:
        await supabase_client.execute(
            "INSERT INTO gap_clusters (tenant_id, theme, frequency, example_questions) "
            "VALUES ($1, $2, $3, $4::text[])",
            tenant_id,
            theme["theme"],
            theme["frequency"],
            theme["example_questions"],
        )


async def cluster_tenant(tenant_id: str) -> int:
    """Returns the number of themes written (0 on any degrade — logged, not raised)."""
    questions = await _gap_questions(tenant_id)
    if len(questions) < _MIN_QUESTIONS:
        _log.info("no gap questions; skipping", extra={"tenant_id": tenant_id})
        return 0

    try:
        text = await gateway.complete(
            "gap_cluster", _build_messages(questions), DEFAULT, json_mode=True
        )
        themes = _parse_themes(text)
    except Exception as exc:  # noqa: BLE001 — one tenant's failure must not sink the batch
        _log.warning(
            "gap clustering failed for tenant; skipping",
            extra={"tenant_id": tenant_id, "error": repr(exc)},
        )
        return 0

    await _replace_clusters(tenant_id, themes)
    _log.info(
        "clustered gaps",
        extra={"tenant_id": tenant_id, "questions": len(questions), "themes": len(themes)},
    )
    return len(themes)


async def main(tenant_id: str | None) -> None:
    tenant_ids = [tenant_id] if tenant_id else await _tenants_with_gaps()
    _log.info("clustering gaps", extra={"tenant_count": len(tenant_ids)})
    for tid in tenant_ids:
        await cluster_tenant(tid)
    await supabase_client.close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", default=None, help="Cluster one tenant only")
    args = parser.parse_args()
    asyncio.run(main(args.tenant_id))
