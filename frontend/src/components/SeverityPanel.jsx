import { useEffect, useState } from 'react'
import LoadingSkeleton, { SkeletonBlock } from './LoadingSkeleton.jsx'

const DIRECTION_DEGREES = {
  N: 0,
  NE: 45,
  E: 90,
  SE: 135,
  S: 180,
  SW: 225,
  W: 270,
  NW: 315,
}

function useCountUp(value, duration = 900) {
  const [displayValue, setDisplayValue] = useState(0)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setDisplayValue(value)
      return undefined
    }

    const startedAt = performance.now()
    let frameId

    function tick(now) {
      const progress = Math.min((now - startedAt) / duration, 1)
      const eased = 1 - ((1 - progress) ** 3)
      setDisplayValue(value * eased)
      if (progress < 1) frameId = requestAnimationFrame(tick)
    }

    frameId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frameId)
  }, [duration, value])

  return displayValue
}

function AnimatedNumber({ decimals = 0, suffix = '', value }) {
  const displayValue = useCountUp(value)
  return <>{displayValue.toFixed(decimals)}{suffix}</>
}

function severityFor(pctAffected) {
  // Demo thresholds: low < 10%, moderate 10–25%, severe > 25% of scored tiles.
  if (pctAffected < 10) return { label: 'Low', classes: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' }
  if (pctAffected <= 25) return { label: 'Moderate', classes: 'border-amber-400/30 bg-amber-400/10 text-amber-300' }
  return { label: 'Severe', classes: 'border-red-400/30 bg-red-400/10 text-red-300' }
}

export default function SeverityPanel({ loading, spread }) {
  if (!spread && !loading) return null

  if (loading && !spread) {
    return (
      <section className="mt-5 border-t border-field-border pt-5" aria-labelledby="severity-loading-heading">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Spread analysis</p>
          <h3 className="mt-1 text-lg font-semibold text-white" id="severity-loading-heading">Mapping field severity</h3>
        </div>
        <LoadingSkeleton
          className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-4"
          label="Mapping field severity"
        >
          {['affected area', 'infection clusters', 'spread direction', 'yield impact'].map((label) => (
            <div className="min-h-28 rounded-xl border border-field-border bg-black/20 p-3 sm:min-h-32 sm:p-4" key={label}>
              <SkeletonBlock className="h-2.5 w-24" />
              <SkeletonBlock className="mt-6 h-10 w-20" />
            </div>
          ))}
        </LoadingSkeleton>
      </section>
    )
  }

  const severity = severityFor(spread.pct_affected)
  const directionDegrees = DIRECTION_DEGREES[spread.direction]

  return (
    <section className="result-enter mt-5 border-t border-field-border pt-5" aria-labelledby="severity-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Spread analysis</p>
          <h3 className="mt-1 text-lg font-semibold text-white" id="severity-heading">Field severity</h3>
        </div>
        <span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] ${severity.classes}`}>
          {severity.label}
        </span>
      </div>

      <div className="result-cascade mt-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard label="Field affected">
          <AnimatedNumber decimals={1} suffix="%" value={spread.pct_affected} />
        </StatCard>
        <StatCard label="Infection clusters">
          <AnimatedNumber value={spread.clusters} />
        </StatCard>
        <StatCard label="Spread direction">
          {spread.direction ? (
            <span className="inline-flex items-center gap-3">
              <span
                aria-hidden="true"
                className="inline-block text-4xl leading-none text-amber-300 transition-transform duration-700"
                style={{ transform: `rotate(${directionDegrees}deg)` }}
              >
                ↑
              </span>
              <span>{spread.direction}</span>
            </span>
          ) : <span className="text-slate-500">—</span>}
        </StatCard>
        <StatCard label="Est. yield loss">
          <AnimatedNumber decimals={1} suffix="%" value={spread.est_yield_loss_pct} />
        </StatCard>
      </div>
    </section>
  )
}

function StatCard({ children, label }) {
  return (
    <article className="min-h-28 rounded-xl border border-field-border bg-black/20 p-3 sm:min-h-32 sm:p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</p>
      <p className="mt-5 text-3xl font-bold tabular-nums tracking-tight text-white sm:text-5xl">{children}</p>
    </article>
  )
}
