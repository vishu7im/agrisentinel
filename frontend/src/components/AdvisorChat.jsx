import { useEffect, useRef, useState } from 'react'
import SourceDrawer from './SourceDrawer.jsx'
import { useAdvisorChat } from '../hooks/useAdvisorChat.js'
import { suggestedQuestions } from '../lib/suggestedQuestions.js'

const MARKER = /(\[doc_\d+#p\d+\])/g

/**
 * A cited sentence, with its marker rendered as the same numbered chip the treatment plan uses.
 * Same affordance, same drawer, so a claim in the conversation is checked exactly the way a
 * claim in the plan is.
 */
function Cited({ onSource, sources, text }) {
  const byId = new Map(sources.map((source, index) => [source.id, { number: index + 1, source }]))
  return text.split(MARKER).filter(Boolean).map((token, index) => {
    const marker = token.match(/^\[(doc_\d+#p\d+)\]$/)
    if (!marker) return <span key={index}>{token}</span>
    const entry = byId.get(marker[1])
    return (
      <button
        aria-label={entry ? `Open source ${entry.number}` : `Source ${marker[1]} unavailable`}
        className="mx-1 inline-flex min-w-5 -translate-y-px items-center justify-center rounded-full border border-emerald-400/30 bg-emerald-400/10 px-1.5 text-[10px] font-bold text-emerald-300 transition hover:border-emerald-300 hover:bg-emerald-400/20 disabled:border-slate-700 disabled:bg-slate-800 disabled:text-slate-500"
        disabled={!entry}
        key={index}
        onClick={() => entry && onSource(entry.source)}
        title={entry ? `${entry.source.doc}, page ${entry.source.page}` : marker[1]}
        type="button"
      >
        {entry?.number ?? '?'}
      </button>
    )
  })
}

function Turn({ onSource, turn }) {
  if (turn.role === 'user') {
    return (
      <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-emerald-400/15 px-3 py-2 text-sm leading-6 text-emerald-50">
        {turn.text}
      </p>
    )
  }
  // Amber for a refusal, never red — the Verifier's own colour rule. A decision not to answer
  // is an outcome of this system, not a fault in it.
  const refused = Boolean(turn.refused)
  return (
    <div
      className={`max-w-[92%] rounded-2xl rounded-bl-sm border px-3 py-2 text-sm leading-6 ${
        refused
          ? 'border-verdict-block/40 bg-verdict-block/10 text-amber-100'
          : 'border-field-border bg-black/25 text-slate-200'
      }`}
    >
      {refused && (
        <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-amber-300/80">
          {turn.refused === 'withheld' ? 'Advice withheld' : 'Outside our sources'}
        </p>
      )}
      {turn.text.split('\n').filter(Boolean).map((line, index) => (
        <p className={index ? 'mt-2' : undefined} key={index}>
          <Cited onSource={onSource} sources={turn.sources ?? []} text={line} />
        </p>
      ))}
    </div>
  )
}

export default function AdvisorChat({ blocked, crossCheck, disease, hasPlan, replaying, runId }) {
  const { error, pending, retry, send, turns } = useAdvisorChat(runId)
  const [draft, setDraft] = useState('')
  const [openSource, setOpenSource] = useState(null)
  const endRef = useRef(null)
  const suggestions = suggestedQuestions({ blocked, crossCheck, disease, hasPlan })
  // A replay has no backend behind it, and an input that posts into the void is worse than one
  // that explains itself. The suggestions still render, so the feature is legible with the
  // server down — which is the state the demo has to survive.
  const live = Boolean(runId) && !replaying

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [pending, turns.length])

  function submit(event) {
    event.preventDefault()
    send(draft)
    setDraft('')
  }

  return (
    <section className="mt-5 border-t border-white/10 pt-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300/70">
          Ask about this field
        </h3>
        <p className="text-[10px] text-slate-500">Answers come from the 10 source documents</p>
      </div>

      {turns.length > 0 && (
        <div className="mt-3 max-h-72 space-y-2 overflow-y-auto overscroll-contain pr-1" aria-live="polite">
          {turns.map((turn) => (
            <Turn key={turn.id} onSource={setOpenSource} turn={turn} />
          ))}
          {pending && (
            <p className="flex items-center gap-2 text-xs text-slate-500">
              <span className="size-1.5 animate-pulse rounded-full bg-emerald-400" />
              Searching the sources…
            </p>
          )}
          <div ref={endRef} />
        </div>
      )}

      {error && (
        <p className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-rose-400/25 bg-rose-400/10 px-3 py-2 text-xs text-rose-200" role="alert">
          {error}
          <button className="font-bold underline underline-offset-2" onClick={retry} type="button">
            Try again
          </button>
        </p>
      )}

      {turns.length === 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {suggestions.map((question) => (
            <button
              className="min-h-9 rounded-full border border-field-border bg-black/20 px-3 py-1.5 text-left text-xs text-slate-300 transition hover:border-emerald-400/50 hover:text-white disabled:opacity-50"
              disabled={!live || pending}
              key={question}
              onClick={() => send(question)}
              type="button"
            >
              {question}
            </button>
          ))}
        </div>
      )}

      <form className="mt-3 flex items-center gap-2" onSubmit={submit}>
        <input
          aria-label="Ask a question about this scan"
          className="min-h-11 min-w-0 flex-1 rounded-lg border border-field-border bg-black/25 px-3 text-sm text-white placeholder:text-slate-600 focus:border-emerald-400/60 focus:outline-none disabled:cursor-not-allowed"
          disabled={!live || pending}
          maxLength={600}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={live ? 'Ask a follow-up question…' : 'Recorded scan — chat needs the backend'}
          value={draft}
        />
        <button
          aria-label="Send question"
          className="grid size-11 shrink-0 place-items-center rounded-lg border border-emerald-400/30 bg-emerald-400/10 text-emerald-200 transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-40"
          disabled={!live || pending || !draft.trim()}
          type="submit"
        >
          <span aria-hidden="true">↵</span>
        </button>
      </form>

      {openSource && (
        <SourceDrawer
          onClose={() => setOpenSource(null)}
          source={openSource}
          sourceNumber={openSource.id}
        />
      )}
    </section>
  )
}
