import { useEffect, useRef, useState } from 'react'
import ActivityPanel from './components/ActivityPanel.jsx'
import FieldPanel from './components/FieldPanel.jsx'
import PlanPanel from './components/PlanPanel.jsx'
import { useRunScan } from './hooks/useRunScan.js'

export default function App() {
  const [previewUrl, setPreviewUrl] = useState(null)
  const [fileName, setFileName] = useState('')
  const previewRef = useRef(null)
  const scan = useRunScan()
  const hasPass = scan.events.includes('verify.pass')
  const hasBlock = scan.events.includes('verify.block')
  const hasRewrite = scan.events.includes('verify.rewrite')
  const verdictReady = hasPass || hasBlock || hasRewrite || scan.phase === 'complete'
  const verification = verdictReady ? scan.runState?.verification : null
  const visibleVerification = hasRewrite && !hasPass && !hasBlock && verification
    ? { ...verification, status: 'REWRITE' }
    : verification

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
          spread={scan.events.includes('spread.done') ? scan.runState?.spread : null}
          visibleTileIds={scan.visibleTileIds}
        />
        <ActivityPanel
          events={scan.events}
          phase={scan.phase}
          runId={scan.runId}
          startedAt={scan.startedAt}
          streamStatus={scan.streamStatus}
          tileCount={scan.runState?.tiles?.length ?? 0}
        />
        <PlanPanel
          key={scan.runId ?? 'empty-plan'}
          diagnosisSummary={scan.runState?.report?.en}
          phase={scan.phase}
          plan={verdictReady ? scan.runState?.plan_draft : null}
          verification={visibleVerification}
        />
      </div>
    </main>
  )
}
