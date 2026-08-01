import { useEffect, useRef, useState } from 'react'
import ActivityPanel from './components/ActivityPanel.jsx'
import FieldPanel from './components/FieldPanel.jsx'
import PlanPlaceholder from './components/PlanPlaceholder.jsx'
import { useRunScan } from './hooks/useRunScan.js'

export default function App() {
  const [previewUrl, setPreviewUrl] = useState(null)
  const [fileName, setFileName] = useState('')
  const previewRef = useRef(null)
  const scan = useRunScan()

  useEffect(
    () => () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    },
    [],
  )

  function handleImage(file) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    const nextPreview = URL.createObjectURL(file)
    previewRef.current = nextPreview
    setPreviewUrl(nextPreview)
    setFileName(file.name)
    scan.start(file)
  }

  return (
    <main className="min-h-screen bg-field-bg">
      <header className="border-b border-field-border bg-field-panel/80 px-5 py-4 backdrop-blur sm:px-8">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl border border-emerald-400/30 bg-emerald-400/10 text-xl">
              ◈
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-white sm:text-2xl">
                AgriSentinel
              </h1>
              <p className="text-xs uppercase tracking-[0.18em] text-emerald-300/70">
                Autonomous field health
              </p>
            </div>
          </div>
          <div className="hidden items-center gap-2 text-sm text-slate-400 sm:flex">
            <span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_12px_#4ade80]" />
            Analysis console online
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] gap-5 p-5 sm:p-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <FieldPanel
          error={scan.error}
          fileName={fileName}
          onImage={handleImage}
          phase={scan.phase}
          previewUrl={previewUrl}
          runState={scan.runState}
          visibleTileIds={scan.visibleTileIds}
        />
        <ActivityPanel
          currentEvent={scan.currentEvent}
          phase={scan.phase}
          runId={scan.runId}
          tileCount={scan.runState?.tiles?.length ?? 0}
          visibleCount={scan.visibleTileIds.length}
        />
        <PlanPlaceholder phase={scan.phase} />
      </div>
    </main>
  )
}
