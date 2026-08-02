export const AGENTS = [
  { id: 'orchestrator', icon: '◈', name: 'Orchestrator', short: 'Orchestr.' },
  { id: 'scout', icon: '⌗', name: 'Scout', short: 'Scout' },
  { id: 'observer', icon: '◉', name: 'Vision Observer', short: 'Observer' },
  { id: 'diagnostician', icon: '◎', name: 'Diagnostician', short: 'Diagnose' },
  { id: 'second-opinion', icon: '◇', name: 'Second-Opinion', short: '2nd op.' },
  { id: 'consensus', icon: '⇄', name: 'Consensus', short: 'Consensus' },
  { id: 'spread', icon: '↗', name: 'Spread Analyst', short: 'Spread' },
  { id: 'agronomist', icon: '♧', name: 'Agronomist', short: 'Agronomist' },
  { id: 'verifier', icon: '✓', name: 'Verifier', short: 'Verifier' },
  { id: 'planner', icon: '▤', name: 'Action Planner', short: 'Planner' },
  { id: 'reporter', icon: '◫', name: 'Reporter', short: 'Reporter' },
]

// Ordered, most specific first — the first prefix that matches wins.
const RULES = [
  ['orchestrator.escalate.', 'orchestrator', 'Uncertain tiles escalated', '↗', 'amber'],
  ['second_opinion.revised.', 'second-opinion', 'Tiles revised after a second look', '◇', 'amber'],
  ['second_opinion.tile.', 'second-opinion', 'Re-scoring uncertain tiles', '◇', 'cyan'],
  ['second_opinion.done', 'second-opinion', 'Second opinion complete', '◇', 'emerald'],
  ['scout.grid.', 'scout', 'Field divided into a tile grid', '⌗', 'cyan'],
  ['scout.skipped.', 'scout', 'Soil and sky tiles skipped', '⌗', 'cyan'],
  ['diagnose.crop_detected.', 'diagnostician', 'Crop read from the tiles', '◎', 'cyan'],
  ['diagnose.crop_auto.', 'diagnostician', 'Crop identified from the image', '◎', 'cyan'],
  ['diagnose.crop_mismatch.', 'diagnostician', 'Tile vote disagrees on the crop', '◎', 'amber'],
  ['diagnose.tile.', 'diagnostician', 'Diagnosing field tiles', '◎', 'cyan'],
  ['diagnose.done', 'diagnostician', 'Tile diagnosis complete', '◎', 'emerald'],

  // The vision cross-check. `observer.note` carries free text — see splitPayload below.
  ['observer.requested', 'observer', 'Second opinion requested on the whole image', '◉', 'vision'],
  // Internal bookkeeping — the verdict lands on state.vision here. Named rather than left to
  // the neutral fallback, where it would read as "observer verdict" with no agent attached.
  ['observer.verdict', 'observer', 'Vision verdict received', '◉', 'vision'],
  ['observer.note', 'observer', 'Vision model reports seeing', '◉', 'vision'],
  ['observer.not_crop_photo', 'observer', 'Not a photograph of a crop field', '◉', 'amber'],
  ['observer.crop_mismatch.', 'observer', 'Vision disagrees with the declared crop', '◉', 'amber'],
  ['observer.crop.', 'observer', 'Crop identified by the vision model', '◉', 'vision'],
  ['observer.off_enum.', 'observer', 'Vision saw something outside the known classes', '◉', 'amber'],
  ['observer.unavailable.', 'observer', 'Vision cross-check unavailable', '◉', 'neutral'],
  ['observer.sees.', 'observer', 'Vision model verdict', '◉', 'vision'],
  ['observer.pct.', 'observer', 'Vision severity estimate', '◉', 'vision'],
  ['observer.done', 'observer', 'Cross-check complete', '◉', 'vision'],

  ['consensus.contested.', 'consensus', 'Models disagree — advice withheld', '⇄', 'amber'],
  ['consensus.not_crop', 'consensus', 'No crop in this photograph', '⇄', 'amber'],
  ['consensus.relabel.', 'consensus', 'Diagnosis renamed by the vision check', '⇄', 'rewrite'],
  ['consensus.agree.', 'consensus', 'Both models agree', '⇄', 'emerald'],
  ['consensus.cnn.', 'consensus', 'Tile classifier verdict recorded', '⇄', 'cyan'],
  ['consensus.pct_gap.', 'consensus', 'Severity estimates differ', '⇄', 'neutral'],
  ['consensus.skipped.', 'consensus', 'No cross-check available', '⇄', 'neutral'],
  ['consensus.', 'consensus', 'Cross-check update', '⇄', 'vision'],

  ['agronomist.skipped.contested', 'agronomist', 'Plan withheld — models disagree', '♧', 'amber'],
  ['agronomist.done', 'agronomist', 'Treatment draft prepared', '♧', 'emerald'],
  ['verify.rewrite', 'verifier', 'Draft returned for accuracy', '↻', 'violet'],
  ['verify.pass', 'verifier', 'Safety verification passed', '✓', 'violet'],
  ['verify.block', 'verifier', 'Unverified treatment withheld', '!', 'amber'],
  ['planner.done', 'planner', 'Action schedule prepared', '▤', 'emerald'],
  ['reporter.done', 'reporter', 'Farmer report ready', '◫', 'emerald'],
  ['scout.done', 'scout', 'Field divided into tiles', '⌗', 'emerald'],
  ['spread.clusters.', 'spread', 'Infection clusters found', '↗', 'cyan'],
  ['spread.direction.', 'spread', 'Spread direction measured', '↗', 'cyan'],
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
  rewrite: 'border-yellow-400/40 bg-yellow-400/10 text-yellow-200',
  rose: 'border-rose-400/40 bg-rose-400/10 text-rose-200',
  violet: 'border-violet-400/40 bg-violet-400/10 text-violet-200',
  vision: 'border-sky-400/35 bg-sky-400/[0.07] text-sky-200',
}

const MAX_PAYLOAD = 240

/**
 * `observer.note|A dense green canopy…` -> `['observer.note', 'A dense green canopy…']`.
 *
 * One event carries a sentence rather than a slug, because what the vision model reports seeing
 * is a sentence and `friendlyLabel` would otherwise turn it into word soup by replacing every
 * full stop with a space. Splitting on the first pipe strictly extends the neutral fallback: an
 * unrecognised `foo.bar|some text` still renders, and a build of this file that predates the
 * convention shows it mangled but visible, which is the degradation the project asks for.
 */
export function splitPayload(eventName) {
  const cut = eventName.indexOf('|')
  if (cut === -1) return { name: eventName, payload: null }
  return { name: eventName.slice(0, cut), payload: eventName.slice(cut + 1).slice(0, MAX_PAYLOAD) }
}

export function getEventMeta(eventName) {
  const { name, payload } = splitPayload(eventName)
  const rule = RULES.find(([prefix]) => name.startsWith(prefix))
  if (!rule) {
    return {
      agentId: null,
      agentName: 'System',
      colour: COLOURS.neutral,
      friendlyLabel: name.replaceAll(/[._]/g, ' '),
      icon: '·',
      payload,
    }
  }

  const [, agentId, friendlyLabel, icon, tone] = rule
  return {
    agentId,
    agentName: AGENTS.find((agent) => agent.id === agentId)?.name ?? 'System',
    colour: COLOURS[tone] ?? COLOURS.neutral,
    friendlyLabel,
    icon,
    payload,
  }
}
