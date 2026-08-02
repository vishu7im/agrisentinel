import { useState } from 'react'
import FieldImageCanvas from './FieldImageCanvas.jsx'
import HeatmapLegend from './HeatmapLegend.jsx'
import SeverityPanel from './SeverityPanel.jsx'
import SpreadComparison from './SpreadComparison.jsx'
import TileDetail from './TileDetail.jsx'
import UploadZone from './UploadZone.jsx'

export default function FieldPanel({
  crop,
  error,
  fileName,
  onImage,
  phase,
  previewUrl,
  previousScan,
  relabel,
  runState,
  spread,
  spreadLoading,
  visibleTileIds,
}) {
  const [selectedTile, setSelectedTile] = useState(null)
  const busy = phase === 'uploading'
  const hasImage = Boolean(previewUrl)
  const tiles = runState?.tiles ?? []
  const gridSize = tiles.length
    ? {
        cols: Math.max(...tiles.map((tile) => tile.x)) + 1,
        rows: Math.max(...tiles.map((tile) => tile.y)) + 1,
      }
    : null
  // Re-read from the live tiles rather than held in state: a pinned tile whose label the
  // Consensus agent then rewrote would otherwise keep showing the label it had when tapped.
  const activeTile = selectedTile ? (tiles.find((t) => t.id === selectedTile) ?? null) : null

  return (
    <section className="min-w-0 scroll-mt-24 rounded-2xl border border-field-border bg-field-panel p-4 shadow-2xl shadow-black/20 sm:p-5" id="field-scan">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">
            Field scan
          </p>
          <h2 className="mt-1 truncate text-lg font-semibold text-white" title={hasImage ? fileName : undefined}>
            {hasImage ? fileName : 'Awaiting imagery'}
          </h2>
        </div>
        {hasImage && (
          <label className="flex min-h-11 shrink-0 cursor-pointer items-center rounded-lg border border-field-border px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-emerald-400/50 hover:text-white">
            <span className="sm:hidden">Replace</span><span className="hidden sm:inline">Replace image</span>
            <input
              accept="image/jpeg,image/png"
              className="sr-only"
              disabled={busy}
              // The crop is passed through. Without it a re-scan silently reverted to `auto`,
              // discarding the choice made on the upload screen — the same class of bug as the
              // original everything-is-tomato default, arriving through a different door.
              onChange={(event) => event.target.files?.[0] && onImage(event.target.files[0], crop)}
              type="file"
            />
          </label>
        )}
      </div>

      {!hasImage ? (
        <UploadZone disabled={busy} error={error} onImage={onImage} />
      ) : (
        <>
          <FieldImageCanvas
            centroids={spread?.cluster_centroids}
            gridSize={gridSize}
            onSelectTile={(tile) => setSelectedTile(tile?.id ?? null)}
            previewUrl={previewUrl}
            selectedTileId={activeTile?.id ?? null}
            tiles={tiles}
            visibleTileIds={visibleTileIds}
          >
            {(phase === 'uploading' || phase === 'scanning') && (
              <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/80 px-3 py-2 text-xs font-semibold text-white backdrop-blur">
                <span className="size-2 animate-pulse rounded-full bg-emerald-400" />
                {phase === 'uploading' ? 'Uploading field…' : 'Scanning field…'}
              </div>
            )}
          </FieldImageCanvas>
          <TileDetail
            onClear={() => setSelectedTile(null)}
            relabel={relabel}
            tile={activeTile}
          />
          <div className="mt-4">
            <HeatmapLegend hasClusters={Boolean(spread?.cluster_centroids?.length)} />
          </div>
          <SeverityPanel loading={spreadLoading} spread={spread} />
          <SpreadComparison
            blocked={runState?.verification?.status === 'BLOCK'}
            current={spread}
            currentFileName={fileName}
            phase={phase}
            previous={previousScan}
          />
          {error && (
            <p className="mt-4 rounded-lg border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-200" role="alert">
              {error}
            </p>
          )}
        </>
      )}
    </section>
  )
}
