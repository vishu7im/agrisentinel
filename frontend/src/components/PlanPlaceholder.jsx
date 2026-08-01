export default function PlanPlaceholder({ phase }) {
  return (
    <section className="rounded-2xl border border-field-border bg-field-panel p-5 shadow-2xl shadow-black/20 lg:col-span-2">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">
        Verified treatment plan
      </p>
      <div className="mt-4 flex min-h-28 items-center justify-center rounded-xl border border-dashed border-field-border bg-black/10 px-6 text-center">
        <div>
          <span className="mx-auto grid size-9 place-items-center rounded-full bg-slate-800 text-slate-400">⌁</span>
          <p className="mt-3 text-sm font-medium text-slate-300">
            {phase === 'complete' ? 'Field diagnosis complete' : 'Plan pending field diagnosis'}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Grounded treatment advice will appear here after agronomy verification.
          </p>
        </div>
      </div>
    </section>
  )
}
