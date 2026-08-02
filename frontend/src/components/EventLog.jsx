import { useEffect, useMemo, useRef, useState } from 'react'
import { getEventMeta } from '../lib/eventCatalog.js'

function buildEntries(events, tileCount) {
  const entries = []
  let diagnosed = 0
  let rescored = 0

  events.forEach((eventName, index) => {
    if (eventName.startsWith('second_opinion.tile.')) {
      rescored += 1
      const entry = {
        eventName,
        id: 'second-opinion-progress',
        meta: getEventMeta(eventName),
        label: `Re-scoring uncertain tiles… ${rescored}`,
      }
      const at = entries.findIndex((item) => item.id === entry.id)
      if (at >= 0) entries[at] = entry
      else entries.push(entry)
      return
    }

    if (eventName.startsWith('diagnose.tile.')) {
      diagnosed += 1
      const entry = {
        eventName,
        id: 'diagnose-progress',
        meta: getEventMeta(eventName),
        label: `Diagnosing tiles… ${diagnosed}/${tileCount || '?'}`,
      }
      const currentIndex = entries.findIndex((item) => item.id === entry.id)
      if (currentIndex >= 0) entries[currentIndex] = entry
      else entries.push(entry)
      return
    }

    const meta = getEventMeta(eventName)
    let label = meta.friendlyLabel
    if (eventName.startsWith('orchestrator.escalate.')) {
      const count = eventName.match(/escalate\.(\d+)_tiles/)?.[1]
      if (count) label = `${count} uncertain tiles escalated`
    } else if (eventName.startsWith('consensus.relabel.')) {
      const renamed = eventName.match(/relabel\.(.+?)_to_(.+?)\.(\d+)_tiles/)
      if (renamed) {
        label = `Renamed ${renamed[1].replaceAll('_', ' ')} → ${renamed[2].replaceAll('_', ' ')} on ${renamed[3]} tiles`
      }
    } else if (eventName.startsWith('consensus.contested.')) {
      label = 'Models disagree — treatment advice withheld'
    }
    entries.push({ eventName, id: `${eventName}-${index}`, label, meta })
  })

  return entries
}

function formatElapsed(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

export default function EventLog({ events, phase, startedAt, streamStatus, tileCount }) {
  const [now, setNow] = useState(Date.now())
  const viewportRef = useRef(null)
  const entries = useMemo(() => buildEntries(events, tileCount), [events, tileCount])
  const diagnosedCount = events.filter((eventName) => eventName.startsWith('diagnose.tile.')).length

  useEffect(() => {
    setNow(Date.now())
    if (!startedAt || phase === 'complete' || phase === 'error') return undefined
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [phase, startedAt])

  useEffect(() => {
    const viewport = viewportRef.current
    viewport?.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })
  }, [diagnosedCount, entries.length])

  return (
    <section className="mt-5 border-t border-field-border pt-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">Live event log</h3>
          <p className="mt-1 text-[10px] text-slate-600">Newest activity appears below</p>
        </div>
        <div className="text-right">
          <p className="font-mono text-sm text-white">{startedAt ? formatElapsed(now - startedAt) : '00:00'}</p>
          <p className={`text-[9px] uppercase tracking-wider ${streamStatus === 'reconnecting' ? 'text-amber-300' : 'text-slate-600'}`}>
            {streamStatus === 'reconnecting' ? 'reconnecting' : streamStatus}
          </p>
        </div>
      </div>

      <div className="mt-3 h-44 space-y-2 overflow-y-auto overscroll-contain pr-1 sm:h-56" ref={viewportRef} aria-live="polite">
        {entries.length === 0 && (
          <div className="grid h-full place-items-center rounded-xl border border-dashed border-field-border text-center text-xs text-slate-600">
            Agent events will appear here
          </div>
        )}
        {entries.map((entry) => (
          <article className={`agent-event-enter rounded-lg border px-3 py-2 ${entry.meta.colour}`} key={entry.id}>
            <div className="flex items-start gap-2">
              <span aria-hidden="true" className="mt-px w-4 shrink-0 text-center text-xs">{entry.meta.icon}</span>
              <div className="min-w-0">
                <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">{entry.meta.agentName}</p>
                <p className="mt-0.5 text-xs leading-4">{entry.label}</p>
                {entry.meta.payload && (
                  // The free-text half of an `observer.note|…` event, rendered verbatim rather
                  // than slug-formatted — it is a sentence the model wrote about the photograph.
                  <p className="mt-1 text-xs italic leading-4 opacity-80">“{entry.meta.payload}”</p>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
