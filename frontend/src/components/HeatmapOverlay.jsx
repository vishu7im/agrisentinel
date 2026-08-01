function humanize(label) {
  return label.replace(/^skipped_/, 'Skipped: ').replaceAll('_', ' ')
}

function tileFill(tile) {
  if (tile.label.startsWith('skipped')) return 'rgba(75, 85, 99, 0.38)'
  const confidence = tile.confidence ?? 0
  const alpha = 0.4 + confidence * 0.6
  return tile.label === 'healthy'
    ? `rgba(74, 222, 128, ${alpha})`
    : `rgba(249, 115, 22, ${alpha})`
}

export default function HeatmapOverlay({ diagnosedTileIds, tiles }) {
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
        const confidence = tile.confidence == null ? 'Not scored' : `${Math.round(tile.confidence * 100)}% confidence`
        const tooltipY = tile.y < rows / 2 ? 'top-full mt-2' : 'bottom-full mb-2'
        const tooltipX =
          tile.x === 0
            ? 'left-1'
            : tile.x === columns - 1
              ? 'right-1'
              : 'left-1/2 -translate-x-1/2'

        return (
          <div
            key={tile.id}
            aria-label={visible ? `${tile.id}: ${humanize(tile.label)}, ${confidence}` : `${tile.id}: pending`}
            className={`group relative border border-white/10 transition-[background-color] duration-500 ${
              visible && tile.escalated ? 'border-2 border-dashed !border-white' : ''
            }`}
            style={{
              backgroundColor: visible ? tileFill(tile) : 'transparent',
              gridColumn: tile.x + 1,
              gridRow: tile.y + 1,
            }}
            tabIndex={visible ? 0 : -1}
          >
            {visible && tile.escalated && (
              <span className="absolute right-1 top-1 grid size-5 place-items-center rounded-full bg-white text-[11px] font-black text-slate-900 shadow-lg" title="Second opinion used">
                ↻
              </span>
            )}
            {visible && (
              <div className={`pointer-events-none absolute z-30 hidden min-w-max rounded-lg border border-white/15 bg-slate-950/95 px-3 py-2 text-left text-xs shadow-2xl group-hover:block group-focus:block ${tooltipX} ${tooltipY}`}>
                <p className="font-mono text-slate-400">{tile.id}</p>
                <p className="mt-0.5 capitalize text-white">{humanize(tile.label)}</p>
                <p className="mt-0.5 text-slate-300">{confidence}</p>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
