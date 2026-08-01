import { useMemo, useState } from 'react'

function formatCost(cost) {
  if (!cost) return null
  try {
    const formatter = new Intl.NumberFormat('en-IN', {
      currency: cost.currency,
      maximumFractionDigits: 0,
      style: 'currency',
    })
    return `${formatter.format(cost.low)}–${formatter.format(cost.high)}`
  } catch {
    return `${cost.currency} ${cost.low}–${cost.high}`
  }
}

function formatDate(value) {
  if (!value) return null
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return value
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
    .format(new Date(year, month - 1, day))
}

export default function ScheduleTimeline({ costEstimate, rescanDate, schedule }) {
  const entries = useMemo(
    () => schedule
      .map((item, index) => ({ ...item, key: `${item.day_offset}-${index}` }))
      .sort((first, second) => first.day_offset - second.day_offset),
    [schedule],
  )
  const groups = useMemo(
    () => entries.reduce((result, item) => {
      const group = result.at(-1)
      if (group?.[0] === item.day_offset) group[1].push(item)
      else result.push([item.day_offset, [item]])
      return result
    }, []),
    [entries],
  )
  const [selectedKey, setSelectedKey] = useState(entries[0]?.key)
  const selected = entries.find((item) => item.key === selectedKey) ?? entries[0]
  const formattedCost = formatCost(costEstimate)

  return (
    <div className="result-enter mt-6">
      <div className="space-y-3 sm:hidden" aria-label="Action schedule">
        {groups.map(([dayOffset, items], groupIndex) => (
          <div className="relative pl-9" key={dayOffset}>
            {groupIndex < groups.length - 1 && (
              <span className="absolute bottom-[-0.9rem] left-[0.86rem] top-7 w-px bg-gradient-to-b from-emerald-400/60 to-field-border" />
            )}
            <span className={`absolute left-0 top-1 grid size-7 place-items-center rounded-full border text-[10px] font-black ${dayOffset === 0 ? 'border-emerald-300 bg-emerald-400 text-emerald-950' : 'border-emerald-400/50 bg-field-panel text-emerald-300'}`}>
              {dayOffset}
            </span>
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
              Day {dayOffset}{dayOffset === 0 ? ' · Today' : ''}
            </p>
            <div className="space-y-2">
              {items.map((item) => {
                const active = item.key === selected?.key
                const rescan = item.kind === 'rescan'
                return (
                  <button
                    aria-expanded={active}
                    className={`flex min-h-12 w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition ${rescan ? 'border-amber-400/30 bg-amber-400/10' : active ? 'border-emerald-400/50 bg-emerald-400/10' : 'border-field-border bg-black/15'} ${active ? 'ring-2 ring-emerald-400/10' : ''}`}
                    key={item.key}
                    onClick={() => setSelectedKey(item.key)}
                    type="button"
                  >
                    <span aria-hidden="true" className={`grid size-8 shrink-0 place-items-center rounded-full ${rescan ? 'bg-amber-400/15 text-amber-200' : 'bg-emerald-400/15 text-emerald-300'}`}>
                      {rescan ? '↻' : '✓'}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold leading-5 text-white">{item.action}</span>
                      {active && (
                        <span className="mt-1.5 block text-xs font-normal leading-5 text-slate-300">
                          {item.note}
                          {rescan && rescanDate && <span className="mt-1 block font-semibold text-amber-200">Re-scan: {formatDate(rescanDate)}</span>}
                        </span>
                      )}
                    </span>
                    <span aria-hidden="true" className="pt-1 text-slate-500">{active ? '⌄' : '›'}</span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="hidden overflow-x-auto pb-2 sm:block">
        <div className="relative min-w-[38rem] px-4 pt-1">
          <div className="absolute left-12 right-12 top-[4rem] h-px bg-gradient-to-r from-emerald-400/70 via-emerald-400/35 to-amber-400/70" />
          <div className="relative grid gap-6" style={{ gridTemplateColumns: `repeat(${groups.length}, minmax(0, 1fr))` }}>
            {groups.map(([dayOffset, items]) => (
              <div className="text-center" key={dayOffset}>
                <p className="text-sm font-semibold text-white">Day {dayOffset}</p>
                <p className={`mt-0.5 min-h-4 text-[10px] font-bold uppercase tracking-[0.16em] ${dayOffset === 0 ? 'text-emerald-300' : 'text-slate-600'}`}>
                  {dayOffset === 0 ? 'Today' : '\u00a0'}
                </p>
                <div className="mt-3 flex justify-center gap-2">
                  {items.map((item) => {
                    const active = item.key === selected?.key
                    const rescan = item.kind === 'rescan'
                    return (
                      <button
                        aria-expanded={active}
                        aria-label={`Day ${dayOffset}: ${item.action}`}
                        className={`group relative grid size-11 place-items-center rounded-full border-2 transition ${rescan ? 'border-amber-300 bg-amber-400/20 text-amber-200' : active ? 'border-emerald-300 bg-emerald-400 text-emerald-950' : 'border-emerald-400/60 bg-field-panel text-emerald-300 hover:border-emerald-300'} ${active ? 'ring-4 ring-emerald-400/10' : ''}`}
                        key={item.key}
                        onClick={() => setSelectedKey(item.key)}
                        type="button"
                      >
                        <span aria-hidden="true" className="text-xs font-black">{rescan ? '↻' : '●'}</span>
                      </button>
                    )
                  })}
                </div>
                <p className="mx-auto mt-3 max-w-36 text-xs leading-5 text-slate-400">
                  {items.length === 1 ? items[0].action : `${items.length} actions`}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {selected && (
        <div className={`result-enter mt-4 hidden rounded-xl border p-4 sm:block ${selected.kind === 'rescan' ? 'border-amber-400/30 bg-amber-400/10' : 'border-field-border bg-black/15'}`} key={selected.key}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-semibold text-white">{selected.action}</p>
            <span className="text-xs font-bold uppercase tracking-[0.14em] text-emerald-300">Day {selected.day_offset}</span>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-300">{selected.note}</p>
          {selected.kind === 'rescan' && rescanDate && (
            <p className="mt-3 text-sm font-semibold text-amber-200">Re-scan date: {formatDate(rescanDate)}</p>
          )}
        </div>
      )}

      {(formattedCost || rescanDate) && (
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-field-border pt-4 text-sm">
          {formattedCost && <p className="text-slate-300"><span className="font-semibold text-white">Estimated cost:</span> {formattedCost}</p>}
          {rescanDate && <p className="text-amber-200"><span className="font-semibold">Re-scan:</span> {formatDate(rescanDate)}</p>}
          {costEstimate?.note && <p className="w-full text-xs leading-5 text-slate-500">{costEstimate.note}</p>}
        </div>
      )}
    </div>
  )
}
