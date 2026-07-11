// Daily-digest formatter for WF-O (spec E10 Req 1). Pure: turns the three
// upstream fetches (per-tenant stats rows, the one-row account stats, the
// Upstash demo-budget mget response) into one Slack text + one Gmail
// subject/body. Real counts only — a stat the query couldn't produce renders
// as "n/a", never invented. The Upstash call is continueOnFail upstream, so a
// dead Redis shows the budget as "n/a" instead of killing the digest.
function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function pct(rate) {
  if (rate === null || rate === undefined || rate === "") return "n/a";
  const n = Number(rate);
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : "n/a";
}

function budgetLine(used, cap) {
  if (used === null || used === undefined) return `n/a of ${cap ?? "?"}`;
  return `${used} of ${cap ?? "?"}`;
}

function formatDigest(tenants, account, budget, env, now) {
  const day = (now instanceof Date ? now : new Date(now || Date.now()))
    .toISOString()
    .slice(0, 10);

  const tenantLines = tenants.length
    ? tenants.map((t) => {
        const head =
          `*${t.tenant_name}* — ${t.conversations_24h ?? 0} conversation(s) in 24h · ` +
          `deflection ${pct(t.deflection_rate)} all-time (${t.total_conversations ?? 0} total) · ` +
          `${t.open_escalations ?? 0} open escalation(s)`;
        return t.top_gaps ? `${head}\n    gaps: ${t.top_gaps}` : head;
      })
    : ["(no tenants yet)"];

  const accountLine =
    `*Accounts:* ${account.trial_signups_24h ?? "n/a"} trial signup(s) · ` +
    `${account.premium_leads_24h ?? "n/a"} premium lead(s) in 24h ` +
    `(${account.premium_leads_total ?? "n/a"} all-time)`;

  const budgetText =
    `*Demo budget today (UTC):* chat ${budgetLine(budget.chatUsed, env.DEMO_CHAT_DAILY)} · ` +
    `embed ${budgetLine(budget.embedUsed, env.DEMO_EMBED_DAILY)}`;

  const slackText =
    `:newspaper: *HelpFlow daily digest — ${day}*\n` +
    `${tenantLines.join("\n")}\n` +
    `${accountLine}\n` +
    `${budgetText}\n` +
    `Console: ${env.CONSOLE_BASE_URL || ""}`;

  const emailSubject = `[HelpFlow] Daily digest — ${day}`;
  const emailBody =
    `<h3>HelpFlow daily digest — ${day}</h3>` +
    `<ul>${tenants
      .map(
        (t) =>
          `<li><strong>${escapeHtml(t.tenant_name)}</strong> — ` +
          `${t.conversations_24h ?? 0} conversation(s) in 24h · ` +
          `deflection ${pct(t.deflection_rate)} all-time (${t.total_conversations ?? 0} total) · ` +
          `${t.open_escalations ?? 0} open escalation(s)` +
          (t.top_gaps ? `<br/>gaps: ${escapeHtml(t.top_gaps)}` : "") +
          `</li>`,
      )
      .join("")}</ul>` +
    `<p>${escapeHtml(accountLine.replace(/\*/g, ""))}</p>` +
    `<p>${escapeHtml(budgetText.replace(/\*/g, ""))}</p>` +
    (env.CONSOLE_BASE_URL
      ? `<p><a href="${env.CONSOLE_BASE_URL}">Open the console</a></p>`
      : "");

  return { slackText, emailSubject, emailBody };
}

if (typeof $input !== "undefined") {
  const tenants = $("Fetch Digest Stats")
    .all()
    .map((i) => i.json)
    .filter((t) => t.tenant_name);
  const accountItem = $("Fetch Account Stats").first();
  const account = (accountItem && accountItem.json) || {};
  const budgetItem = $input.first();
  const raw = (budgetItem && budgetItem.json) || {};
  const result = Array.isArray(raw.result) ? raw.result : [null, null];
  const budget = {
    chatUsed: result[0] === null || result[0] === undefined ? null : parseInt(result[0], 10) || 0,
    embedUsed: result[1] === null || result[1] === undefined ? null : parseInt(result[1], 10) || 0,
  };
  return [
    {
      json: formatDigest(tenants, account, budget, {
        DEMO_CHAT_DAILY: $env.DEMO_CHAT_DAILY,
        DEMO_EMBED_DAILY: $env.DEMO_EMBED_DAILY,
        CONSOLE_BASE_URL: $env.CONSOLE_BASE_URL,
      }, new Date()),
    },
  ];
}

module.exports = { formatDigest };
