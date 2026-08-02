import { useEffect, useState } from 'react'
import { getHealth } from '../api/client.js'

/**
 * Whether the backend is actually up.
 *
 * The header used to read "Analysis console online" as a hardcoded string, while `getHealth()`
 * sat exported and never called. A status light that is always green is worse than no status
 * light: it is the one element on screen a viewer trusts without checking, and during a demo it
 * is exactly what they will look at when something stops working.
 */

const POLL_MS = 20_000

export function useBackendHealth(paused = false) {
  const [status, setStatus] = useState('checking')

  useEffect(() => {
    if (paused) {
      setStatus('replay')
      return undefined
    }

    let cancelled = false

    async function probe() {
      // Skipped while the tab is hidden — a laptop left open on this page overnight should not
      // spend the night talking to a backend nobody is watching.
      if (document.hidden) return
      try {
        await getHealth()
        if (!cancelled) setStatus('online')
      } catch {
        // apiUrl() throws outright when VITE_API_URL is unset, so this covers configuration
        // errors as well as a backend that is down. Both mean the same thing to a viewer.
        if (!cancelled) setStatus('offline')
      }
    }

    probe()
    const timer = setInterval(probe, POLL_MS)
    document.addEventListener('visibilitychange', probe)
    return () => {
      cancelled = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', probe)
    }
  }, [paused])

  return status
}
