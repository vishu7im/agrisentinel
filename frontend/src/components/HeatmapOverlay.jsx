function humanize(label) {
  return label.replace(/^skipped_/, 'Skipped: ').replaceAll('_', ' ')
}

/**
 * Tile colour. Opacity carries confidence, hue carries the finding.
 *
 * `crossChecked` paints the tiles both models call diseased in `tile.severe` — the red that has
 * been sitting in the theme unused since Phase 0. It is the only place on screen where the two
 * independent readings are visible at the level of a single cell, and it earns the colour:
 * "orange means the classifier flagged this, red means so did the second model."
 */
function tileFill(tile, crossChecked) {
  if (tile.label.startsWith('skipped')) return 'rgba(75, 85, 99, 0.38)'
  const alpha = 0.4 + (tile.confidence ?? 0) * 0.6
  if (tile.label === 'healthy') return `rgba(74, 222, 128, ${alpha})`
  return crossChecked ? `rgba(220, 38, 38, ${alpha})` : `rgba(249, 115, 22, ${alpha})`
}

export default function HeatmapOverlay({
  crossChecked = false,
  diagnosedTileIds,
  onSelectTile,
  selectedTileId,
  tiles,
}) {
  if (!tiles?.length) return null
  const columns = Math.max(...tiles.map((tile) => tile.x)) + 1
  const rows = Math.max(...tiles.map((tile) => tile.y)) + 1
  const diagnosed = new Set(diagnosedTileIds)

  return (
    <div
      aria-label={`${columns} by ${rows} field diagnosis heatmap`}
      className="absolute inset-0 grid"
      style={{
        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
      }}
    >
      {tiles.map((tile) => {
        const visible = diagnosed.has(tile.id)
        const confidence =
          tile.confidence == null ? 'Not scored' : `${Math.round(tile.confidence * 100)}% confidence`
        const selected = selectedTileId === tile.id
        const tooltipY = tile.y < rows / 2 ? 'top-full mt-2' : 'bottom-full mb-2'
        const tooltipX =
          tile.x === 0 ? 'left-1' : tile.x === columns - 1 ? 'right-1' : 'left-1/2 -translate-x-1/2'

        return (
          // A button, not a div. The legend has always said "tap a tile for detail" and on a
          // touch screen that was untrue — the detail lived in a `group-hover` popover. Making
          // it a real control gives the same affordance to a finger, a mouse and a keyboard,
          // and TileDetail below the image is what a phone actually shows.
          <button
            aria-label={
              visible ? `${tile.id}: ${humanize(tile.label)}, ${confidence}` : `${tile.id}: pending`
            }
            aria-pressed={selected}
            className={`group relative border border-white/10 transition-[background-color] duration-500 ${
              visible && tile.escalated ? 'border-2 border-dashed !border-white' : ''
            } ${selected ? 'z-20 outline outline-2 outline-offset-[-2px] outline-white' : ''}`}
            disabled={!visible}
            key={tile.id}
            onClick={() => onSelectTile?.(selected ? null : tile)}
            style={{
              backgroundColor: visible ? tileFill(tile, crossChecked) : 'transparent',
              gridColumn: tile.x + 1,
              gridRow: tile.y + 1,
            }}
            type="button"
          >
            {visible && tile.escalated && (
              <span
                className="absolute right-1 top-1 grid size-5 place-items-center rounded-full bg-white text-[11px] font-black text-slate-900 shadow-lg"
                title="Second opinion used"
              >
                ↻
              </span>
            )}
            {visible && (
              <div
                className={`pointer-events-none absolute z-30 hidden min-w-max rounded-lg border border-white/15 bg-slate-950/95 px-3 py-2 text-left text-xs shadow-2xl group-hover:block group-focus:block ${tooltipX} ${tooltipY}`}
              >
                <p className="font-mono text-slate-400">{tile.id}</p>
                <p className="mt-0.5 capitalize text-white">{humanize(tile.label)}</p>
                <p className="mt-0.5 text-slate-300">{confidence}</p>
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}
