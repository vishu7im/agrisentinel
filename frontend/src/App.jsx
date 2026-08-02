import { useEffect, useMemo, useRef, useState } from 'react'
import ActionPanel from './components/ActionPanel.jsx'
import ActivityPanel from './components/ActivityPanel.jsx'
import ConsensusPanel from './components/ConsensusPanel.jsx'
import DemoControls from './components/DemoControls.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import FieldPanel from './components/FieldPanel.jsx'
import LandingHero from './components/LandingHero.jsx'
import MobileFieldNav from './components/MobileFieldNav.jsx'
import PipelineSpine from './components/PipelineSpine.jsx'
import PlanPanel from './components/PlanPanel.jsx'
import RunErrorCard from './components/RunErrorCard.jsx'
import StatusChip from './components/StatusChip.jsx'
import Wordmark from './components/Wordmark.jsx'
import { useBackendHealth } from './hooks/useBackendHealth.js'
import { useRunScan } from './hooks/useRunScan.js'
import { useScanHistory } from './hooks/useScanHistory.js'
import { cropWasGuessed, deriveConsensus } from './lib/consensus.js'

export default function App() {
  const [previewUrl, setPreviewUrl] = useState(null)
  const [fileName, setFileName] = useState('')
  const [crop, setCrop] = useState('auto')
  const previewRef = useRef(null)
  const lastFileRef = useRef(null)
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
  const health = useBackendHealth(scan.demoMode)
  const consensus = useMemo(
    () => deriveConsensus(scan.events, scan.runState),
    [scan.events, scan.runState],
  )
  const storedPreviousScan = useScanHistory({
    crop: scan.runState?.crop,
    enabled: !scan.demoMode,
    fileName: visibleFileName,
    phase: scan.phase,
    runId: scan.runId,
    spread: scan.runState?.spread,
    verificationStatus: scan.runState?.verification?.status,
  })
  const previousScan = scan.demoMode ? scan.demoPreviousScan : storedPreviousScan
  // The cold-open screen: nothing uploaded and no run in flight. A replay counts as a run, so
  // clicking a sample scan leaves the hero immediately.
  const landing = scan.phase === 'idle' && !visiblePreviewUrl && !scan.runId

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

  // Re-run the held image under a crop the user just corrected. The file is already kept for
  // the retry path, so nothing has to be asked for twice — and the crop is what masks the
  // classifier's logits, so this is a genuinely different scan rather than a relabel.
  function handleRecrop(nextCrop) {
    if (!lastFileRef.current) return
    setCrop(nextCrop)
    scan.start(lastFileRef.current, nextCrop)
  }

  function handleImage(file, nextCrop) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    const nextPreview = URL.createObjectURL(file)
    previewRef.current = nextPreview
    // Held so a failed run can be retried without asking for the file a second time.
    lastFileRef.current = file
    if (nextCrop) setCrop(nextCrop)
    setPreviewUrl(nextPreview)
    setFileName(file.name)
    scan.start(file, nextCrop ?? crop)
  }

  return (
    <main className="min-h-dvh bg-field-bg pb-24 lg:pb-0">
      <header className="app-header sticky top-0 z-40 border-b border-field-border bg-field-panel/90 backdrop-blur lg:static">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
            <Wordmark className="shrink-0" size={38} />
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold tracking-tight text-white sm:text-2xl">
                AgriSentinel
              </h1>
              <p className="truncate text-[9px] uppercase tracking-[0.14em] text-emerald-300/70 sm:text-xs sm:tracking-[0.18em]">
                Autonomous field health
              </p>
            </div>
          </div>
          <StatusChip health={health} streamStatus={scanActive ? scan.streamStatus : null} />
        </div>
      </header>

      {demoMode && (
        <DemoControls
          activeCaseId={scan.activeDemoCaseId}
          cases={demoCases}
          onSelect={startDemo}
        />
      )}

      {!landing && <PipelineSpine events={scan.events} runState={scan.runState} />}

      {landing ? (
        <div className="app-content mx-auto max-w-[1600px]">
          <LandingHero
            demoCases={demoCases}
            error={scan.error}
            onImage={handleImage}
            onStartDemo={startDemo}
          />
        </div>
      ) : (
        <div className="app-content mx-auto grid max-w-[1600px] gap-4 py-4 sm:gap-5 sm:py-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <ErrorBoundary label="The field scan">
            <FieldPanel
              crop={crop}
              // The flat red paragraph is gone; failures render as RunErrorCard below, which
              // has somewhere to go next.
              error={null}
              fileName={visibleFileName}
              onImage={handleImage}
              phase={scan.phase}
              previewUrl={visiblePreviewUrl}
              previousScan={previousScan}
              relabel={consensus.relabel}
              runState={scan.runState}
              spread={scan.events.includes('spread.done') ? scan.runState?.spread : null}
              spreadLoading={scanActive && !scan.events.includes('spread.done')}
              visibleTileIds={scan.visibleTileIds}
            />
          </ErrorBoundary>
          <ActivityPanel
            events={scan.events}
            phase={scan.phase}
            runId={scan.runId}
            startedAt={scan.startedAt}
            streamStatus={scan.streamStatus}
            tileCount={scan.runState?.tiles?.length ?? 0}
          />

          {scan.error && (
            <div className="order-1 lg:col-span-2">
              <RunErrorCard
                demoCases={demoCases}
                message={scan.error}
                onRetry={lastFileRef.current ? () => scan.start(lastFileRef.current, crop) : null}
                onStartDemo={startDemo}
                runId={scan.runId}
              />
            </div>
          )}

          <ErrorBoundary label="The cross-check">
            <ConsensusPanel consensus={consensus} phase={scan.phase} />
          </ErrorBoundary>

          <ErrorBoundary label="The treatment plan">
            <PlanPanel
              key={scan.runId ?? 'empty-plan'}
              diagnosisSummary={scan.runState?.report?.en}
              phase={scan.phase}
              loading={scanActive && !verdictReady}
              plan={verdictReady ? scan.runState?.plan_draft : null}
              verification={visibleVerification}
            />
          </ErrorBoundary>
          <ErrorBoundary label="The action plan">
            <ActionPanel
              key={scan.runId ?? 'empty-actions'}
              costEstimate={scheduleReady ? scan.runState?.cost_estimate : null}
              blocked={hasBlock}
              crop={scan.runState?.crop}
              cropGuessed={!scan.replaying && cropWasGuessed(scan.events)}
              crossCheck={consensus.state}
              disease={consensus.relabel?.to ?? consensus.cnn?.disease ?? null}
              fieldName={visibleFileName}
              onRecrop={lastFileRef.current ? handleRecrop : null}
              phase={scan.phase}
              replaying={scan.replaying}
              report={reportReady ? scan.runState?.report : null}
              reportLoading={scanActive && !reportReady}
              rescanDate={scheduleReady ? scan.runState?.rescan_date : null}
              runId={scan.runId}
              schedule={scheduleReady ? scan.runState?.schedule : null}
              scheduleLoading={scanActive && !scheduleReady && !hasBlock}
            />
          </ErrorBoundary>
        </div>
      )}
      <MobileFieldNav phase={scan.phase} />
    </main>
  )
}
