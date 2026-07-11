import type { SourceItem } from '../api/types'

const CITATION_RE = /\[(\d+)\]/g

/** Turns final `[n]` markers into markdown links (`[n](citation:n)`) so
 * react-markdown's `a` renderer can swap them for a `CitationChip` (ported
 * from DocChat's `lib/citations.ts`). Numbers with no matching source are
 * stripped. During streaming, leave `[n]` as plain text — sources only land
 * once the `sources` event arrives, after the last token. */
export function annotateCitations(text: string, sources: SourceItem[]): string {
  const validNs = new Set(sources.map((s) => s.n))
  return text.replace(CITATION_RE, (_match, numStr) => {
    const n = Number(numStr)
    return validNs.has(n) ? `[${n}](citation:${n})` : ''
  })
}
