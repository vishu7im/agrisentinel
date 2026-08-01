import FarmerBrief from './FarmerBrief.jsx'
import LoadingSkeleton, { SkeletonBlock } from './LoadingSkeleton.jsx'
import ScheduleTimeline from './ScheduleTimeline.jsx'

export default function ActionPanel({
  blocked,
  costEstimate,
  phase,
  report,
  reportLoading,
  rescanDate,
  schedule,
  scheduleLoading,
}) {
  const pendingMessage = blocked
    ? 'No treatment schedule is shown when advice is withheld.'
    : phase === 'complete'
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
        ) : scheduleLoading ? (
          <LoadingSkeleton
            className="mt-5 min-h-40 rounded-xl border border-field-border bg-black/10 p-5"
            label="Preparing action schedule"
          >
            <div className="flex items-center justify-between gap-5">
              {[0, 1, 2, 3].map((step) => (
                <div className="flex flex-1 flex-col items-center" key={step}>
                  <SkeletonBlock className="h-3 w-12" />
                  <SkeletonBlock className="mt-4 size-9 rounded-full" />
                  <SkeletonBlock className="mt-4 h-2.5 w-full max-w-24" />
                </div>
              ))}
            </div>
            <SkeletonBlock className="mt-6 h-12 w-full" />
          </LoadingSkeleton>
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

      <FarmerBrief loading={reportLoading} phase={phase} report={report} />
    </section>
  )
}
