import { useEffect } from 'react'

export default function SourceDrawer({ onClose, source, sourceNumber }) {
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50" role="presentation">
      <button
        aria-label="Close source details"
        className="absolute inset-0 cursor-default bg-black/65 backdrop-blur-sm"
        onClick={onClose}
        type="button"
      />
      <aside
        aria-labelledby="source-title"
        aria-modal="true"
        className="drawer-enter absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-field-border bg-field-panel p-6 shadow-2xl shadow-black/60"
        role="dialog"
      >
        <div className="flex items-start justify-between gap-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Source {sourceNumber}</p>
            <h2 className="mt-2 text-xl font-semibold leading-7 text-white" id="source-title">{source.doc}</h2>
          </div>
          <button
            autoFocus
            className="grid size-10 shrink-0 place-items-center rounded-full border border-field-border text-xl text-slate-400 transition hover:border-slate-500 hover:text-white"
            onClick={onClose}
            type="button"
          >
            <span aria-hidden="true">×</span>
            <span className="sr-only">Close source details</span>
          </button>
        </div>

        <div className="mt-5 flex items-center gap-2 text-xs font-medium text-slate-400">
          <span className="rounded-full border border-field-border bg-black/20 px-2.5 py-1">Page {source.page}</span>
          <span className="font-mono text-slate-600">{source.id}</span>
        </div>

        <div className="mt-6 overflow-y-auto rounded-xl border border-field-border bg-black/20 p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Retrieved evidence</p>
          <blockquote className="mt-4 border-l-2 border-emerald-400/50 pl-4 text-base leading-7 text-slate-200">
            {source.text}
          </blockquote>
        </div>
      </aside>
    </div>
  )
}
