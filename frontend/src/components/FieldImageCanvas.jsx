import { useState } from 'react'
import ClusterMarkers from './ClusterMarkers.jsx'
import HeatmapOverlay from './HeatmapOverlay.jsx'

/**
 * The field photograph with the tile grid laid exactly over it.
 *
 * The bug this exists to fix: the overlay used to be `absolute inset-0` inside a container
 * holding an `object-contain` image. `agents/tiling.py` lays its grid edge to edge over the
 * whole image with no padding, so the overlay is correct only when the container box and the
 * image's content box are the same rectangle — and with `object-contain` they are the same
 * rectangle only when the aspect ratios happen to match. Two separate failures came out of it:
 *
 *   - a portrait phone photo pillarboxes, and tiles land on the black bars beside the picture;
 *   - with the height cap off on desktop, that same photo renders two thousand pixels tall and
 *     everything below the image becomes unreachable.
 *
 * Fixed by construction rather than by measurement. The inner box is given the image's own
 * aspect ratio and the image fills it, so the inner box *is* the content box at every viewport
 * and `inset-0` is exact. Preferred over reading `getBoundingClientRect` into state: no layout
 * effect, no re-render on every frame of a window drag, and it cannot drift by a subpixel.
 *
 * `naturalWidth/naturalHeight` already account for EXIF orientation in current browsers, which
 * matches the `ImageOps.exif_transpose` the Scout applies before tiling.
 */

// Before the image loads there is no aspect ratio to use. 8:5 is the tile grid's own shape, so
// the placeholder is the size the result will most often be and nothing jumps on load.
const FALLBACK_RATIO = '8 / 5'

export default function FieldImageCanvas({
  centroids,
  children,
  gridSize,
  onSelectTile,
  previewUrl,
  selectedTileId,
  tiles,
  visibleTileIds,
}) {
  const [natural, setNatural] = useState(null)

  return (
    <div className="grid place-items-center overflow-hidden rounded-xl border border-field-border bg-black">
      <div
        className="relative w-full"
        style={{
          aspectRatio: natural ? `${natural.w} / ${natural.h}` : FALLBACK_RATIO,
          // The cap belongs here, on the box that has the image's shape, so a tall photo is
          // bounded without the grid ever leaving the picture.
          maxHeight: 'min(70dvh, 34rem)',
          maxWidth: natural ? `calc(min(70dvh, 34rem) * ${natural.w} / ${natural.h})` : '100%',
        }}
      >
        <img
          alt="Uploaded field selected for disease analysis"
          className="block size-full"
          onLoad={(event) =>
            setNatural({
              h: event.currentTarget.naturalHeight || 5,
              w: event.currentTarget.naturalWidth || 8,
            })
          }
          src={previewUrl}
        />
        {natural && (
          <>
            <HeatmapOverlay
              diagnosedTileIds={visibleTileIds}
              onSelectTile={onSelectTile}
              selectedTileId={selectedTileId}
              tiles={tiles}
            />
            <ClusterMarkers centroids={centroids} gridSize={gridSize} />
          </>
        )}
        {children}
      </div>
    </div>
  )
}
