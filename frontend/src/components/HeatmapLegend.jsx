const items = [
  { label: 'Healthy', swatch: 'bg-tile-healthy' },
  { label: 'Disease detected', swatch: 'bg-tile-diseased' },
  { label: 'Skipped / no crop', swatch: 'bg-tile-skipped' },
]

export default function HeatmapLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-slate-400 sm:gap-x-5 sm:text-xs">
      {items.map((item) => (
        <span className="flex items-center gap-2" key={item.label}>
          <span className={`size-3 rounded-sm ${item.swatch}`} />
          {item.label}
        </span>
      ))}
      <span className="flex items-center gap-2">
        <span className="size-3 rounded-sm border border-dashed border-white" />
        Second opinion
      </span>
      <span className="w-full text-slate-500 sm:ml-auto sm:w-auto">Tap a tile for detail · opacity shows confidence</span>
    </div>
  )
}
