// Is-now-within-BUSINESS_HOURS check for WF-H (spec E6 Req 3). Reads only
// `$env.BUSINESS_HOURS` + `$env.BUSINESS_TZ` — no per-tenant hours exist in the
// schema (confirmed: grep of sql/ + backend/ for business_hours is empty), so
// this is a single global window, not per-tenant.
//
// BUSINESS_HOURS format: "HH:MM-HH:MM" (every day) or "DDD-DDD HH:MM-HH:MM"
// (day range, e.g. "MON-FRI 09:00-18:00"). Wraps past midnight if start > end.
// An unparseable value fails OPEN (never silently swallows a real escalation —
// off-hours only suppresses the on-call ping, it never drops the alert).
function isWithinBusinessHours(now, businessHours, businessTz) {
  const spec = String(businessHours || "").trim();
  const match = spec.match(/^(?:([A-Za-z]{3})-([A-Za-z]{3})\s+)?(\d{2}):(\d{2})-(\d{2}):(\d{2})$/);
  if (!match) return true;

  const [, dayFrom, dayTo, h1, m1, h2, m2] = match;
  const tz = businessTz || "UTC";

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(now);
  const get = (type) => parts.find((p) => p.type === type)?.value || "";

  const DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  const weekday = get("weekday").toUpperCase().slice(0, 3);
  const hour = parseInt(get("hour"), 10) % 24; // Intl can return "24" for midnight
  const minute = parseInt(get("minute"), 10);
  const minutesNow = hour * 60 + minute;
  const minutesStart = parseInt(h1, 10) * 60 + parseInt(m1, 10);
  const minutesEnd = parseInt(h2, 10) * 60 + parseInt(m2, 10);

  let inDayRange = true;
  if (dayFrom && dayTo) {
    const from = DAYS.indexOf(dayFrom.toUpperCase());
    const to = DAYS.indexOf(dayTo.toUpperCase());
    const cur = DAYS.indexOf(weekday);
    if (from === -1 || to === -1 || cur === -1) return true; // fail open
    inDayRange = from <= to ? cur >= from && cur <= to : cur >= from || cur <= to;
  }

  const inTimeRange =
    minutesStart <= minutesEnd
      ? minutesNow >= minutesStart && minutesNow < minutesEnd
      : minutesNow >= minutesStart || minutesNow < minutesEnd;

  return inDayRange && inTimeRange;
}

function run(items, env) {
  const inBusinessHours = isWithinBusinessHours(new Date(), env.BUSINESS_HOURS, env.BUSINESS_TZ);
  return items.map((item) => ({ json: { ...item.json, inBusinessHours } }));
}

if (typeof $input !== "undefined") {
  return run($input.all(), { BUSINESS_HOURS: $env.BUSINESS_HOURS, BUSINESS_TZ: $env.BUSINESS_TZ });
}

module.exports = { isWithinBusinessHours, run };
