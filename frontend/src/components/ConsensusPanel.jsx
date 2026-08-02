import { CONSENSUS_COPY, UNAVAILABLE_COPY, humaniseLabel } from '../lib/consensus.js'

/**
 * The two-model cross-check, side by side.
 *
 * Left: a 40-tile CNN running offline on the CPU. Right: a whole-image vision model that never
 * saw the CNN's answer. Between them, the verdict — and on a contested run, that verdict is the
 * most interesting thing this system does, because it is the moment it declines to give advice
 * it cannot stand behind.
 *
 * Colour carries the argument: emerald is the classifier, sky is the second opinion, amber is
 * a refusal. Never red — a refusal is a decision, not an error.
 */

const TONE = {
  block: {
    chip: 'border-verdict-block/50 bg-verdict-block/15 text-amber-200',
    ring: 'ring-verdict-block/30',
  },
  neutral: {
    chip: 'border-slate-600 bg-white/[0.03] text-slate-300',
    ring: 'ring-slate-700/40',
  },
  pass: {
    chip: 'border-verdict-pass/50 bg-verdict-pass/15 text-emerald-200',
    ring: 'ring-verdict-pass/30',
  },
  rewrite: {
    chip: 'border-verdict-rewrite/50 bg-verdict-rewrite/15 text-yellow-200',
    ring: 'ring-verdict-rewrite/30',
  },
  vision: {
    chip: 'border-vision/50 bg-vision/15 text-sky-200',
    ring: 'ring-vision/30',
  },
}

function ModelCard({ accent, detail, eyebrow, label, pct, pending, sub, title }) {
  return (
    <div className={`flex-1 rounded-xl border ${accent.border} ${accent.bg} p-4`}>
      <div className="flex items-baseline justify-between gap-2">
        <p className={`text-eyebrow font-semibold uppercase ${accent.text}`}>{eyebrow}</p>
        <p className="shrink-0 text-[10px] uppercase tracking-wider text-slate-500">{sub}</p>
      </div>
      <p className="mt-2 truncate text-lg font-semibold text-white" title={title}>
        {pending ? <span className="text-slate-500">Working…</span> : label}
      </p>
      <div className="mt-3 flex items-end gap-2">
        <span className="text-stat font-bold tabular-nums text-white">
          {pct == null ? '—' : `${pct}%`}
        </span>
        <span className="pb-1.5 text-xs text-slate-400">of field</span>
      </div>
      {detail && <p className="mt-2 text-xs leading-relaxed text-slate-400">{detail}</p>}
    </div>
  )
}

export default function ConsensusPanel({ consensus, phase }) {
  const { cnn, gap, observer, relabel, state, unavailableReason } = consensus

  // Nothing to say before a scan starts, and an empty box on the landing screen is worse than
  // no box at all.
  if (state === 'idle' && phase !== 'scanning') return null

  const copy = CONSENSUS_COPY[state] ?? CONSENSUS_COPY.unavailable
  const tone = TONE[copy.tone] ?? TONE.neutral
  const observing = state === 'observing'
  const contested = state === 'contested'

  return (
    <section
      aria-labelledby="consensus-heading"
      className={`order-2 rounded-2xl border border-field-border bg-field-panel p-4 shadow-2xl shadow-black/20 ring-1 ${tone.ring} sm:p-5 lg:col-span-2`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-eyebrow font-semibold uppercase text-vision">Cross-check</p>
          <h2 className="mt-1 text-lg font-semibold text-white" id="consensus-heading">
            Two models, one field
          </h2>
        </div>
        <span
          className={`consensus-verdict rounded-full border px-3 py-1 text-xs font-semibold ${tone.chip}`}
          key={state}
        >
          {copy.label}
        </span>
      </div>

      <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-stretch">
        <ModelCard
          accent={{
            bg: 'bg-emerald-400/[0.04]',
            border: 'border-emerald-400/20',
            text: 'text-emerald-300/80',
          }}
          detail={
            cnn?.derived
              ? 'Recomputed from the tile grid.'
              : '40 tiles · EfficientNet-B0 · ONNX on CPU, offline'
          }
          eyebrow="Tile classifier"
          label={humaniseLabel(cnn?.disease)}
          pct={cnn?.pct}
          sub="where"
          title={cnn?.disease ?? ''}
        />

        <div className="flex items-center justify-center lg:w-16">
          <span
            aria-hidden="true"
            className={`grid size-9 place-items-center rounded-full border text-sm ${tone.chip}`}
          >
            {contested ? '≠' : state === 'agree' ? '=' : '⇄'}
          </span>
        </div>

        <ModelCard
          accent={{ bg: 'bg-vision/[0.04]', border: 'border-vision/20', text: 'text-vision' }}
          detail={
            unavailableReason
              ? (UNAVAILABLE_COPY[unavailableReason] ?? unavailableReason)
              : 'Whole image · one pass · never shown the tile result'
          }
          eyebrow="Vision cross-check"
          label={
            observer.isCropField === false
              ? 'Not a field photo'
              : humaniseLabel(observer.disease ?? (unavailableReason ? '—' : 'unknown'))
          }
          pct={observer.pct}
          pending={observing}
          sub="what"
          title={observer.classKey ?? ''}
        />
      </div>

      <p className={`mt-4 text-sm leading-relaxed ${contested ? 'text-amber-200' : 'text-slate-300'}`}>
        {copy.text}
      </p>

      {relabel && (
        <p className="mt-2 text-sm text-slate-400">
          <span className="text-slate-500 line-through">{humaniseLabel(relabel.from)}</span>
          <span className="mx-2 text-vision">→</span>
          <span className="font-semibold text-white">{humaniseLabel(relabel.to)}</span>
          <span className="ml-2 text-xs text-slate-500">
            across {relabel.tiles} tile{relabel.tiles === 1 ? '' : 's'}
          </span>
        </p>
      )}

      {observer.note && (
        <figure className="mt-3 border-l-2 border-vision/40 pl-3">
          <blockquote className="text-sm italic leading-relaxed text-slate-300">
            “{observer.note}”
          </blockquote>
          <figcaption className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">
            What the second model reports seeing
          </figcaption>
        </figure>
      )}

      {gap != null && gap >= 30 && (
        <p className="mt-3 text-xs text-slate-500">
          The two estimates differ by {Math.round(gap)} percentage points. The tile grid is the
          measurement; the whole-image figure is an estimate.
        </p>
      )}
    </section>
  )
}
