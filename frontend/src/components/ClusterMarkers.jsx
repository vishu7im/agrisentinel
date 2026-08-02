/**
 * The infection clusters the Spread Analyst found, drawn on the photograph.
 *
 * `spread.cluster_centroids` has been in the frozen contract since Phase 0 and has never been
 * rendered. It is DBSCAN output over the infected tiles — the answer to "is this one spreading
 * patch or scattered noise", which is the distinction between a spot treatment and spraying the
 * whole block, and it was only ever visible as a number.
 *
 * Coordinates are tile indices, so a centroid at (3, 2) on an 8x5 grid sits at the centre of
 * that cell: (3 + 0.5) / 8 across. Correct only because the parent box is now the image's exact
 * content box — see FieldImageCanvas.
 */

// Rings scale with the cluster's tile count, between these bounds as a share of the frame.
// Large enough to read across a room, small enough that three clusters do not merge into one.
const MIN_SIZE = 12
const MAX_SIZE = 34

export default function ClusterMarkers({ centroids, gridSize }) {
  if (!centroids?.length || !gridSize?.cols || !gridSize?.rows) return null

  const largest = Math.max(...centroids.map((c) => c.size ?? 1))

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      {centroids.map((centroid, index) => {
        const share = largest > 1 ? ((centroid.size ?? 1) - 1) / (largest - 1) : 0
        const size = MIN_SIZE + share * (MAX_SIZE - MIN_SIZE)
        return (
          <div
            className="cluster-ring absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white/70 shadow-[0_0_0_1px_rgba(0,0,0,.5),0_0_18px_rgba(255,255,255,.35)]"
            key={`${centroid.x}-${centroid.y}-${index}`}
            style={{
              animationDelay: `${index * 140}ms`,
              height: `${size}%`,
              left: `${((centroid.x + 0.5) / gridSize.cols) * 100}%`,
              top: `${((centroid.y + 0.5) / gridSize.rows) * 100}%`,
              width: `${size}%`,
            }}
          >
            <span className="absolute left-1/2 top-full mt-1 -translate-x-1/2 whitespace-nowrap rounded bg-slate-950/85 px-1.5 py-0.5 text-[10px] font-semibold text-white">
              {centroid.size} tile{centroid.size === 1 ? '' : 's'}
            </span>
          </div>
        )
      })}
    </div>
  )
}
