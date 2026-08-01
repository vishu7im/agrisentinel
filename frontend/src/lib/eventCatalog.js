export const AGENTS = [
  { id: 'orchestrator', name: 'Orchestrator', icon: '◈' },
  { id: 'scout', name: 'Scout', icon: '⌗' },
  { id: 'diagnostician', name: 'Diagnostician', icon: '◎' },
  { id: 'second-opinion', name: 'Second-Opinion', icon: '◇' },
  { id: 'spread', name: 'Spread Analyst', icon: '↗' },
  { id: 'agronomist', name: 'Agronomist', icon: '♧' },
  { id: 'verifier', name: 'Verifier', icon: '✓' },
  { id: 'planner', name: 'Action Planner', icon: '▤' },
  { id: 'reporter', name: 'Reporter', icon: '◫' },
]

const RULES = [
  ['orchestrator.escalate.', 'orchestrator', 'Uncertain tiles escalated', '↗', 'amber'],
  ['second_opinion.done', 'second-opinion', 'Second opinion complete', '◇', 'emerald'],
  ['diagnose.tile.', 'diagnostician', 'Diagnosing field tiles', '◎', 'cyan'],
  ['diagnose.done', 'diagnostician', 'Tile diagnosis complete', '◎', 'emerald'],
  ['agronomist.done', 'agronomist', 'Treatment draft prepared', '♧', 'emerald'],
  ['verify.rewrite', 'verifier', 'Draft returned for accuracy', '↻', 'violet'],
  ['verify.pass', 'verifier', 'Safety verification passed', '✓', 'violet'],
  ['verify.block', 'verifier', 'Unverified treatment withheld', '!', 'amber'],
  ['planner.done', 'planner', 'Action schedule prepared', '▤', 'emerald'],
  ['reporter.done', 'reporter', 'Farmer report ready', '◫', 'emerald'],
  ['scout.done', 'scout', 'Field divided into tiles', '⌗', 'emerald'],
  ['spread.done', 'spread', 'Spread pattern mapped', '↗', 'emerald'],
  ['run.start', 'orchestrator', 'Coordinating field analysis', '◈', 'cyan'],
  ['run.complete', 'orchestrator', 'Analysis complete', '✓', 'emerald'],
  ['run.error', 'orchestrator', 'Analysis stopped', '!', 'rose'],
  ['verify.', 'verifier', 'Verification update', '◇', 'violet'],
]

const COLOURS = {
  amber: 'border-amber-400/40 bg-amber-400/10 text-amber-200',
  cyan: 'border-cyan-400/25 bg-cyan-400/5 text-cyan-200',
  emerald: 'border-emerald-400/20 bg-emerald-400/5 text-emerald-200',
  neutral: 'border-slate-700 bg-white/[0.02] text-slate-300',
  rose: 'border-rose-400/40 bg-rose-400/10 text-rose-200',
  violet: 'border-violet-400/40 bg-violet-400/10 text-violet-200',
}

export function getEventMeta(eventName) {
  const rule = RULES.find(([prefix]) => eventName.startsWith(prefix))
  if (!rule) {
    return {
      agentId: null,
      agentName: 'System',
      colour: COLOURS.neutral,
      friendlyLabel: eventName.replaceAll(/[._]/g, ' '),
      icon: '·',
    }
  }

  const [, agentId, friendlyLabel, icon, tone] = rule
  return {
    agentId,
    agentName: AGENTS.find((agent) => agent.id === agentId)?.name ?? 'System',
    colour: COLOURS[tone],
    friendlyLabel,
    icon,
  }
}
