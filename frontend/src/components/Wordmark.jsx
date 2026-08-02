/**
 * The mark: an 8x5 tile grid, two cells lit emerald, one amber.
 *
 * Literally what the product does — a field cut into forty cells, most healthy, one flagged.
 * It replaces a purple lightning glyph left over from the project scaffold, which sat in the
 * browser tab through every screenshot and demo.
 *
 * Inline SVG rather than an icon package: the same geometry is redrawn on the canvas poster in
 * lib/farmerBriefImage.js, and a React component cannot be drawn to a canvas.
 */

// Cells the mark lights up, as [column, row] on the 8x5 grid it represents. Reduced to a 4x3
// mark for legibility at 16px — the shape reads, forty cells at that size do not.
const LIT = { amber: [[3, 1]], emerald: [[0, 0], [1, 2]] }

export default function Wordmark({ className = '', size = 36 }) {
  const cols = 4
  const rows = 3
  const gap = 1.5
  const cell = (24 - gap * (cols - 1)) / cols
  const cellH = (24 - gap * (rows - 1)) / rows

  const at = (x, y) => ({ x: x * (cell + gap), y: y * (cellH + gap) })

  return (
    <svg
      aria-hidden="true"
      className={className}
      height={size}
      role="presentation"
      viewBox="-4 -4 32 32"
      width={size}
    >
      <rect fill="#0d1410" height="32" rx="8" stroke="#243329" width="32" x="-4" y="-4" />
      {Array.from({ length: rows }, (_, y) =>
        Array.from({ length: cols }, (_, x) => {
          const lit = LIT.emerald.some(([lx, ly]) => lx === x && ly === y)
          const flagged = LIT.amber.some(([lx, ly]) => lx === x && ly === y)
          const { x: px, y: py } = at(x, y)
          return (
            <rect
              fill={flagged ? '#f59e0b' : lit ? '#4ade80' : '#243329'}
              height={cellH}
              key={`${x}-${y}`}
              rx="1"
              width={cell}
              x={px}
              y={py}
            />
          )
        }),
      )}
    </svg>
  )
}
