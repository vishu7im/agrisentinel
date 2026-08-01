function formatDelta(value, decimals = 1) {
  const rounded = Math.abs(value).toFixed(decimals)
  if (Math.abs(value) < (decimals ? 0.05 : 0.5)) return 'No change'
  return `${value > 0 ? '+' : '−'}${rounded}`
}

function trendFor(delta) {
  if (delta > 0.05) {
    return {
      badge: 'border-red-400/30 bg-red-400/10 text-red-200',
      label: `Spread increased ${Math.abs(delta).toFixed(1)} points`,
      tone: 'text-red-300',
    }
  }
  if (delta < -0.05) {
    return {
      badge: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
      label: `Spread decreased ${Math.abs(delta).toFixed(1)} points`,
      tone: 'text-emerald-300',
    }
  }
  return {
    badge: 'border-slate-400/20 bg-slate-400/10 text-slate-200',
    label: 'Spread is unchanged',
    tone: 'text-slate-300',
  }
}

function previousLabel(previous) {
  if (previous.age_days) return `${previous.age_days} days earlier`
  if (!previous.recorded_at) return 'Previous scan'

  const date = new Date(previous.recorded_at)
  if (Number.isNaN(date.getTime())) return 'Previous scan'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function MetricDelta({ current, decimals = 1, label, previous, suffix = '' }) {
  const delta = current - previous
  const unchanged = Math.abs(delta) < (decimals ? 0.05 : 0.5)
  const tone = unchanged ? 'text-slate-400' : delta > 0 ? 'text-red-300' : 'text-emerald-300'

  return (
    <article className="rounded-xl border border-field-border bg-black/20 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</p>
      <div className="mt-2 flex items-end justify-between gap-2">
        <p className="text-xl font-bold tabular-nums text-white">{current.toFixed(decimals)}{suffix}</p>
        <p className={`text-xs font-semibold tabular-nums ${tone}`}>{formatDelta(delta, decimals)}{unchanged ? '' : suffix}</p>
      </div>
      <p className="mt-1 text-[11px] text-slate-500">was {previous.toFixed(decimals)}{suffix}</p>
    </article>
  )
}

function SpreadBar({ label, value, variant }) {
  const width = `${Math.min(100, Math.max(0, value))}%`
  const barClass = variant === 'current' ? 'bg-amber-400' : 'bg-slate-500'

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
        <span className="font-medium text-slate-300">{label}</span>
        <span className="font-semibold tabular-nums text-white">{value.toFixed(1)}%</span>
      </div>
      <div
        aria-label={`${label}: ${value.toFixed(1)} percent of field affected`}
        className="h-2.5 overflow-hidden rounded-full bg-slate-800"
        role="img"
      >
        <div className={`h-full rounded-full transition-[width] duration-700 ${barClass}`} style={{ width }} />
      </div>
    </div>
  )
}

export default function SpreadComparison({ blocked, current, currentFileName, phase, previous }) {
  if (!current) return null

  if (blocked) {
    return (
      <section className="mt-5 border-t border-field-border pt-5" aria-labelledby="comparison-heading">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Change over time</p>
        <h3 className="mt-1 text-lg font-semibold text-white" id="comparison-heading">Trend comparison paused</h3>
        <p className="mt-3 rounded-xl border border-amber-400/20 bg-amber-400/10 p-4 text-sm leading-6 text-amber-100">
          The Verifier blocked this result, so it will not be stored or compared as a field-health baseline.
        </p>
      </section>
    )
  }

  if (!previous) {
    return (
      <section className="mt-5 border-t border-field-border pt-5" aria-labelledby="comparison-heading">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Change over time</p>
        <h3 className="mt-1 text-lg font-semibold text-white" id="comparison-heading">Previous scan comparison</h3>
        <p className="mt-3 rounded-xl border border-field-border bg-black/20 p-4 text-sm leading-6 text-slate-300">
          {phase === 'complete'
            ? 'This result is now the on-device baseline. Complete another scan to see whether spread improved or worsened.'
            : 'No earlier completed scan is stored on this device yet.'}
        </p>
      </section>
    )
  }

  const affectedDelta = current.pct_affected - previous.spread.pct_affected
  const trend = trendFor(affectedDelta)
  const differentFile = previous.file_name && currentFileName
    && previous.file_name.trim().toLowerCase() !== currentFileName.trim().toLowerCase()
  const source = previous.source === 'synthetic_demo' ? 'Synthetic demo baseline' : 'Stored on this device'

  return (
    <section className="result-enter mt-5 border-t border-field-border pt-5" aria-labelledby="comparison-heading" id="scan-comparison">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Change over time</p>
          <h3 className="mt-1 text-lg font-semibold text-white" id="comparison-heading">Previous scan comparison</h3>
          <p className="mt-1 text-xs text-slate-500">{source} · {previousLabel(previous)}</p>
        </div>
        <span className={`rounded-full border px-3 py-1.5 text-xs font-bold ${trend.badge}`}>
          {affectedDelta > 0.05 ? 'Worsening' : affectedDelta < -0.05 ? 'Improving' : 'Stable'}
        </span>
      </div>

      <div className="mt-4 rounded-xl border border-field-border bg-black/20 p-4 sm:p-5">
        <p className={`text-sm font-semibold ${trend.tone}`}>{trend.label}</p>
        <div className="mt-4 space-y-4">
          <SpreadBar label={previousLabel(previous)} value={previous.spread.pct_affected} variant="previous" />
          <SpreadBar label="Current scan" value={current.pct_affected} variant="current" />
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <MetricDelta
          current={current.est_yield_loss_pct}
          label="Est. yield loss"
          previous={previous.spread.est_yield_loss_pct}
          suffix="%"
        />
        <MetricDelta
          current={current.clusters}
          decimals={0}
          label="Clusters"
          previous={previous.spread.clusters}
        />
        <article className="col-span-2 rounded-xl border border-field-border bg-black/20 p-3 sm:col-span-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Direction</p>
          <p className="mt-2 text-xl font-bold text-white">{current.direction ?? '—'}</p>
          <p className="mt-1 text-[11px] text-slate-500">was {previous.spread.direction ?? '—'}</p>
        </article>
      </div>

      <p className="mt-3 text-xs leading-5 text-slate-500">
        Previous image: <span className="font-medium text-slate-400">{previous.file_name || 'filename unavailable'}</span>.
        {differentFile && ' The filename differs from this scan; confirm both images are from the same field before using this trend.'}
      </p>
    </section>
  )
}
