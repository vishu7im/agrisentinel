import { useEffect, useRef, useState } from 'react'
import { openRunEvents } from '../api/client.js'

export function useEventStream(runId) {
  const [snapshot, setSnapshot] = useState({ runId: null, events: [] })
  const [status, setStatus] = useState('idle')
  const eventsRef = useRef([])

  useEffect(() => {
    eventsRef.current = []
    setSnapshot({ runId, events: [] })
    if (!runId) {
      setStatus('idle')
      return undefined
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
        setSnapshot({ runId, events })

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
  }, [runId])

  const events = snapshot.runId === runId ? snapshot.events : []
  return { events, status }
}
