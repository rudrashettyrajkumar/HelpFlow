# SPEC INDEX — HelpFlow

Implement in this order (dependencies flow downward). **One epic per Claude Code session.**
Paste the matching prompt from `docs/BUILD-PROMPTS.md` to start each session.

This is the capstone — larger than DocChat/LeadFlow — so it has **7 core epics + 1 optional**
(E8 WhatsApp). Heavy reuse from #1/#2 keeps each epic small; see the "Reuses" column and each
spec's "Port from" notes.

| ID | Spec | Side | Depends on | Reuses | Skills that should trigger |
|---|---|---|---|---|---|
| E1 | foundation | Backend/Infra | — | DocChat utils, LeadFlow sql/export | helpflow-conventions, helpflow-schema |
| E2 | ingestion | Backend | E1 | DocChat chunker/embed/qdrant | helpflow-rag, helpflow-conventions |
| E3 | answer-escalation | Backend + AI | E2 | DocChat pipeline/agents | helpflow-rag, helpflow-conventions |
| E4 | handoff | n8n | E3 | LeadFlow n8n discipline | helpflow-n8n, helpflow-schema |
| E5 | widget | UI | E3 (API), E4 | DocChat frontend patterns | (none — reads live API) |
| E6 | console | UI | E5, E4 | LeadFlow dashboard patterns | helpflow-schema, dataviz |
| E7 | ship | Polish/DevOps | E6 | LeadFlow ship playbook | helpflow-n8n, helpflow-conventions |
| E8 | whatsapp *(optional)* | n8n | E3, E4 | — | helpflow-n8n |

Every spec ends with **Acceptance criteria** and **Required tests/verification**. An epic is
DONE only when: tests pass, `ruff`/`npm run build` is clean, n8n repo-sync is clean where
relevant, and `/spec-check <spec path>` passes.

Commit format: `feat(E3): escalation decision + streaming answer pipeline` — epic prefix always.

## Sub-agents note
No custom sub-agents are required (same as DocChat/LeadFlow). The built-in agents cover the
gaps: use **Explore** for "where is X in the DocChat/LeadFlow reference code" fan-out
searches before porting, and **Plan** if an epic's approach needs shaping first. The
`/spec-check` command is the verification gate. Skills (`.claude/skills/`) carry the
conventions each epic needs; they trigger automatically by file path.
