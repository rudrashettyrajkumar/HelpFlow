/** `#RRGGBB` → `"R G B"` (this repo's CSS-var convention — see index.css) so a
 * tenant's `brand_color` can override `--brand` without touching Tailwind. */
export function hexToRgbTriple(hex: string): string | null {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!match) return null
  const n = parseInt(match[1], 16)
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`
}
