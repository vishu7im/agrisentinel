export function replayRecordedEvents(events, { intervalMs, onEvent, onStatus }) {
  let cursor = 0
  let timer = null
  let stopped = false

  onStatus('live')

  function emitNext() {
    if (stopped || cursor >= events.length) return

    const eventName = events[cursor]
    cursor += 1
    onEvent(eventName)

    if (eventName === 'run.complete' || eventName === 'run.error') {
      onStatus(eventName === 'run.complete' ? 'complete' : 'error')
      return
    }

    timer = setTimeout(emitNext, intervalMs)
  }

  timer = setTimeout(emitNext, intervalMs)

  return () => {
    stopped = true
    clearTimeout(timer)
  }
}
