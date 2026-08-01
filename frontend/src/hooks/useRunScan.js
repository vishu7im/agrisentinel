import { useCallback, useEffect, useRef, useState } from 'react'
import { getRun, startRun } from '../api/client.js'
import { useEventStream } from './useEventStream.js'

const DIAGNOSE_PREFIX = 'diagnose.tile.'

export function useRunScan() {
  const [phase, setPhase] = useState('idle')
  const [runId, setRunId] = useState(null)
  const [runState, setRunState] = useState(null)
  const [visibleTileIds, setVisibleTileIds] = useState([])
  const [error, setError] = useState(null)
  const [startedAt, setStartedAt] = useState(null)
  const requestRef = useRef(0)
  const processedRef = useRef({ runId: null, count: 0 })
  const refreshTimerRef = useRef(null)
  const runStateRef = useRef(null)
  const stream = useEventStream(runId)

  const clearRefresh = useCallback(() => {
    clearTimeout(refreshTimerRef.current)
  }, [])

  useEffect(() => clearRefresh, [clearRefresh])

  const refreshState = useCallback((revealAll = false) => {
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

  useEffect(() => {
    if (!runId) return
    if (processedRef.current.runId !== runId) {
      processedRef.current = { runId, count: 0 }
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
      if (eventName === 'verify.pass') refreshState()
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
  }, [refreshState, runId, stream.events])

  const start = useCallback(async (image) => {
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
  }, [clearRefresh])

  return {
    currentEvent: stream.events.at(-1) ?? null,
    error,
    events: stream.events,
    phase,
    runId,
    runState,
    start,
    startedAt,
    streamStatus: stream.status,
    visibleTileIds,
  }
}
