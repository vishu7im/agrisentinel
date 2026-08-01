import { useCallback, useEffect, useRef, useState } from 'react'
import { getRun, openRunEvents, startRun } from '../api/client.js'

const DIAGNOSE_PREFIX = 'diagnose.tile.'

export function useRunScan() {
  const [phase, setPhase] = useState('idle')
  const [runId, setRunId] = useState(null)
  const [runState, setRunState] = useState(null)
  const [visibleTileIds, setVisibleTileIds] = useState([])
  const [currentEvent, setCurrentEvent] = useState(null)
  const [error, setError] = useState(null)
  const sourceRef = useRef(null)
  const requestRef = useRef(0)
  const refreshTimerRef = useRef(null)

  const closeStream = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
    clearTimeout(refreshTimerRef.current)
  }, [])

  useEffect(() => closeStream, [closeStream])

  const start = useCallback(async (image) => {
    const requestId = ++requestRef.current
    closeStream()
    setPhase('uploading')
    setRunId(null)
    setRunState(null)
    setVisibleTileIds([])
    setCurrentEvent(null)
    setError(null)

    try {
      const created = await startRun(image)
      if (requestId !== requestRef.current) return
      setRunId(created.run_id)
      setPhase('scanning')

      const initialState = await getRun(created.run_id)
      if (requestId !== requestRef.current) return
      setRunState(initialState)

      let terminal = false
      const refreshState = (revealAll = false) => {
        clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = setTimeout(async () => {
          try {
            const nextState = await getRun(created.run_id)
            if (requestId !== requestRef.current) return
            setRunState(nextState)
            if (revealAll) setVisibleTileIds(nextState.tiles.map((tile) => tile.id))
          } catch {
            // SSE remains authoritative; a later event will schedule another refresh.
          }
        }, 80)
      }

      sourceRef.current = openRunEvents(created.run_id, {
        onEvent(eventName) {
          if (requestId !== requestRef.current) return
          setCurrentEvent(eventName)
          if (eventName === 'scout.done') {
            const skipped = initialState.tiles
              .filter((tile) => tile.label.startsWith('skipped'))
              .map((tile) => tile.id)
            setVisibleTileIds(skipped)
          }
          if (eventName.startsWith(DIAGNOSE_PREFIX)) {
            const tileId = eventName.slice(DIAGNOSE_PREFIX.length)
            setVisibleTileIds((current) =>
              current.includes(tileId) ? current : [...current, tileId],
            )
            refreshState()
          }
          if (eventName === 'diagnose.done') refreshState(true)
          if (eventName === 'run.complete') {
            terminal = true
            setPhase('complete')
            refreshState(true)
            sourceRef.current?.close()
            sourceRef.current = null
          }
          if (eventName === 'run.error') {
            terminal = true
            setPhase('error')
            setError('The field analysis could not be completed.')
            sourceRef.current?.close()
            sourceRef.current = null
          }
        },
        onError(_event, source) {
          if (!terminal && source.readyState === EventSource.CLOSED) {
            setPhase('error')
            setError('The live analysis stream disconnected. Drop the image to retry.')
          }
        },
      })
    } catch (caught) {
      if (requestId !== requestRef.current) return
      setPhase('error')
      setError(caught instanceof Error ? caught.message : 'Upload failed. Please try again.')
    }
  }, [closeStream])

  return { currentEvent, error, phase, runId, runState, start, visibleTileIds }
}
