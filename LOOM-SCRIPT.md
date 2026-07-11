# Loom script — HelpFlow (target: 3–4 minutes)

Audience: a non-technical Upwork client who has seen a bad chatbot demo and is
skeptical. Two jobs in this Loom: (1) prove the bot won't lie to their customers, (2)
let them believe they could try this themselves in two minutes, because they can.

Screen-record at normal speed except where noted "speed up." Voice is conversational,
not a pitch-deck read. Keep the cursor deliberate — no frantic mouse movement, it reads
as nervous.

---

## Beat 1 — Landing widget (0:00–0:25)

**Show:** Portal landing page, live demo widget already visible.

**Say:** "This is HelpFlow — an AI support agent that answers questions from a
business's own website, and knows when to stop and get a human instead of making
something up. This chat widget on the landing page right now is talking to a live,
seeded demo business — nothing staged, nothing scripted. Watch."

**Do:** Type a normal question into the widget ("What are your business hours?" or
similar, matched to the seeded demo content). Let the streamed answer arrive with its
citation chip visible.

---

## Beat 2 — Wizard crawl (0:25–1:00, speed up the crawl wait 2x)

**Show:** Register → new workspace → paste a real URL.

**Say:** "Now let's do it on a real site — I'll paste a URL and watch it learn the
content live." *(paste URL, hit go)* "It's crawling the pages right now, same as a new
support hire skimming your docs before their first shift."

**Do:** Let the SSE crawl progress UI run (discovering → fetching n/25 → embedding →
ready). Speed this segment up in editing if it takes more than ~15 real seconds.

---

## Beat 3 — Cited answer (1:00–1:25)

**Show:** Chat with the freshly-crawled workspace.

**Say:** "Now it's answering from THAT site's content — and every answer is grounded,
with a citation back to the exact page. No black box."

**Do:** Ask a question the crawled content actually answers. Click the citation chip to
show the sources drawer.

---

## Beat 4 — Refund escalation (1:25–1:50)

**Show:** Same chat.

**Say:** "Here's the part that actually matters. Watch what happens when I ask
something it shouldn't guess at."

**Do:** Type "I want a refund." Let the deterministic escalation fire — the warm
handoff message appears, no hallucinated policy.

**Say (as it happens):** "It didn't make up a refund policy. It stopped, and it's
getting a human right now."

---

## Beat 5 — Slack ping (1:50–2:05)

**Show:** Cut to a Slack window already open on the alert channel.

**Say:** "That escalation just fired a real alert — Slack and email, within seconds."

**Do:** Show the `:rotating_light: Escalation` message landing (timestamp visible,
ideally captured live rather than pre-recorded).

---

## Beat 6 — Console takeover (2:05–2:30)

**Show:** Cut to the console inbox.

**Say:** "I claim it from the inbox — and now I'm talking to that same customer, live,
in the same window they never left."

**Do:** Click the conversation, click **Claim**, type a short human reply, send it.

---

## Beat 7 — Live reply in widget (2:30–2:45)

**Show:** Cut back to the widget.

**Say:** "No dropped context, no 'please repeat your issue.' Same conversation, now
with a person."

**Do:** Show the reply arriving live + the "A human joined" banner.

---

## Beat 8 — Gap report (2:45–3:05)

**Show:** Console → Analytics → Gap Report.

**Say:** "The dashboard also tells you what your documentation is missing — not just
how the bot performed, but what your customers are actually asking that your docs
don't cover yet. That's a to-do list, not just a scorecard."

**Do:** Point at a theme with example questions.

---

## Beat 9 — Demo-exhausted card (3:05–3:25)

**Show:** Trigger (or use a pre-triggered) demo-budget-exhausted state in the widget.

**Say:** "One more honesty check. This whole demo runs on a shared free daily budget of
open-source models — and when that budget runs out for the day, instead of a cryptic
error, it tells you exactly that, with one-click links to get your own free key in
about two minutes. No credit card."

**Do:** Show the designed `notice` card with the "Get a Groq key" / "Get an OpenRouter
key" buttons.

---

## Beat 10 — Model Studio with a real key (3:25–3:50)

**Show:** Model Studio.

**Say:** "And that's not a hypothetical — here's a real free key, pasted in, tested
live." *(paste key, click test, show "key works ✓")* "It's stored only in my browser.
It's never sent to my database — I built it that way on purpose, not just promised it."

**Do:** Select the validated model, show the config chip appear in the preview widget
composer.

---

## Beat 11 — Premium gate (3:50–4:10)

**Show:** Create a third workspace → the gate screen.

**Say:** "Every account gets two free workspaces, no strings. Want a third, or a real
deployment for your business — that's this screen. No hard paywall, just an honest
'let's talk.'"

**Do:** Show the warm gate screen (name/photo/LinkedIn/WhatsApp/email + short form).
Optionally submit it live and cut to the Slack DM landing (this is the same WF-P
workflow that generates real leads from real visitors).

---

## Closing line (4:10–4:20)

**Say:** "That's HelpFlow — grounded answers when it knows, a real human when it
doesn't, and you can go verify all of it yourself right now at `<PORTAL_URL>`."

---

## Production notes

- Record beats 1–4 and 6–8 in one continuous take if possible — the escalation → Slack
  → claim → reply loop reads better unbroken. Beats 9–11 can be a separate take spliced
  in (different account state).
- Have the Slack window and console pre-arranged in visible tabs/windows before
  recording — no fumbling to find them mid-take.
- Keep total runtime under 4:30. This audience is skeptical, not patient — the trust
  proof (beats 4–7) is the part that can't be cut; the rest can be trimmed if running
  long.
