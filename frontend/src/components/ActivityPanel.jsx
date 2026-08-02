import EventLog from './EventLog.jsx'

/**
 * The live event log.
 *
 * The vertical agent list that used to sit above this moved to PipelineSpine, across the top of
 * the page — it is the architecture, and the architecture had been living in a 22rem side rail.
 * Removing it from here also removes the eleven grey "pending" rows that were the first thing
 * anyone saw on an untouched page.
 */

export default function ActivityPanel({ events, phase, runId, startedAt, streamStatus, tileCount }) {
  return (
    <aside className="rounded-2xl border border-field-border bg-field-panel p-4 shadow-2xl shadow-black/20 sm:p-5" id="agent-activity">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-eyebrow font-semibold uppercase text-emerald-300/70">Agent activity</p>
          <p className="mt-1 text-[11px] text-slate-500">Eleven specialists, one verified decision</p>
        </div>
        {(phase === 'uploading' || phase === 'scanning') && (
          <span className="mt-1 size-2 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_10px_#4ade80]" />
        )}
      </div>

      <div className="mt-3 rounded-xl border border-field-border bg-black/15 px-3 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-white">
            {phase === 'idle' && 'Ready for a new scan'}
            {phase === 'uploading' && 'Sending field image'}
            {phase === 'scanning' && 'Scanning field…'}
            {phase === 'complete' && 'Field map complete'}
            {phase === 'error' && 'Scan interrupted'}
          </span>
        </div>
        {runId && <p className="mt-1 truncate font-mono text-[10px] text-slate-600">Run {runId}</p>}
      </div>
      <EventLog events={events} phase={phase} startedAt={startedAt} streamStatus={streamStatus} tileCount={tileCount} />
    </aside>
  )
}
