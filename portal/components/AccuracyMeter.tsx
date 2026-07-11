const LABEL = ['', 'Basic', 'Good', 'Great', 'Excellent', 'Frontier']

/** 5-segment accuracy meter — color + width + text label, never color alone
 * (ARCHITECTURE §4.2: "editorial tiers, not rotting benchmark numbers"). */
export function AccuracyMeter({ tier }: { tier: number }) {
  return (
    <div className="flex items-center gap-2" title={`Accuracy: ${LABEL[tier]} (${tier}/5)`}>
      <div className="flex gap-0.5" role="img" aria-label={`Accuracy ${tier} out of 5`}>
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className={`h-1.5 w-3 rounded-full ${
              i <= tier ? 'bg-gradient-to-r from-brand to-brand-2' : 'bg-foreground-muted/20'
            }`}
          />
        ))}
      </div>
      <span className="text-[11px] font-semibold text-foreground-muted">{LABEL[tier]}</span>
    </div>
  )
}
