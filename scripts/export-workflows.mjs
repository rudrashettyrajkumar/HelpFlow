#!/usr/bin/env node
// Deterministic n8n workflow exporter (spec E1 Req 7; ported discipline from
// LeadFlow). Pulls every workflow from the n8n REST API, strips instance-
// specific + secret fields, sorts all keys, and writes workflows/<kebab>.json.
// A second run against an unchanged instance produces an EMPTY git diff — that
// determinism is the whole point (it's what `check-sync.mjs` proves in E7).
//
// Usage:
//   N8N_BASE_URL=https://<railway-n8n> N8N_API_KEY=<key> node scripts/export-workflows.mjs
//
// The repo is the source of truth for workflow JSON, Code-node JS (snippets/),
// and prompts; the developer edits here, imports into the n8n editor, then
// re-runs this to re-sync (CLAUDE.md "How building works here").

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.N8N_BASE_URL;
const KEY = process.env.N8N_API_KEY;
if (!BASE || !KEY) {
  console.error("set N8N_BASE_URL and N8N_API_KEY");
  process.exit(1);
}

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT_DIR = join(ROOT, "workflows");

// Instance-specific or secret fields that must never land in the repo. Node
// `credentials` bind to a specific n8n instance's credential ids, so they are
// stripped; the credential NAMES are contracts documented in CLAUDE.md, not
// exported here.
const WORKFLOW_DROP = new Set([
  "id", "versionId", "createdAt", "updatedAt", "active",
  "pinData", "staticData", "meta", "shared", "tags", "triggerCount",
  "homeProject", "scopes", "isArchived",
]);
const NODE_DROP = new Set(["credentials", "webhookId"]);

// Recursively sort object keys so serialization is stable regardless of the
// order the API returns fields in.
function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((k) => [k, sortKeys(value[k])]),
    );
  }
  return value;
}

function cleanWorkflow(wf) {
  const out = {};
  for (const [k, v] of Object.entries(wf)) {
    if (WORKFLOW_DROP.has(k)) continue;
    if (k === "nodes" && Array.isArray(v)) {
      out.nodes = v.map((node) => {
        const n = {};
        for (const [nk, nv] of Object.entries(node)) {
          if (NODE_DROP.has(nk)) continue;
          n[nk] = nv;
        }
        return n;
      });
    } else {
      out[k] = v;
    }
  }
  return sortKeys(out);
}

function kebab(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

async function api(path) {
  const res = await fetch(`${BASE.replace(/\/$/, "")}/api/v1${path}`, {
    headers: { "X-N8N-API-KEY": KEY, accept: "application/json" },
  });
  if (!res.ok) throw new Error(`n8n API ${path} → ${res.status} ${res.statusText}`);
  return res.json();
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  const list = await api("/workflows");
  const workflows = list.data ?? list;
  // Sort workflows by name so console output is stable too.
  workflows.sort((a, b) => a.name.localeCompare(b.name));

  for (const summary of workflows) {
    const full = await api(`/workflows/${summary.id}`);
    const cleaned = cleanWorkflow(full);
    const file = join(OUT_DIR, `${kebab(full.name)}.json`);
    await writeFile(file, JSON.stringify(cleaned, null, 2) + "\n", "utf8");
    console.log(`exported ${full.name} → ${file}`);
  }
  console.log(`done: ${workflows.length} workflow(s)`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
