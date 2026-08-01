import { useCallback, useRef, useState } from 'react'
import { startRun } from '../api/client.js'

export function useRunUpload() {
  const [phase, setPhase] = useState('idle')
  const [runId, setRunId] = useState(null)
  const [error, setError] = useState(null)
  const requestRef = useRef(0)

  const start = useCallback(async (image) => {
    const requestId = ++requestRef.current
    setPhase('uploading')
    setRunId(null)
    setError(null)

    try {
      const created = await startRun(image)
      if (requestId !== requestRef.current) return
      setRunId(created.run_id)
      setPhase('scanning')
    } catch (caught) {
      if (requestId !== requestRef.current) return
      setPhase('error')
      setError(caught instanceof Error ? caught.message : 'Upload failed. Please try again.')
    }
  }, [])

  return { error, phase, runId, start }
}
