const STEPS = ['Image received', 'Field tiled', 'Tiles diagnosed', 'Analysis assembled']

function stepState(index, phase) {
  if (phase === 'idle' || phase === 'error') return 'pending'
  if (index === 0) return 'done'
  if (index === 1) return 'active'
  return 'pending'
}

export default function ActivityPanel({ phase, runId }) {
  return (
    <aside className="rounded-2xl border border-field-border bg-field-panel p-5 shadow-2xl shadow-black/20">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">
        Agent activity
      </p>
      <div className="mt-4 rounded-xl border border-field-border bg-black/15 p-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-white">
            {phase === 'idle' && 'Ready for a new scan'}
            {phase === 'uploading' && 'Sending field image'}
            {phase === 'scanning' && 'Scanning field…'}
            {phase === 'complete' && 'Field map complete'}
            {phase === 'error' && 'Scan interrupted'}
          </span>
          {(phase === 'uploading' || phase === 'scanning') && (
            <span className="size-2 animate-pulse rounded-full bg-emerald-400" />
          )}
        </div>
        {runId && <p className="mt-2 break-all font-mono text-[11px] text-slate-500">Run {runId}</p>}
      </div>

      <ol className="mt-6 space-y-1">
        {STEPS.map((step, index) => {
          const state = stepState(index, phase)
          return (
            <li className="flex gap-3" key={step}>
              <div className="flex flex-col items-center">
                <span className={`mt-0.5 grid size-6 place-items-center rounded-full border text-xs ${
                  state === 'done'
                    ? 'border-emerald-400 bg-emerald-400 text-emerald-950'
                    : state === 'active'
                      ? 'border-emerald-300 text-emerald-300'
                      : 'border-slate-700 text-slate-600'
                }`}>
                  {state === 'done' ? '✓' : index + 1}
                </span>
                {index < STEPS.length - 1 && <span className="h-8 w-px bg-field-border" />}
              </div>
              <span className={`pt-1 text-sm ${state === 'pending' ? 'text-slate-600' : 'text-slate-200'}`}>
                {step}
              </span>
            </li>
          )
        })}
      </ol>

      <p className="mt-5 border-t border-field-border pt-4 text-xs leading-5 text-slate-500">
        Detailed agent events will appear here as the analysis progresses.
      </p>
    </aside>
  )
}
