import { AGENTS } from '../lib/eventCatalog.js'

function indexOfLast(events, prefix) {
  return events.findLastIndex((eventName) => eventName.startsWith(prefix))
}

function deriveStates(events) {
  const has = (prefix) => events.some((eventName) => eventName.startsWith(prefix))
  const terminal = has('run.complete') || has('run.error')
  const escalated = has('orchestrator.escalate.')
  const diagnosisDone = has('diagnose.done')
  const secondDone = has('second_opinion.done')
  const spreadDone = has('spread.done')
  const draftIndex = indexOfLast(events, 'agronomist.done')
  const rewriteIndex = indexOfLast(events, 'verify.rewrite')
  const verified = has('verify.pass') || has('verify.block')
  const blocked = has('verify.block')
  const planned = has('planner.done')
  const reported = has('reporter.done')

  return {
    orchestrator: terminal ? 'done' : has('run.start') ? 'active' : 'pending',
    scout: has('scout.done') ? 'done' : has('run.start') ? 'active' : 'pending',
    diagnostician: diagnosisDone ? 'done' : has('scout.done') ? 'active' : 'pending',
    'second-opinion': secondDone ? 'done' : escalated ? 'active' : 'pending',
    spread: spreadDone ? 'done' : diagnosisDone && (!escalated || secondDone) ? 'active' : 'pending',
    agronomist: verified || draftIndex > rewriteIndex ? 'done' : spreadDone ? 'active' : 'pending',
    verifier: verified ? 'done' : draftIndex >= 0 ? 'active' : 'pending',
    planner: planned ? 'done' : has('verify.pass') ? 'active' : 'pending',
    reporter: reported ? 'done' : planned || blocked ? 'active' : 'pending',
  }
}

export default function AgentPipeline({ events }) {
  const states = deriveStates(events)

  return (
    <ol className="mt-4 grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-1">
      {AGENTS.map((agent, index) => {
        const state = states[agent.id]
        return (
          <li className="relative flex items-center gap-3 rounded-lg px-2 py-1.5" key={agent.id}>
            {index < AGENTS.length - 1 && (
              <span className="absolute left-[1.05rem] top-8 hidden h-3 w-px bg-field-border lg:block" />
            )}
            <span className={`grid size-7 shrink-0 place-items-center rounded-full border text-xs transition-all duration-300 ${
              state === 'done'
                ? 'border-emerald-400 bg-emerald-400 text-emerald-950'
                : state === 'active'
                  ? 'animate-pulse border-cyan-300 bg-cyan-300/10 text-cyan-200 shadow-[0_0_14px_rgba(103,232,249,.25)]'
                  : 'border-slate-700 text-slate-600'
            }`}>
              {state === 'done' ? '✓' : agent.icon}
            </span>
            <span className={`min-w-0 flex-1 truncate text-xs font-medium ${state === 'pending' ? 'text-slate-600' : 'text-slate-200'}`}>
              {agent.name}
            </span>
            <span className={`text-[9px] font-bold uppercase tracking-wider ${
              state === 'done' ? 'text-emerald-400' : state === 'active' ? 'text-cyan-300' : 'text-slate-700'
            }`}>
              {state}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
