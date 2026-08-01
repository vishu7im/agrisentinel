import FarmerBrief from './FarmerBrief.jsx'
import ScheduleTimeline from './ScheduleTimeline.jsx'

export default function ActionPanel({ costEstimate, phase, report, rescanDate, schedule }) {
  const pendingMessage = phase === 'complete'
    ? 'No action schedule was returned for this run.'
    : 'The dated action plan appears after verification.'

  return (
    <section className="grid gap-5 lg:col-span-2 xl:grid-cols-[minmax(0,1.45fr)_minmax(20rem,0.75fr)]">
      <div className="rounded-2xl border border-field-border bg-field-panel p-5 shadow-2xl shadow-black/20 sm:p-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Action schedule</p>
          <h2 className="mt-1 text-xl font-semibold text-white">What to do next</h2>
        </div>

        {schedule?.length ? (
          <ScheduleTimeline
            costEstimate={costEstimate}
            rescanDate={rescanDate}
            schedule={schedule}
          />
        ) : (
          <div className="mt-5 flex min-h-40 items-center justify-center rounded-xl border border-dashed border-field-border bg-black/10 px-6 text-center">
            <div>
              <span className="mx-auto grid size-9 place-items-center rounded-full bg-slate-800 text-slate-400">◷</span>
              <p className="mt-3 text-sm font-medium text-slate-300">{pendingMessage}</p>
              <p className="mt-1 text-xs text-slate-500">Safety checks finish before any treatment dates are shown.</p>
            </div>
          </div>
        )}
      </div>

      <FarmerBrief phase={phase} report={report} />
    </section>
  )
}
