import { Check } from 'lucide-react'

const STEPS = ['Name & URL', 'Learning', 'Pick a brain', 'Try it']

export function WizardSteps({ current }: { current: number }) {
  return (
    <ol className="mb-8 flex items-center gap-1.5 sm:gap-3">
      {STEPS.map((label, i) => {
        const step = i + 1
        const done = step < current
        const active = step === current
        return (
          <li key={label} className="flex flex-1 items-center gap-1.5 sm:gap-3">
            <div className="flex items-center gap-2">
              <span
                className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                  done
                    ? 'bg-brand text-white'
                    : active
                      ? 'bg-brand-gradient text-white shadow-glow'
                      : 'bg-surface-muted text-foreground-muted'
                }`}
              >
                {done ? <Check className="size-3.5" aria-hidden="true" /> : step}
              </span>
              <span
                className={`hidden text-xs font-semibold sm:block ${
                  active ? 'text-foreground' : 'text-foreground-muted'
                }`}
              >
                {label}
              </span>
            </div>
            {step < STEPS.length && <div className="h-px flex-1 bg-border" aria-hidden="true" />}
          </li>
        )
      })}
    </ol>
  )
}
