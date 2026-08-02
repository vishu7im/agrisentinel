import { useEffect, useRef, useState } from 'react'
import { openRunEvents } from '../api/client.js'
import { replayRecordedEvents } from '../lib/demoReplay.js'

// How long the stream may go quiet before the UI says so. The whole pipeline is about a second
// offline, and the one legitimately slow stage is the vision cross-check at up to 25 s — so this
// sits above that. Under it, a normal run would report itself stalled every single time.
const STALL_MS = 30_000

// EventSource reconnects for ever by default. On a venue network that turns a dead backend into
// a spinner that never resolves, so the retries are counted and the stream is given up on. The
// hook reports `dropped` and useRunScan falls back to polling GET /api/run/{id}, which the
// contract says always returns the completed run.
const MAX_RECONNECTS = 5

export function useEventStream(runId, recording = null, replayKey = 0) {
  const [snapshot, setSnapshot] = useState({ replayKey: null, runId: null, events: [] })
  const [status, setStatus] = useState('idle')
  const eventsRef = useRef([])

  useEffect(() => {
    eventsRef.current = []
    setSnapshot({ replayKey, runId, events: [] })
    if (!runId) {
      setStatus('idle')
      return undefined
    }

    if (recording) {
      setStatus('connecting')
      return replayRecordedEvents(recording.events, {
        intervalMs: recording.event_interval_ms,
        onEvent(eventName) {
          const events = [...eventsRef.current, eventName]
          eventsRef.current = events
          setSnapshot({ replayKey, runId, events })
        },
        onStatus: setStatus,
      })
    }

    let replayCursor = null
    let terminal = false
    let reconnects = 0
    let lastEventAt = Date.now()
    setStatus('connecting')

    const stallTimer = setInterval(() => {
      if (terminal) return
      if (Date.now() - lastEventAt > STALL_MS) setStatus('stalled')
    }, 2000)

    const source = openRunEvents(runId, {
      onOpen() {
        lastEventAt = Date.now()
        setStatus('live')
      },
      onEvent(eventName) {
        lastEventAt = Date.now()
        if (replayCursor !== null && eventsRef.current[replayCursor] === eventName) {
          replayCursor += 1
          return
        }

        replayCursor = null
        const events = [...eventsRef.current, eventName]
        eventsRef.current = events
        setSnapshot({ replayKey, runId, events })

        if (eventName === 'run.complete' || eventName === 'run.error') {
          terminal = true
          setStatus(eventName === 'run.complete' ? 'complete' : 'error')
          source.close()
        }
      },
      onError() {
        if (terminal) return
        reconnects += 1
        if (reconnects > MAX_RECONNECTS) {
          setStatus('dropped')
          source.close()
          return
        }
        replayCursor = 0
        setStatus('reconnecting')
      },
    })

    return () => {
      clearInterval(stallTimer)
      source.close()
    }
  }, [recording, replayKey, runId])

  const events = snapshot.runId === runId && snapshot.replayKey === replayKey
    ? snapshot.events
    : []
  return { events, status }
}
