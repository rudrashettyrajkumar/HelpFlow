"""Deterministic input/output rails — plain Python, zero new deps, zero LLM cost.

Ported from DocChat `utils/guardrails.py` (CLAUDE.md invariant #3: the input
guardrail runs BEFORE any LLM call and blocked messages are never stored). No
agent framework — a small, high-precision rail taxonomy instead:

* **Input rail** — `check_input()` scans the raw user message for unambiguous
  prompt-injection shapes (instruction override, prompt exfiltration, jailbreak
  keywords, role/template smuggling). A hit short-circuits the pipeline to a
  canned refusal: zero LLM tokens, no persistence (injection text must never be
  replayed into a later prompt).
* **Output rail** — `guard_stream()` wraps the answerer's token stream and trips
  if the model starts echoing internal prompt-block markers ([CONTEXT]/
  [HISTORY]/[QUESTION], the labels the answer prompt is assembled with in E3).

Bias: HIGH precision. A false positive deflects a real customer's honest support
question — worse than letting a clumsy injection through to the model, whose
grounding-only prompt (E3 citation_rules.md) is the second layer. Only phrasings
with no plausible innocent reading match: "does your refund policy override the
one on the invoice" must pass.

The deflection copy lives in `backend/prompts/guardrails.md` (never in Python),
variants split on `---` lines.
"""

from __future__ import annotations

import random
import re
from collections.abc import AsyncIterator
from functools import cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_GUARDRAILS_PATH = _PROMPTS_DIR / "guardrails.md"


class GuardrailTripped(RuntimeError):
    """The output rail detected internal prompt content leaking into the reply."""


# --------------------------------------------------------------------------- input rail
# Punctuation folds to spaces, so "Ignore   your--instructions!!" and "ignore
# your instructions" match the same phrase rules.
_SEPARATORS = re.compile(r"[\W_]+", re.UNICODE)

# Phrase rules run on NORMALIZED text. Each needs a qualifier that ties the verb
# to HelpFlow's OWN instructions ("your/previous/system …"), so questions about
# the business's content like "does this policy override the previous one" never
# match.
_PHRASE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b[\w ]{0,30}"
            r"\b(your|previous|prior|above|earlier|initial|original|system)\s+"
            r"(instructions?|prompts?|rules?|guidelines?|programming|training)\b"
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"\bsystem prompt\b"
            r"|\b(show|reveal|print|repeat|display|leak|share|give me|tell me)\b[\w ]{0,30}"
            r"\byour (hidden |secret |initial |original )?(prompt|instructions)\b"
        ),
    ),
    (
        "jailbreak",
        re.compile(
            r"\bjail ?break\b|\bdan mode\b|\bdeveloper mode\b|\bdo anything now\b"
            r"|\b(act|role ?play) as (chatgpt|gpt|claude|gemini|dan|an ai without)\b"
            # Matched against NORMALIZED text: the separator fold turns an
            # apostrophe into a space, so "you're" arrives as "you re".
            r"|\bpretend (to be|you re|you are) (chatgpt|gpt|claude|gemini|dan)\b"
        ),
    ),
)

# Markup rules run on the RAW text (normalization would strip the very characters
# that make them attacks): smuggled role headers and chat-template tags.
_MARKUP_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("role_smuggling", re.compile(r"(?im)^\s*(system|assistant|developer)\s*:")),
    (
        "template_smuggling",
        re.compile(r"(?i)</?(system|sys|instructions?)>|\[/?(system|inst)\]|<<sys>>"),
    ),
)


def check_input(text: str) -> str | None:
    """The category of an unambiguous injection attempt, or None to let the turn proceed.

    Pure, deterministic, no I/O, never raises.
    """
    if not text:
        return None
    for category, pattern in _MARKUP_RULES:
        if pattern.search(text):
            return category
    normalized = _SEPARATORS.sub(" ", text.lower()).strip()
    for category, pattern in _PHRASE_RULES:
        if pattern.search(normalized):
            return category
    return None


@cache
def _responses() -> tuple[str, ...]:
    """The deflection variants from prompts/guardrails.md (split on `---` lines)."""
    raw = _GUARDRAILS_PATH.read_text(encoding="utf-8")
    parts = (part.strip() for part in raw.split("\n---\n"))
    variants = tuple(p for p in parts if p.strip("- \n"))
    if not variants:  # a broken/empty file must never break the turn
        return ("Sorry, I can't help with that. Ask me about how we can help you.",)
    return variants


def deflection() -> str:
    """One canned deflection line, chosen at random so repeats don't feel scripted."""
    return random.choice(_responses())  # noqa: S311 — not cryptographic, just variety


# --------------------------------------------------------------------------- output rail
# The internal prompt-block labels the answer prompt is assembled with (E3,
# ARCHITECTURE §6). The answerer's prose never contains bracketed markers, so any
# of these in the output means the model is echoing its own prompt structure.
_LEAK_MARKERS: tuple[str, ...] = ("[CONTEXT]", "[HISTORY]", "[QUESTION]")
# The tail window keeps marker detection O(1) per token while still catching a
# marker split across token boundaries; comfortably longer than the longest marker.
_TAIL_CHARS = 32


async def guard_stream(tokens: AsyncIterator[str]) -> AsyncIterator[str]:
    """Yield `tokens` through, tripping `GuardrailTripped` if a prompt-block marker appears.

    The offending token is never yielded; earlier tokens may already have
    streamed, which is acceptable — the markers sit at the START of leaked
    prompt content. The raised error is handled by the SSE producer's catch-all
    (→ the one error event), so the turn degrades like any other stream failure.
    """
    tail = ""
    async for token in tokens:
        tail = (tail + token)[-_TAIL_CHARS:]
        if any(marker in tail for marker in _LEAK_MARKERS):
            raise GuardrailTripped("prompt-block marker in model output")
        yield token
