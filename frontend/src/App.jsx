import { useEffect, useRef, useState } from 'react'
import ActionPanel from './components/ActionPanel.jsx'
import ActivityPanel from './components/ActivityPanel.jsx'
import DemoControls from './components/DemoControls.jsx'
import FieldPanel from './components/FieldPanel.jsx'
import MobileFieldNav from './components/MobileFieldNav.jsx'
import PlanPanel from './components/PlanPanel.jsx'
import { useRunScan } from './hooks/useRunScan.js'

const MOBILE_STATUS = {
  complete: 'Result ready',
  error: 'Needs attention',
  idle: 'Ready to scan',
  scanning: 'Scanning',
  uploading: 'Uploading',
}

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
  const scheduleReady = scan.events.includes('planner.done') || scan.phase === 'complete'
  const reportReady = scan.events.includes('reporter.done') || scan.phase === 'complete'
  const scanActive = scan.phase === 'uploading' || scan.phase === 'scanning'
  const { demoCases, demoMode, startDemo } = scan
  const visiblePreviewUrl = scan.demoMode ? scan.demoPreviewUrl : previewUrl
  const visibleFileName = scan.demoMode ? scan.demoFileName : fileName

  useEffect(
    () => () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    },
    [],
  )

  useEffect(() => {
    if (!demoMode) return undefined

    function selectDemoCase(event) {
      if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
      const target = event.target
      if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]')) return
      const demoCase = demoCases.find((item) => item.shortcut === event.key)
      if (demoCase) startDemo(demoCase.id)
    }

    window.addEventListener('keydown', selectDemoCase)
    return () => window.removeEventListener('keydown', selectDemoCase)
  }, [demoCases, demoMode, startDemo])

  function handleImage(file) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    const nextPreview = URL.createObjectURL(file)
    previewRef.current = nextPreview
    setPreviewUrl(nextPreview)
    setFileName(file.name)
    scan.start(file)
  }

  return (
    <main className="min-h-dvh bg-field-bg pb-24 lg:pb-0">
      <header className="app-header sticky top-0 z-40 border-b border-field-border bg-field-panel/90 backdrop-blur lg:static">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
            <div className="grid size-9 shrink-0 place-items-center rounded-xl border border-emerald-400/30 bg-emerald-400/10 text-lg sm:size-10 sm:text-xl">
              ◈
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold tracking-tight text-white sm:text-2xl">
                AgriSentinel
              </h1>
              <p className="truncate text-[9px] uppercase tracking-[0.14em] text-emerald-300/70 sm:text-xs sm:tracking-[0.18em]">
                Autonomous field health
              </p>
            </div>
          </div>
          <div
            aria-live="polite"
            className="flex min-h-10 shrink-0 items-center gap-2 rounded-full border border-field-border bg-black/20 px-3 text-[11px] font-semibold text-slate-200 sm:hidden"
          >
            <span className={`size-2 rounded-full ${scan.phase === 'error' ? 'bg-red-400' : scanActive ? 'animate-pulse bg-cyan-300' : scan.phase === 'complete' ? 'bg-emerald-400' : 'bg-slate-500'}`} />
            {MOBILE_STATUS[scan.phase] ?? 'Ready'}
          </div>
          <div className="hidden items-center gap-2 text-sm text-slate-400 sm:flex">
            <span className={`size-2 rounded-full ${demoMode ? 'bg-amber-300 shadow-[0_0_12px_#fcd34d]' : 'bg-emerald-400 shadow-[0_0_12px_#4ade80]'}`} />
            {demoMode ? 'Offline replay ready' : 'Analysis console online'}
          </div>
        </div>
      </header>

      {demoMode && (
        <DemoControls
          activeCaseId={scan.activeDemoCaseId}
          cases={demoCases}
          onSelect={startDemo}
        />
      )}

      <div className="app-content mx-auto grid max-w-[1600px] gap-4 py-4 sm:gap-5 sm:py-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <FieldPanel
          error={scan.error}
          fileName={visibleFileName}
          onImage={handleImage}
          phase={scan.phase}
          previewUrl={visiblePreviewUrl}
          runState={scan.runState}
          spread={scan.events.includes('spread.done') ? scan.runState?.spread : null}
          spreadLoading={scanActive && !scan.events.includes('spread.done')}
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
          loading={scanActive && !verdictReady}
          plan={verdictReady ? scan.runState?.plan_draft : null}
          verification={visibleVerification}
        />
        <ActionPanel
          key={scan.runId ?? 'empty-actions'}
          costEstimate={scheduleReady ? scan.runState?.cost_estimate : null}
          blocked={hasBlock}
          phase={scan.phase}
          report={reportReady ? scan.runState?.report : null}
          reportLoading={scanActive && !reportReady}
          rescanDate={scheduleReady ? scan.runState?.rescan_date : null}
          schedule={scheduleReady ? scan.runState?.schedule : null}
          scheduleLoading={scanActive && !scheduleReady && !hasBlock}
        />
      </div>
      <MobileFieldNav phase={scan.phase} />
    </main>
  )
}
