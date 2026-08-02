/**
 * The header status light, telling the truth.
 *
 * `streamStatus` takes priority over backend health while a scan is in flight, because during
 * those seconds "is my scan still arriving" is the only question anyone is asking.
 */

const HEALTH = {
  checking: { dot: 'bg-slate-500', label: 'Connecting…' },
  offline: { dot: 'bg-red-400 shadow-[0_0_12px_#f87171]', label: 'Backend offline' },
  online: { dot: 'bg-emerald-400 shadow-[0_0_12px_#4ade80]', label: 'Analysis console online' },
  replay: { dot: 'bg-amber-300 shadow-[0_0_12px_#fcd34d]', label: 'Offline replay' },
}

const STREAM = {
  dropped: { dot: 'bg-amber-300 animate-pulse', label: 'Stream lost — polling' },
  reconnecting: { dot: 'bg-amber-300 animate-pulse', label: 'Reconnecting…' },
  stalled: { dot: 'bg-amber-300 animate-pulse', label: 'Stream quiet — polling' },
}

export default function StatusChip({ health, streamStatus }) {
  const state = STREAM[streamStatus] ?? HEALTH[health] ?? HEALTH.checking

  return (
    <div
      aria-live="polite"
      className="flex min-h-10 shrink-0 items-center gap-2 rounded-full border border-field-border bg-black/20 px-3 text-[11px] font-semibold text-slate-200 sm:border-0 sm:bg-transparent sm:px-0 sm:text-sm sm:font-normal sm:text-slate-400"
    >
      <span className={`size-2 shrink-0 rounded-full ${state.dot}`} />
      <span className="truncate">{state.label}</span>
    </div>
  )
}
