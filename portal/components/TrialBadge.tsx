const MAX_TRIALS = 2

export function TrialBadge({ trialsUsed }: { trialsUsed: number }) {
  const atCap = trialsUsed >= MAX_TRIALS
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
        atCap ? 'bg-destructive/15 text-destructive' : 'bg-brand/15 text-brand'
      }`}
    >
      Trial {Math.min(trialsUsed, MAX_TRIALS)} of {MAX_TRIALS}
    </span>
  )
}
