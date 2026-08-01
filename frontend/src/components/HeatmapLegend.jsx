const items = [
  { label: 'Healthy', swatch: 'bg-tile-healthy' },
  { label: 'Disease detected', swatch: 'bg-tile-diseased' },
  { label: 'Skipped / no crop', swatch: 'bg-tile-skipped' },
]

export default function HeatmapLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-400">
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
      <span className="ml-auto text-slate-500">Opacity indicates confidence</span>
    </div>
  )
}
