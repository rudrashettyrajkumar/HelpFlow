'use client'

import { useState } from 'react'
import { Check, Wand2 } from 'lucide-react'
import { Glass } from '@/components/Glass'
import { ModelStudioBody } from '@/components/ModelStudioBody'
import { useModelStudio } from '@/lib/useModelStudio'

export default function ModelStudioPage() {
  const studio = useModelStudio()
  const [saved, setSaved] = useState(false)

  const handleSave = () => {
    studio.save()
    setSaved(true)
    setTimeout(() => setSaved(false), 2500)
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex items-center gap-3">
        <span className="flex size-11 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
          <Wand2 className="size-5" aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Model Studio</h1>
          <p className="text-sm text-foreground-muted">
            Bring your own key — chat on your quota, with any model you like.
          </p>
        </div>
      </div>

      <Glass strong className="rounded-3xl p-5 sm:p-6">
        <ModelStudioBody {...studio} />

        <div className="mt-6 flex items-center justify-between gap-3 border-t border-border pt-5">
          <p className="hidden text-[11px] text-foreground-muted sm:block">
            Applies to your next question in every workspace&apos;s widget preview.
          </p>
          <button
            type="button"
            onClick={handleSave}
            disabled={studio.draft.mode === 'byok' && !studio.canSaveByok}
            className="ml-auto flex min-h-[44px] cursor-pointer items-center gap-2 rounded-xl bg-brand-gradient px-5 text-sm font-bold text-white shadow-glow transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            {saved ? (
              <>
                <Check className="size-4" aria-hidden="true" /> Saved
              </>
            ) : studio.draft.mode === 'demo' ? (
              'Use demo mode'
            ) : (
              `Save & use ${studio.draft.modelName || 'model'}`
            )}
          </button>
        </div>
      </Glass>
    </div>
  )
}
