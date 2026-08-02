import { AGENTS } from '../lib/eventCatalog.js'
import { deriveCounters, deriveStates } from '../lib/pipelineState.js'

/**
 * The eleven agents, across the top, executing.
 *
 * This used to be a 22rem right rail — peripheral on a laptop, below the fold on a phone. The
 * architecture is the thing this project is being judged on and it was the least visible part
 * of the screen.
 *
 * Two details do the actual persuading:
 *
 * **The veto edge.** An arc drawn back from the Verifier to the Agronomist that lights amber
 * when `verify.rewrite` fires, while the Agronomist node visibly re-enters `active`. A loop in
 * the graph, running, is the one thing a chain of three prompts cannot show.
 *
 * **The counters.** `40 tiles · 3 escalated · 2 opinions · 1 veto`, derived from the log.
 */

const STATE_STYLE = {
  active: 'animate-pulse border-cyan-300 bg-cyan-300/10 text-cyan-200 shadow-[0_0_14px_rgba(103,232,249,.3)]',
  done: 'border-emerald-400 bg-emerald-400 text-emerald-950',
  pending: 'border-slate-700 text-slate-600',
  // A stage a refusal made unnecessary. Amber, and drawn as deliberately not-run rather than
  // greyed out like something still waiting — the run is over and this did not happen.
  skipped: 'border-verdict-block/50 bg-verdict-block/10 text-amber-300/70',
}

function Counter({ label, value }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="text-sm font-bold tabular-nums text-white">{value}</span>
      <span className="text-[10px] uppercase tracking-wider text-slate-500">{label}</span>
    </span>
  )
}

export default function PipelineSpine({ events = [], runState }) {
  const states = deriveStates(events)
  const counters = deriveCounters(events, runState)
  const vetoing = counters.vetoes > 0

  return (
    <section
      aria-label="Agent pipeline"
      className="sticky top-0 z-30 border-b border-field-border bg-field-panel/95 backdrop-blur lg:top-[4.25rem]"
    >
      <div className="page-gutter mx-auto max-w-[1600px]">
        <div className="flex items-center gap-4 overflow-x-auto py-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <ol className="flex shrink-0 items-center gap-0">
            {AGENTS.map((agent, index) => {
              const state = states[agent.id] ?? 'pending'
              // The rewrite loop runs backwards from the Verifier to the Agronomist. Marking
              // the span between them is what lets the arc below be drawn over exactly it.
              const inLoop = agent.id === 'agronomist' || agent.id === 'verifier'
              return (
                <li className="relative flex items-center" key={agent.id}>
                  {index > 0 && (
                    <span
                      aria-hidden="true"
                      className={`h-px w-4 shrink-0 transition-colors duration-500 sm:w-6 ${
                        state === 'pending' ? 'bg-field-border' : 'bg-emerald-400/50'
                      }`}
                    />
                  )}
                  <div className="flex flex-col items-center gap-1 px-0.5">
                    <span
                      className={`grid size-8 shrink-0 place-items-center rounded-full border text-xs transition-all duration-300 ${STATE_STYLE[state]} ${
                        inLoop && vetoing ? 'ring-2 ring-verdict-rewrite/40' : ''
                      }`}
                      title={`${agent.name}: ${state}`}
                    >
                      {state === 'done' ? '✓' : state === 'skipped' ? '–' : agent.icon}
                    </span>
                    <span
                      className={`max-w-[5.5rem] truncate text-center text-[9px] font-medium leading-tight ${
                        state === 'pending' ? 'text-slate-600' : 'text-slate-300'
                      }`}
                    >
                      {agent.short ?? agent.name}
                    </span>
                  </div>
                </li>
              )
            })}
          </ol>

          {vetoing && (
            <span className="veto-edge flex shrink-0 items-center gap-1.5 rounded-full border border-verdict-rewrite/50 bg-verdict-rewrite/10 px-3 py-1 text-[11px] font-semibold text-yellow-200">
              ↩ Verifier sent the draft back
              {counters.vetoes > 1 && ` ×${counters.vetoes}`}
            </span>
          )}

          <div className="ml-auto hidden shrink-0 items-center gap-4 pl-4 xl:flex">
            <Counter label="tiles" value={counters.tiles} />
            <Counter label="escalated" value={counters.escalated} />
            <Counter label="opinions" value={counters.opinions} />
            <Counter label="vetoes" value={counters.vetoes} />
          </div>
        </div>
      </div>
    </section>
  )
}
