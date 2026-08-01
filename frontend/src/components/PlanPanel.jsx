import { useMemo, useState } from 'react'
import MarkdownPlan from './MarkdownPlan.jsx'
import SourceDrawer from './SourceDrawer.jsx'

const SOURCE_MARKER = /\[(doc_\d+#p\d+)\]/g

export default function PlanPanel({ phase, plan, verification }) {
  const [activeSource, setActiveSource] = useState(null)
  const sourceNumbers = useMemo(
    () => new Map((verification?.sources ?? []).map((source, index) => [source.id, { number: index + 1, source }])),
    [verification],
  )
  const claimIds = [...(plan?.matchAll(SOURCE_MARKER) ?? [])].map((match) => match[1])
  const groundedClaims = claimIds.filter((id) => sourceNumbers.has(id)).length
  const allGrounded = claimIds.length > 0 && groundedClaims === claimIds.length
  const activeNumber = activeSource ? sourceNumbers.get(activeSource.id)?.number : null

  return (
    <section className="rounded-2xl border border-field-border bg-field-panel p-5 shadow-2xl shadow-black/20 lg:col-span-2 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Verified treatment plan</p>
          <h2 className="mt-1 text-xl font-semibold text-white">Grounded field guidance</h2>
        </div>
        {plan && verification && (
          <span className={`rounded-full border px-3 py-1.5 text-xs font-bold ${allGrounded ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : 'border-amber-400/30 bg-amber-400/10 text-amber-300'}`}>
            Grounded: {groundedClaims}/{claimIds.length} claims
          </span>
        )}
      </div>

      {plan && verification ? (
        <div className="mt-5 rounded-xl border border-field-border bg-black/10 p-5 sm:p-6">
          <MarkdownPlan markdown={plan} onSource={setActiveSource} sourceNumbers={sourceNumbers} />
        </div>
      ) : (
        <div className="mt-4 flex min-h-32 items-center justify-center rounded-xl border border-dashed border-field-border bg-black/10 px-6 text-center">
          <div>
            <span className="mx-auto grid size-9 place-items-center rounded-full bg-slate-800 text-slate-400">⌁</span>
            <p className="mt-3 text-sm font-medium text-slate-300">
              {phase === 'complete' ? 'No verified plan was returned' : 'Plan pending field diagnosis'}
            </p>
            <p className="mt-1 text-xs text-slate-500">Grounded treatment advice appears after verification.</p>
          </div>
        </div>
      )}

      {activeSource && activeNumber && (
        <SourceDrawer onClose={() => setActiveSource(null)} source={activeSource} sourceNumber={activeNumber} />
      )}
    </section>
  )
}
