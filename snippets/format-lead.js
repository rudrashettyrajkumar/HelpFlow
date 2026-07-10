// premium_leads row -> Slack text + Gmail body + one-tap quick-reply links
// (spec E6 Req 8). This workflow is literally how the HelpFlow demo hands Raj
// freelance leads, so the message is written to be worth screenshotting for
// the case study: name, company, message, buying-intent signal (workspaces
// used), a mailto: to the lead's own address, and a wa.me link.
//
// wa.me deliberately points at $env.RAJ_WHATSAPP_URL, not a lead phone number
// — premium_leads captures no phone field (schema: id/user_id/name/email/
// company/message/source/created_at), so there's nothing lead-specific to
// build a wa.me link from. This matches spec Req 8's literal wording
// ("a wa.me link ($env.RAJ_WHATSAPP_URL)") — a one-tap jump into Raj's own
// WhatsApp, not a deep link to the lead.
function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function formatLead(lead, env) {
  const name = lead.name || "(no name)";
  const email = lead.email || "";
  const company = lead.company ? lead.company : "(no company given)";
  const message = lead.message || "";
  const source = lead.source || "unknown";
  const workspacesUsed = Number.isFinite(lead.workspaces_used) ? lead.workspaces_used : 0;
  const mailtoLink = email
    ? `mailto:${email}?subject=${encodeURIComponent("Re: your HelpFlow message")}`
    : "";
  const waLink = env.RAJ_WHATSAPP_URL || "";

  const intentLine =
    workspacesUsed > 0
      ? `Used ${workspacesUsed} trial workspace${workspacesUsed === 1 ? "" : "s"} before hitting the gate — real buying intent.`
      : `Came in via the ${source} form (no trial workspace on file).`;

  const slackText =
    `:moneybag: *New premium lead* (${source})\n` +
    `*${name}*${company ? ` — ${company}` : ""}\n` +
    `${intentLine}\n` +
    `> ${message}\n` +
    (mailtoLink ? `<${mailtoLink}|Reply by email>` : "no email") +
    (waLink ? `  •  <${waLink}|Open WhatsApp>` : "");

  const emailSubject = `[HelpFlow] Premium lead: ${name}${lead.company ? ` (${lead.company})` : ""}`;
  const emailBody =
    `<p><strong>${escapeHtml(name)}</strong>${lead.company ? ` — ${escapeHtml(lead.company)}` : ""}</p>` +
    `<p>${escapeHtml(intentLine)}</p>` +
    `<p style="white-space:pre-wrap">${escapeHtml(message)}</p>` +
    `<p>` +
    (mailtoLink ? `<a href="${mailtoLink}">Reply by email</a>` : "no email on file") +
    (waLink ? ` &nbsp;|&nbsp; <a href="${waLink}">Open WhatsApp</a>` : "") +
    `</p>`;

  return { slackText, emailSubject, emailBody, mailtoLink, waLink };
}

function run(items, env) {
  return items.map((item) => ({ json: { ...item.json, ...formatLead(item.json, env) } }));
}

if (typeof $input !== "undefined") {
  return run($input.all(), { RAJ_WHATSAPP_URL: $env.RAJ_WHATSAPP_URL });
}

module.exports = { formatLead, run };
