import { useCallback, useEffect, useRef, useState } from 'react'
import { getRun, startRun } from '../api/client.js'
import { DEMO_CASES, DEMO_CASE_SUMMARIES, DEMO_MODE } from '../lib/demoRuns.js'
import { useEventStream } from './useEventStream.js'

const DIAGNOSE_PREFIX = 'diagnose.tile.'

export function useRunScan() {
  const [phase, setPhase] = useState('idle')
  const [runId, setRunId] = useState(null)
  const [runState, setRunState] = useState(null)
  const [visibleTileIds, setVisibleTileIds] = useState([])
  const [error, setError] = useState(null)
  const [startedAt, setStartedAt] = useState(null)
  const [activeDemoCaseId, setActiveDemoCaseId] = useState(DEMO_CASES[0]?.id ?? null)
  const [demoReplayKey, setDemoReplayKey] = useState(0)
  const requestRef = useRef(0)
  const demoAutostartRef = useRef(false)
  const processedRef = useRef({ count: 0, replayKey: null, runId: null })
  const refreshTimerRef = useRef(null)
  const runStateRef = useRef(null)
  const activeDemoCase = DEMO_CASES.find((demoCase) => demoCase.id === activeDemoCaseId) ?? null
  const stream = useEventStream(runId, DEMO_MODE ? activeDemoCase : null, demoReplayKey)

  const clearRefresh = useCallback(() => {
    clearTimeout(refreshTimerRef.current)
  }, [])

  useEffect(() => clearRefresh, [clearRefresh])

  const refreshState = useCallback((revealAll = false) => {
    if (DEMO_MODE) {
      const currentState = runStateRef.current
      if (currentState) setRunState(currentState)
      if (revealAll && currentState) setVisibleTileIds(currentState.tiles.map((tile) => tile.id))
      return
    }

    clearTimeout(refreshTimerRef.current)
    refreshTimerRef.current = setTimeout(async () => {
      try {
        const nextState = await getRun(runId)
        if (runId !== processedRef.current.runId) return
        runStateRef.current = nextState
        setRunState(nextState)
        if (revealAll) setVisibleTileIds(nextState.tiles.map((tile) => tile.id))
      } catch {
        // The stream remains authoritative; a later event schedules another refresh.
      }
    }, 80)
  }, [runId])

  const startDemo = useCallback((caseId) => {
    const recording = DEMO_CASES.find((demoCase) => demoCase.id === caseId)
    if (!recording) return

    requestRef.current += 1
    clearRefresh()
    const nextState = structuredClone(recording.runState)
    setActiveDemoCaseId(recording.id)
    setDemoReplayKey((current) => current + 1)
    setPhase('scanning')
    setRunId(nextState.run_id)
    setRunState(nextState)
    runStateRef.current = nextState
    setVisibleTileIds([])
    setError(null)
    setStartedAt(Date.now())
  }, [clearRefresh])

  useEffect(() => {
    if (!DEMO_MODE || demoAutostartRef.current || !DEMO_CASES[0]) return
    demoAutostartRef.current = true
    startDemo(DEMO_CASES[0].id)
  }, [startDemo])

  useEffect(() => {
    if (!runId) return
    if (processedRef.current.runId !== runId || processedRef.current.replayKey !== demoReplayKey) {
      processedRef.current = { count: 0, replayKey: demoReplayKey, runId }
    }

    const pendingEvents = stream.events.slice(processedRef.current.count)
    pendingEvents.forEach((eventName) => {
      if (eventName === 'scout.done') {
        const skipped = (runStateRef.current?.tiles ?? [])
          .filter((tile) => tile.label.startsWith('skipped'))
          .map((tile) => tile.id)
        setVisibleTileIds((current) => [...new Set([...current, ...skipped])])
      }
      if (eventName.startsWith(DIAGNOSE_PREFIX)) {
        const tileId = eventName.slice(DIAGNOSE_PREFIX.length)
        setVisibleTileIds((current) => current.includes(tileId) ? current : [...current, tileId])
        refreshState()
      }
      if (eventName === 'diagnose.done') refreshState(true)
      if (eventName === 'spread.done') refreshState()
      if (eventName === 'verify.rewrite' || eventName === 'verify.block') refreshState()
      if (eventName === 'verify.pass') refreshState()
      if (eventName === 'planner.done' || eventName === 'reporter.done') refreshState()
      if (eventName === 'run.complete') {
        setPhase('complete')
        refreshState(true)
      }
      if (eventName === 'run.error') {
        setPhase('error')
        setError('The field analysis could not be completed.')
      }
    })
    processedRef.current.count = stream.events.length
  }, [demoReplayKey, refreshState, runId, stream.events])

  const start = useCallback(async (image) => {
    if (DEMO_MODE) {
      startDemo(activeDemoCaseId)
      return
    }

    const requestId = ++requestRef.current
    clearRefresh()
    setPhase('uploading')
    setRunId(null)
    setRunState(null)
    runStateRef.current = null
    setVisibleTileIds([])
    setError(null)
    setStartedAt(Date.now())

    try {
      const created = await startRun(image)
      if (requestId !== requestRef.current) return
      setRunId(created.run_id)
      setPhase('scanning')

      const initialState = await getRun(created.run_id)
      if (requestId !== requestRef.current) return
      runStateRef.current = initialState
      setRunState(initialState)
    } catch (caught) {
      if (requestId !== requestRef.current) return
      setPhase('error')
      setError(caught instanceof Error ? caught.message : 'Upload failed. Please try again.')
    }
  }, [activeDemoCaseId, clearRefresh, startDemo])

  return {
    currentEvent: stream.events.at(-1) ?? null,
    activeDemoCaseId,
    demoCases: DEMO_CASE_SUMMARIES,
    demoFileName: activeDemoCase?.file_name ?? '',
    demoMode: DEMO_MODE,
    demoPreviewUrl: activeDemoCase?.previewUrl ?? null,
    error,
    events: stream.events,
    phase,
    runId,
    runState,
    start,
    startDemo,
    startedAt,
    streamStatus: stream.status,
    visibleTileIds,
  }
}
