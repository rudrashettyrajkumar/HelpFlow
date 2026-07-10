/** Ambient blob background behind hero/auth sections — the "gradient-mesh
 * hero" ARCHITECTURE §8 calls for. Pure decoration: `aria-hidden`, and every
 * animated blob respects `prefers-reduced-motion` via the global CSS rule. */
export function GradientMesh() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div
        className="absolute -left-24 -top-24 size-[28rem] animate-float rounded-full opacity-40 blur-3xl"
        style={{ background: 'rgb(var(--blob-1))' }}
      />
      <div
        className="absolute -right-32 top-10 size-[24rem] animate-float-slow rounded-full opacity-30 blur-3xl"
        style={{ background: 'rgb(var(--blob-2))' }}
      />
      <div
        className="absolute bottom-0 left-1/3 size-[22rem] animate-float rounded-full opacity-25 blur-3xl"
        style={{ background: 'rgb(var(--blob-3))' }}
      />
    </div>
  )
}
