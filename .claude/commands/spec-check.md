---
description: Verify the current implementation against an epic spec before declaring it done. Usage: /spec-check docs/specs/E3-answer-escalation.md
---

Verify the implementation against the spec at: $ARGUMENTS

HelpFlow is a hybrid repo: backend/widget/console are runnable codebases; n8n logic lives in
workflow JSON + snippets. Verify accordingly. Do this strictly:

1. Read the spec fully. Build a checklist from three sections: **Deliverables** (every file),
   **Requirements** (every numbered item), **Acceptance criteria / Required tests or
   verification** (every check).
2. For each deliverable file: confirm it exists AND actually implements what the spec says
   (read it — existence alone is not a pass). For workflow JSON, confirm the node graph does
   what the requirement describes; for snippets/ports, confirm the logic matches the DocChat/
   LeadFlow source where the spec says "port".
3. For each requirement: cite the `file:line` (or workflow node name) that satisfies it.
   Partial → say exactly what's missing.
4. **Cross-check the CLAUDE.md invariants** for the epic's surface — especially:
   - Grounded-or-handoff: escalation is deterministic; no code path lets the model answer when
     `low_relevance`/sensitive/handoff without escalating.
   - Tenant isolation: every Qdrant search carries the `tenant_id` filter (one choke point);
     console reads go through tenant-scoped masked RLS views, not base tables; `tenant_id` is
     resolved server-side from the widget key, never trusted from the client.
   - Guardrail before any LLM call; zero router calls on the guardrail path.
   - AI-never-talks-over-human: the `human_assigned` guard is the first check after
     conversation load and there is no path around it.
   - Guarded transitions: every conversation/escalation status UPDATE has `AND status='<expected>'`;
     one owner per transition (WF-H writes no status; WF-O owns `abandoned`; console owns claim/resolve).
   - No hardcoded model ids / limits / thresholds / tokens in code or nodes (the ONE allowed
     registry is `backend/llm/catalog.py`); no secrets in the repo; BYOK keys parsed only in
     `backend/llm/runconfig.py`, never logged/stored/echoed.
5. **n8n source-of-truth sync** (for n8n epics): every Code node opens `// source:
   snippets/<file>.js` and its body matches that snippet; mismatch = FAIL (the check-sync invariant).
6. **SSE contract**: for E3/E4/E7, confirm the event shapes (`token`/`seq`, `sources`, `handoff`,
   `human_turn`, `done`, `error`, additive v2 `notice` (`code`, `message`, `links[]`);
   subscribe: `message`, `status`) match between backend and widget — existing shapes frozen.
7. Where the spec's verification names a live check (a run transcript, a SQL assertion, a curl,
   a token-grep, a psql assertion), confirm the developer pasted it in the session summary. If
   missing, mark that item ⚠️ and say what to run.

Output a verdict table: ✅ met / ⚠️ partial / ❌ missing per item, with file:line or node
references, followed by PASS or FAIL overall. FAIL if any requirement or required verification
is ❌, if an n8n source-of-truth mismatch exists, or if any invariant is violated. Do not fix
anything in this pass — report only.
