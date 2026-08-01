export default function DemoControls({ activeCaseId, cases, onSelect }) {
  return (
    <section className="mx-auto mt-5 max-w-[1600px] px-5 sm:px-8" aria-label="Offline demo controls">
      <div className="flex flex-col gap-3 rounded-xl border border-amber-400/25 bg-amber-400/[0.06] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-amber-300">Offline demo mode</p>
          <p className="mt-1 text-xs text-slate-400">Backend disabled · press 1, 2, or 3 to replay a case</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {cases.map((demoCase) => {
            const active = demoCase.id === activeCaseId
            return (
              <button
                aria-pressed={active}
                className={`rounded-lg border px-3 py-2 text-left text-xs transition ${
                  active
                    ? 'border-amber-300/60 bg-amber-300/15 text-white'
                    : 'border-field-border bg-black/15 text-slate-300 hover:border-amber-300/30 hover:text-white'
                }`}
                key={demoCase.id}
                onClick={() => onSelect(demoCase.id)}
                type="button"
              >
                <kbd className="mr-2 rounded border border-white/15 px-1.5 py-0.5 font-mono text-[10px] text-amber-200">
                  {demoCase.shortcut}
                </kbd>
                {demoCase.label}
              </button>
            )
          })}
        </div>
      </div>
    </section>
  )
}
