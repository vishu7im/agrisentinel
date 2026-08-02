/**
 * What one tile says, for a finger.
 *
 * The hover popover on the grid is fine with a mouse and invisible on a phone, which is the
 * device this gets demonstrated on. This is the same information as a real row under the image,
 * plus the one thing the popover could never show: whether the vision cross-check renamed the
 * finding on this tile.
 */

function humanize(label) {
  return String(label ?? '').replace(/^skipped_/, 'Skipped: ').replaceAll('_', ' ')
}

export default function TileDetail({ onClear, relabel, tile }) {
  if (!tile) {
    return (
      <p className="mt-3 text-center text-xs text-slate-500">
        Tap any tile for its diagnosis and confidence.
      </p>
    )
  }

  const confidence = tile.confidence == null ? null : Math.round(tile.confidence * 100)
  const renamed = Boolean(relabel) && tile.label === relabel.to

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-field-border bg-black/20 px-4 py-3">
      <span className="font-mono text-xs text-slate-400">{tile.id}</span>
      <span className="text-sm font-semibold capitalize text-white">{humanize(tile.label)}</span>
      {confidence != null && (
        <span className="text-sm tabular-nums text-slate-300">{confidence}% confident</span>
      )}
      {tile.escalated && (
        <span className="rounded-full border border-white/20 bg-white/5 px-2 py-0.5 text-[11px] text-slate-200">
          ↻ second opinion
        </span>
      )}
      {renamed && (
        <span className="rounded-full border border-vision/40 bg-vision/10 px-2 py-0.5 text-[11px] text-sky-200">
          renamed from {humanize(relabel.from)}
        </span>
      )}
      <button
        className="ml-auto min-h-8 rounded-lg border border-field-border px-3 text-xs text-slate-400 transition hover:border-slate-500 hover:text-white"
        onClick={onClear}
        type="button"
      >
        Clear
      </button>
    </div>
  )
}
