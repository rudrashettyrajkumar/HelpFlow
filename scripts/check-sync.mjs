#!/usr/bin/env node
// Drift-proofing (spec E10 Req 2; LeadFlow discipline). The repo is the source
// of truth for every n8n Code node (snippets/*.js) and any other file a node
// embeds (prompts, SQL — anything marked). This proves the exported workflow
// JSON still matches those files, byte for byte:
//
//   1. Every Code node's jsCode MUST open with `// source: <repo path>` and
//      match that file exactly (modulo trailing newline / CRLF — drvfs).
//   2. Any OTHER string parameter whose first line is a source marker
//      (`// source:`, `-- source:`, `# source:` — covers prompts/SQL if a
//      node ever embeds one) is checked the same way.
//   3. A marker pointing at a file that doesn't exist is a failure.
//   4. A snippets/*.js no workflow references is a WARNING (E11's snippets
//      may land before their workflow) — it never fails the run.
//
// Exit 0 = everything in sync; exit 1 = drift (the pasted-back n8n editor copy
// diverged from the repo — re-export with export-workflows.mjs or fix the
// snippet, then re-import).
//
// Usage: node scripts/check-sync.mjs

import { readdirSync, readFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WF_DIR = join(ROOT, "workflows");
const SNIPPETS_DIR = join(ROOT, "snippets");

const MARKER = /^(?:\/\/|--|#)\s*source:\s*(\S+)\s*$/;

// drvfs/CRLF + trailing-newline tolerant comparison; everything else is exact.
const normalize = (s) => String(s).replace(/\r\n/g, "\n").replace(/\n+$/, "");

let failures = 0;
let checks = 0;
const referenced = new Set();

function* stringLeaves(value, path) {
  if (typeof value === "string") {
    yield [path, value];
  } else if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) yield* stringLeaves(value[i], `${path}[${i}]`);
  } else if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) yield* stringLeaves(v, `${path}.${k}`);
  }
}

function checkMarker(wfName, nodeName, where, text) {
  const normalized = normalize(text);
  const lines = normalized.split("\n");
  const m = lines[0].match(MARKER);
  if (!m) return false;

  checks++;
  const relPath = m[1];
  referenced.add(relPath);
  const file = join(ROOT, relPath);
  if (!existsSync(file)) {
    failures++;
    console.error(`DRIFT  ${wfName} · ${nodeName} · ${where}: marker points at missing file ${relPath}`);
    return true;
  }
  // The marker line itself (line 1) is an artifact of embedding — it names
  // the source file but isn't part of that file's own content. Compare the
  // node's body from line 2 onward against the file verbatim.
  const embeddedBody = lines.slice(1).join("\n");
  if (normalize(readFileSync(file, "utf8")) !== embeddedBody) {
    failures++;
    console.error(`DRIFT  ${wfName} · ${nodeName} · ${where}: does not match ${relPath}`);
  } else {
    console.log(`ok     ${wfName} · ${nodeName} → ${relPath}`);
  }
  return true;
}

const wfFiles = readdirSync(WF_DIR).filter((f) => f.endsWith(".json")).sort();
if (wfFiles.length === 0) {
  console.error("no workflow JSON found in workflows/");
  process.exit(1);
}

for (const f of wfFiles) {
  const wf = JSON.parse(readFileSync(join(WF_DIR, f), "utf8"));
  for (const node of wf.nodes ?? []) {
    const isCode = node.type === "n8n-nodes-base.code";
    let sawMarker = false;
    for (const [where, text] of stringLeaves(node.parameters ?? {}, "parameters")) {
      if (checkMarker(wf.name ?? f, node.name, where, text)) sawMarker = true;
    }
    if (isCode && !sawMarker) {
      failures++;
      console.error(`DRIFT  ${wf.name ?? f} · ${node.name}: Code node has no "// source: snippets/<file>.js" marker`);
    }
  }
}

for (const s of readdirSync(SNIPPETS_DIR).filter((f) => f.endsWith(".js")).sort()) {
  if (!referenced.has(`snippets/${s}`)) {
    console.warn(`warn   snippets/${s} is not referenced by any workflow (future epic?)`);
  }
}

console.log(`\n${checks} marker(s) checked across ${wfFiles.length} workflow file(s); ${failures} drift(s).`);
process.exit(failures === 0 ? 0 : 1);
