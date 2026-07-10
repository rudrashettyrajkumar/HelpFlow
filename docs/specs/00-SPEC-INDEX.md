# SPEC INDEX — HelpFlow (v2.0)

Implement in this order (dependencies flow downward). **One epic per Claude Code session.**
Paste the matching prompt from `docs/BUILD-PROMPTS.md` to start each session.

**v2.0 note:** E1–E3 were built and merged against ARCHITECTURE v1.0 (LiteLLM,
seeded-tenants-only). v2.0 makes HelpFlow self-serve + BYOK on LangChain/LangGraph; their
specs stay with an "as built" banner, and **E4/E5 retrofit** the merged code (see
ARCHITECTURE §13). Old E4–E8 spec files (handoff/widget/console/ship/whatsapp) were
renumbered to E6–E11 in v2.

| ID | Spec | Side | Depends on | Reuses | Skills that should trigger |
|---|---|---|---|---|---|
| ~~E1~~ | foundation ✅ merged (v1) | Backend/Infra | — | — | — |
| ~~E2~~ | ingestion ✅ merged (v1) | Backend | — | — | — |
| ~~E3~~ | answer-escalation ✅ merged (v1) | Backend + AI | — | — | — |
| E4 | model-layer | Backend retrofit | E1–E3 | **DocChat v3 `llm/` + `graph/`** | helpflow-rag, helpflow-conventions |
| E5 | accounts-trials | Backend | E4 | DocChat v2 auth | helpflow-schema, helpflow-conventions |
| E6 | orchestration (WF-H + WF-P) | n8n | E3, E5 | LeadFlow n8n discipline | helpflow-n8n, helpflow-schema |
| E7 | widget | UI | E4, E5, E6 | DocChat frontend patterns | ui-ux-pro-max |
| E8 | portal (landing/wizard/Model Studio/gates) | UI | E5, E7 | DocChat v3 ModelStudio + design system | ui-ux-pro-max |
| E9 | console (inbox/admin/analytics) | UI | E8, E6 | LeadFlow dashboard patterns | helpflow-schema, dataviz |
| E10 | ship | Polish/DevOps | E9 | LeadFlow ship playbook | helpflow-n8n, helpflow-conventions |
| E11 | whatsapp *(optional)* | n8n | E4, E6 | — | helpflow-n8n |

Every spec ends with **Acceptance criteria** and **Required verification**. An epic is
DONE only when: tests pass, `ruff`/`npm run build` is clean, n8n repo-sync is clean where
relevant, and `/spec-check <spec path>` passes.

Commit format: `feat(E4): LangChain factory + LangGraph graph + BYOK catalog` — epic
prefix always.

## Sub-agents note
No custom sub-agents required. Use **Explore** for "where is X in DocChat/LeadFlow
reference code" fan-out searches before porting, and **Plan** if an epic's approach needs
shaping first. `/spec-check` is the verification gate; `.claude/skills/` carry
conventions and trigger by file path.
