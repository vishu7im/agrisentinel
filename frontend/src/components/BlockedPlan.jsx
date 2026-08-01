import { useState } from 'react'

export default function BlockedPlan({ diagnosisSummary, verification }) {
  const [copyState, setCopyState] = useState('Copy summary')
  const unsupportedClaims = verification.unsupported_claims ?? []

  async function copySummary() {
    if (!diagnosisSummary || !navigator.clipboard) {
      setCopyState('Select text to copy')
      return
    }
    try {
      await navigator.clipboard.writeText(diagnosisSummary)
      setCopyState('Copied')
    } catch {
      setCopyState('Select text to copy')
    }
  }

  return (
    <section className="result-enter rounded-2xl border border-amber-400/30 bg-field-panel p-5 shadow-2xl shadow-black/20 lg:col-span-2 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-300/80">Verifier decision</p>
          <h2 className="mt-2 text-2xl font-semibold leading-tight text-white">
            Treatment advice withheld — insufficient verified sources
          </h2>
          <p className="mt-3 leading-7 text-slate-300">{verification.block_reason}</p>
        </div>
        <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-xs font-bold uppercase tracking-[0.16em] text-amber-300">
          Advice withheld
        </span>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-amber-400/20 bg-amber-400/5 p-5">
          <h3 className="font-semibold text-amber-200">Claims that could not be verified</h3>
          <ul className="mt-3 space-y-3 text-sm leading-6 text-slate-300">
            {unsupportedClaims.map((claim) => (
              <li className="flex gap-3" key={claim}>
                <span aria-hidden="true" className="mt-0.5 text-amber-400">⊘</span>
                <span>{claim}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 border-t border-amber-400/15 pt-4 text-sm font-medium text-amber-100">
            AgriSentinel will not recommend an unverified chemical treatment.
          </p>
        </div>

        <div className="rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300/70">Next safe step</p>
          <h3 className="mt-2 text-xl font-semibold text-white">Consult a local agriculture extension officer</h3>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            Share the field result below so an officer can confirm a locally approved treatment and label rate.
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-field-border bg-black/20 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Field result to share</p>
          <button
            className="rounded-lg border border-field-border px-3 py-2 text-xs font-semibold text-slate-300 transition hover:border-emerald-400/40 hover:text-white"
            onClick={copySummary}
            type="button"
          >
            {copyState}
          </button>
        </div>
        <p className="mt-4 max-w-5xl select-text text-base leading-7 text-slate-200">
          {diagnosisSummary || 'Diagnosis details remain available in the field scan and severity panel above.'}
        </p>
      </div>
    </section>
  )
}
