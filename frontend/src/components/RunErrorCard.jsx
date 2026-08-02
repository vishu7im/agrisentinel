/**
 * A failed run, with a way out of it.
 *
 * This used to be one flat red sentence with no run id and no next step. The second button is
 * the one that matters on stage: a single click from a broken live run to a recorded replay
 * that always works, without touching a terminal or reloading the page.
 */
export default function RunErrorCard({ demoCases, message, onRetry, onStartDemo, runId }) {
  return (
    <div
      className="mt-4 rounded-xl border border-red-400/25 bg-red-400/[0.07] px-4 py-4"
      role="alert"
    >
      <p className="text-eyebrow font-semibold uppercase text-red-300/80">Scan stopped</p>
      <p className="mt-1.5 text-sm leading-relaxed text-red-100">{message}</p>
      {runId && <p className="mt-1 font-mono text-[11px] text-red-300/60">run {runId}</p>}

      <div className="mt-4 flex flex-wrap gap-2">
        {onRetry && (
          <button
            className="min-h-11 rounded-lg border border-red-400/30 bg-red-400/10 px-4 text-sm font-medium text-red-100 transition hover:border-red-400/60"
            onClick={onRetry}
            type="button"
          >
            Retry this scan
          </button>
        )}
        {demoCases?.length > 0 && (
          <button
            className="min-h-11 rounded-lg border border-field-border bg-white/5 px-4 text-sm font-medium text-slate-200 transition hover:border-emerald-400/50 hover:text-white"
            onClick={() => onStartDemo(demoCases[0].id)}
            type="button"
          >
            Play a recorded scan instead
          </button>
        )}
      </div>
    </div>
  )
}
