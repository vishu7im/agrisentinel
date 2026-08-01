import { useEffect, useRef, useState } from 'react'
import { openRunEvents } from '../api/client.js'
import { replayRecordedEvents } from '../lib/demoReplay.js'

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
    setStatus('connecting')

    const source = openRunEvents(runId, {
      onOpen() {
        setStatus('live')
      },
      onEvent(eventName) {
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
        if (!terminal) {
          replayCursor = 0
          setStatus('reconnecting')
        }
      },
    })

    return () => source.close()
  }, [recording, replayKey, runId])

  const events = snapshot.runId === runId && snapshot.replayKey === replayKey
    ? snapshot.events
    : []
  return { events, status }
}
