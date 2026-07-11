// Hourly ops-sweep classifier for WF-O (spec E10 Req 1). Pure decision logic:
// the two Postgres fetch nodes upstream supply candidates (notified-unassigned
// escalations + needs_human conversations), the Business Hours node has already
// stamped `inBusinessHours` on every item; this decides what gets acted on and
// never touches the DB itself — the guarded marker INSERT / guarded UPDATE
// downstream stay the single writers.
//
// Decisions:
//  * sla_realert — escalation still status='notified' and unassigned after
//    $env.SLA_MINUTES. Emitted on EVERY sweep while stale; the `sla_realert`
//    events marker (006 partial unique index + ON CONFLICT DO NOTHING) is what
//    makes the Slack re-alert fire exactly ONCE per escalation.
//  * abandon — needs_human conversation with NO captured customer_email
//    (nobody to follow up with), idle longer than $env.ABANDON_HOURS, and only
//    OFF-hours (during business hours a quiet needs_human is the agents' queue,
//    not the sweep's). WF-O is the ONLY writer of needs_human→abandoned.
//
// Missing/unparseable env FAILS QUIET for that decision (no realert / no
// abandon): a state transition and a page must never fire off a misconfigured
// threshold. Anything unclassifiable — fresh, assigned, in-hours, has-email,
// or the empty `alwaysOutputData` placeholder item — drops out.
function sweep(items, env, now) {
  const nowMs = (now instanceof Date ? now : new Date(now)).getTime();
  const slaMinutes = parseInt(env.SLA_MINUTES, 10);
  const abandonHours = parseInt(env.ABANDON_HOURS, 10);
  const actions = [];

  for (const item of items) {
    const row = item.json || item;

    if (row.escalation_id && row.notified_at) {
      if (!Number.isFinite(slaMinutes) || slaMinutes <= 0) continue;
      const waitedMinutes = Math.floor((nowMs - new Date(row.notified_at).getTime()) / 60000);
      if (waitedMinutes >= slaMinutes) {
        actions.push({
          json: {
            action: "sla_realert",
            escalation_id: row.escalation_id,
            conversation_id: row.conversation_id,
            tenant_name: row.tenant_name || "(unknown tenant)",
            waited_minutes: waitedMinutes,
          },
        });
      }
    } else if (row.conversation_id && row.last_activity_at) {
      if (!Number.isFinite(abandonHours) || abandonHours <= 0) continue;
      if (row.customer_email) continue;
      if (row.inBusinessHours !== false) continue;
      const idleHours = Math.floor((nowMs - new Date(row.last_activity_at).getTime()) / 3600000);
      if (idleHours >= abandonHours) {
        actions.push({
          json: {
            action: "abandon",
            conversation_id: row.conversation_id,
            tenant_name: row.tenant_name || "(unknown tenant)",
            idle_hours: idleHours,
          },
        });
      }
    }
  }

  return actions;
}

if (typeof $input !== "undefined") {
  return sweep(
    $input.all(),
    { SLA_MINUTES: $env.SLA_MINUTES, ABANDON_HOURS: $env.ABANDON_HOURS },
    new Date(),
  );
}

module.exports = { sweep };
