import { ArrowRight, Bell, Bot, Database, MessageSquareText, Workflow } from 'lucide-react'

const STEPS = [
  { icon: Database, label: 'Your website', detail: 'crawled & chunked' },
  { icon: Bot, label: 'Qdrant + LangGraph', detail: 'grounded, cited answers' },
  { icon: MessageSquareText, label: 'Chat widget', detail: 'streams to your visitor' },
  { icon: Workflow, label: 'n8n', detail: "when the AI doesn't know" },
  { icon: Bell, label: 'Slack / Gmail', detail: 'a human takes over' },
]

/** A small, honest architecture diagram (spec Req 1) — not a stock graphic:
 * this is the actual data path, box-by-box. */
export function ArchitectureDiagram() {
  return (
    <div className="glass flex flex-col items-stretch gap-3 overflow-x-auto rounded-3xl p-6 sm:flex-row sm:items-center sm:justify-between">
      {STEPS.map((step, i) => (
        <div key={step.label} className="flex items-center gap-3 sm:flex-col sm:text-center">
          <div className="flex flex-col items-center gap-2 sm:w-28">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
              <step.icon className="size-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-bold leading-tight">{step.label}</p>
              <p className="mt-0.5 text-[11px] leading-tight text-foreground-muted">{step.detail}</p>
            </div>
          </div>
          {i < STEPS.length - 1 && (
            <ArrowRight
              className="size-4 shrink-0 rotate-90 text-foreground-muted sm:rotate-0"
              aria-hidden="true"
            />
          )}
        </div>
      ))}
    </div>
  )
}
