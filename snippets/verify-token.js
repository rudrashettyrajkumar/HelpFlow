// Header-token check, shared by every webhook trigger (WF-H, WF-P, and WF-W in
// E11). Deliberately generic: it never names a specific header or env var
// itself (that would make it a literal-per-workflow copy, breaking the
// source-of-truth byte-match) — each workflow's own Set node upstream supplies
// `authHeaderName` + `authExpectedValue`, this just compares them against the
// inbound webhook headers.
function verifyToken(items) {
  return items.map((item) => {
    const headers = item.json.headers || {};
    const headerName = String(item.json.authHeaderName || "").toLowerCase();
    const expected = item.json.authExpectedValue;
    const received = headers[headerName];
    const valid = Boolean(expected) && received === expected;
    return { json: { ...item.json, tokenValid: valid } };
  });
}

if (typeof $input !== "undefined") {
  return verifyToken($input.all());
}

module.exports = { verifyToken };
