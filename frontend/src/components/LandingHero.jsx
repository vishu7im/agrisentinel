import { AGENTS } from '../lib/eventCatalog.js'
import UploadZone from './UploadZone.jsx'

/**
 * What a judge sees before anything has happened.
 *
 * This screen used to be nine grey "pending" agent rows and two dashed placeholder boxes — an
 * empty dashboard, which reads as broken rather than ready. It is also the first and sometimes
 * the only screen anyone sees.
 *
 * The third claim tile is the one that matters. Naming the lab-to-field gap before a judge finds
 * it is worth more than hiding it, and it is the reason the whole cross-check exists — so the
 * weakness and the feature are stated in the same breath.
 */

const CLAIMS = [
  {
    body: 'A field is tiled into 40 cells and every cell is classified separately, so the answer is a map of where the infection is, not one verdict about one leaf.',
    head: '40 tiles, not one leaf',
  },
  {
    body: 'A tile CNN running offline on the CPU, and a whole-image vision model that never sees the first answer. When they disagree, you are told.',
    head: 'Two independent opinions',
  },
  {
    body: '95.6% on lab leaves. 86.6% under simulated field conditions. We show both numbers and cross-check every scan, because that gap is real.',
    head: 'We publish the gap',
  },
]

export default function LandingHero({ demoCases, error, onImage, onStartDemo }) {
  return (
    <div className="mx-auto max-w-4xl py-6 sm:py-12">
      <p className="text-eyebrow font-semibold uppercase text-emerald-300/70">
        Existing tools classify a leaf
      </p>
      <h2 className="mt-2 text-display font-bold text-white">
        AgriSentinel inspects a<span className="text-emerald-400"> field</span>.
      </h2>
      <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-300 sm:text-lg">
        Drop one photograph. Eleven agents tile it into forty cells, diagnose each one, cross-check
        the whole image against a second vision model, ground a treatment plan in cited documents —
        and a verifier with veto power decides whether you are allowed to see it.
      </p>

      <div className="mt-8">
        <UploadZone error={error} onImage={onImage} />
      </div>

      {demoCases?.length > 0 && (
        <div className="mt-8">
          <p className="text-eyebrow font-semibold uppercase text-slate-500">
            No photo to hand? Replay a recorded scan
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {demoCases.map((demoCase) => (
              <button
                className="group rounded-xl border border-field-border bg-black/20 p-4 text-left transition hover:border-emerald-400/50 hover:bg-emerald-400/[0.04]"
                key={demoCase.id}
                onClick={() => onStartDemo(demoCase.id)}
                type="button"
              >
                <p className="text-sm font-semibold text-white group-hover:text-emerald-200">
                  {demoCase.label ?? demoCase.id}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">
                  {demoCase.description ?? 'Recorded run · plays without a backend'}
                </p>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-10 border-t border-field-border pt-6">
        <p className="text-eyebrow font-semibold uppercase text-slate-500">The pipeline</p>
        <ol className="mt-3 flex flex-wrap items-center gap-x-1 gap-y-2">
          {AGENTS.map((agent, index) => (
            <li className="flex items-center gap-1" key={agent.id}>
              {index > 0 && <span aria-hidden="true" className="text-slate-700">·</span>}
              <span className="flex items-center gap-1.5 rounded-full border border-field-border bg-black/20 px-2.5 py-1 text-[11px] text-slate-400">
                <span aria-hidden="true" className="text-slate-500">{agent.icon}</span>
                {agent.name}
              </span>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-xs text-slate-500">
          The Verifier can send a plan back to the Agronomist, or refuse to publish it at all.
          That loop runs live, and you can watch it happen.
        </p>
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {CLAIMS.map((claim) => (
          <div className="rounded-xl border border-field-border bg-field-panel p-4" key={claim.head}>
            <p className="text-sm font-semibold text-white">{claim.head}</p>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">{claim.body}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
