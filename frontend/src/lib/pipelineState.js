/**
 * Which agent is doing what, derived from the event log alone.
 *
 * Extracted from AgentPipeline so the spine and anything else read one source of truth. Pure,
 * so `demo/verify-demo.mjs` can assert against it without a DOM.
 *
 * Unknown events cannot break this: every test is a prefix match against events it knows, so an
 * event nobody here has heard of simply advances nothing. That is the same neutral-degradation
 * property `getEventMeta` provides for the log, and it is a project rule.
 */

function indexOfLast(events, prefix) {
  return events.findLastIndex((eventName) => eventName.startsWith(prefix))
}

export function deriveStates(events) {
  const has = (prefix) => events.some((eventName) => eventName.startsWith(prefix))
  const terminal = has('run.complete') || has('run.error')
  const escalated = has('orchestrator.escalate.')
  const diagnosisDone = has('diagnose.done')
  const secondDone = has('second_opinion.done')
  const observerDone = has('observer.done')
  const consensusDone = has('consensus.done')
  const spreadDone = has('spread.done')
  const draftIndex = indexOfLast(events, 'agronomist.done')
  const rewriteIndex = indexOfLast(events, 'verify.rewrite')
  const verified = has('verify.pass') || has('verify.block')
  const blocked = has('verify.block')
  const planned = has('planner.done')
  const reported = has('reporter.done')

  const states = {
    orchestrator: terminal ? 'done' : has('run.start') ? 'active' : 'pending',
    scout: has('scout.done') ? 'done' : has('run.start') ? 'active' : 'pending',
    // The Observer starts right after the Scout and is collected later — it is genuinely in
    // flight while the Diagnostician works, and the spine should show that rather than pretend
    // the pipeline is a straight line.
    observer: observerDone ? 'done' : has('observer.requested') ? 'active' : 'pending',
    diagnostician: diagnosisDone ? 'done' : has('scout.done') ? 'active' : 'pending',
    'second-opinion': secondDone ? 'done' : escalated ? 'active' : 'pending',
    consensus: consensusDone ? 'done' : diagnosisDone && observerDone ? 'active' : 'pending',
    spread: spreadDone ? 'done' : consensusDone ? 'active' : 'pending',
    agronomist: verified || draftIndex > rewriteIndex ? 'done' : spreadDone ? 'active' : 'pending',
    verifier: verified ? 'done' : draftIndex >= 0 ? 'active' : 'pending',
    planner: planned ? 'done' : has('verify.pass') ? 'active' : 'pending',
    reporter: reported ? 'done' : planned || blocked ? 'active' : 'pending',
  }

  // Nothing is still working once the run is over. A BLOCK skips the Planner and the Reporter
  // outright — there is no schedule to write and the refusal brief is the Verifier's — so
  // without this they pulse "active" for ever on the one screen a judge looks at longest.
  if (terminal) {
    for (const id of Object.keys(states)) {
      if (states[id] === 'active') states[id] = blocked ? 'skipped' : 'done'
    }
  }
  return states
}

/**
 * The counters shown along the spine.
 *
 * Numbers, not labels, because they read from the back of a room and because they are the
 * cheapest possible answer to "did you actually build a multi-agent system or wrap three
 * prompts". `vetoes` counts the times the Verifier sent a draft back — a loop in the graph,
 * executing, which is the part no prompt chain has.
 */
export function deriveCounters(events, runState) {
  const escalate = events.find((event) => event.startsWith('orchestrator.escalate.'))
  const relabel = events.find((event) => event.startsWith('consensus.relabel.'))
  return {
    escalated: escalate ? (Number.parseInt(escalate.split('.')[2], 10) || 0) : 0,
    opinions: events.some((event) => event.startsWith('observer.sees.')) ? 2 : 1,
    relabelled: relabel ? (Number.parseInt(relabel.split('.').pop(), 10) || 0) : 0,
    tiles: runState?.tiles?.length ?? 0,
    vetoes: events.filter((event) => event.startsWith('verify.rewrite')).length,
  }
}
