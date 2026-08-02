import { useMemo, useState } from 'react'
import BlockedPlan from './BlockedPlan.jsx'
import LoadingSkeleton, { SkeletonBlock } from './LoadingSkeleton.jsx'
import MarkdownPlan from './MarkdownPlan.jsx'
import SourceDrawer from './SourceDrawer.jsx'

const SOURCE_MARKER = /\[(doc_\d+#p\d+)\]/g

export default function PlanPanel({ diagnosisSummary, loading, phase, plan, verification }) {
  const [activeSource, setActiveSource] = useState(null)
  const sourceNumbers = useMemo(
    () => new Map((verification?.sources ?? []).map((source, index) => [source.id, { number: index + 1, source }])),
    [verification],
  )
  const claimIds = [...(plan?.matchAll(SOURCE_MARKER) ?? [])].map((match) => match[1])
  const groundedClaims = claimIds.filter((id) => sourceNumbers.has(id)).length
  const allGrounded = claimIds.length > 0 && groundedClaims === claimIds.length
  const activeNumber = activeSource ? sourceNumbers.get(activeSource.id)?.number : null
  const revised = verification?.status === 'PASS' && verification.unsupported_claims.length > 0

  if (verification?.status === 'BLOCK') {
    return <BlockedPlan diagnosisSummary={diagnosisSummary} verification={verification} />
  }

  return (
    <section className="order-4 rounded-2xl border border-field-border bg-field-panel p-4 shadow-2xl shadow-black/20 sm:p-6 lg:order-none lg:col-span-2" id="treatment-plan">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Verified treatment plan</p>
          <h2 className="mt-1 text-xl font-semibold text-white">Grounded field guidance</h2>
        </div>
        {plan && verification?.status === 'PASS' && (
          <span className={`rounded-full border px-3 py-1.5 text-xs font-bold ${allGrounded ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : 'border-amber-400/30 bg-amber-400/10 text-amber-300'}`}>
            Grounded: {groundedClaims}/{claimIds.length} claims
          </span>
        )}
        {verification?.status === 'REWRITE' && (
          <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-xs font-bold text-amber-300">Revision requested</span>
        )}
      </div>

      {verification?.status === 'REWRITE' ? (
        <div className="result-enter mt-5 rounded-xl border border-amber-400/20 bg-amber-400/5 p-5">
          <p className="font-semibold text-amber-200">Plan returned for accuracy revision</p>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            The verifier found claims that need stronger support. Treatment advice remains hidden while the agronomist revises it.
          </p>
        </div>
      ) : plan && verification ? (
        <>
          {revised && (
            <div className="mt-5 flex gap-3 rounded-xl border border-amber-400/20 bg-amber-400/5 px-4 py-3" role="status">
              <span aria-hidden="true" className="text-amber-300">↻</span>
              <div>
                <p className="text-sm font-semibold text-amber-200">Plan revised for accuracy</p>
                <p className="mt-0.5 text-xs leading-5 text-slate-400">The verifier removed unsupported advice before approving this plan.</p>
              </div>
            </div>
          )}
          <div className="result-enter mt-4 rounded-xl border border-field-border bg-black/10 p-5 sm:p-6">
            <MarkdownPlan markdown={plan} onSource={setActiveSource} sourceNumbers={sourceNumbers} />
          </div>
        </>
      ) : loading ? (
        <LoadingSkeleton
          className="mt-4 min-h-44 rounded-xl border border-field-border bg-black/10 p-5 sm:p-6"
          label="Verifying treatment plan"
        >
          <div className="flex items-center justify-between gap-5">
            <SkeletonBlock className="h-4 w-44" />
            <SkeletonBlock className="h-7 w-24 rounded-full" />
          </div>
          <SkeletonBlock className="mt-7 h-3 w-full" />
          <SkeletonBlock className="mt-3 h-3 w-11/12" />
          <SkeletonBlock className="mt-3 h-3 w-4/5" />
          <SkeletonBlock className="mt-6 h-3 w-2/3" />
        </LoadingSkeleton>
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
