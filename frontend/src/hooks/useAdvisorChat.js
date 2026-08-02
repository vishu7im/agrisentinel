import { useCallback, useEffect, useRef, useState } from 'react'
import { askAdvisor } from '../api/client.js'

/**
 * The transcript for one run, and the request in flight.
 *
 * The server keeps nothing — see `backend/app/chat.py` — so this is the conversation. It resets
 * whenever `runId` changes, because a question about the previous scan asked of the next one
 * would be answered confidently against the wrong field.
 */
export function useAdvisorChat(runId) {
  const [turns, setTurns] = useState([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)
  const runRef = useRef(runId)

  useEffect(() => {
    if (runRef.current === runId) return
    runRef.current = runId
    abortRef.current?.abort()
    setTurns([])
    setPending(false)
    setError(null)
  }, [runId])

  // A request still in flight when the panel unmounts would resolve into a dead component.
  useEffect(() => () => abortRef.current?.abort(), [])

  const send = useCallback(
    async (question) => {
      const text = String(question ?? '').trim()
      if (!text || !runId || pending) return

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      // The question is shown immediately and the history is captured before it is added, so
      // the model is never sent the question it is being asked twice.
      const history = turns.map(({ role, text: turnText }) => ({ role, text: turnText }))
      setTurns((current) => [...current, { id: `q-${current.length}`, role: 'user', text }])
      setPending(true)
      setError(null)

      try {
        const result = await askAdvisor(runId, text, history, controller.signal)
        setTurns((current) => [
          ...current,
          {
            grounded: result.grounded,
            id: `a-${current.length}`,
            refused: result.refused,
            role: 'advisor',
            sources: result.sources ?? [],
            text: result.answer,
          },
        ])
      } catch (caught) {
        if (caught.name === 'AbortError') return
        // The question stays on screen with the failure under it, so retrying is retyping
        // nothing — and a backend that is simply down reads as down rather than as a refusal.
        setError(caught instanceof Error ? caught.message : 'The advisor could not be reached.')
      } finally {
        if (abortRef.current === controller) setPending(false)
      }
    },
    [pending, runId, turns],
  )

  const retry = useCallback(() => {
    const last = [...turns].reverse().find((turn) => turn.role === 'user')
    if (!last) return
    setTurns((current) => current.slice(0, current.lastIndexOf(last)))
    send(last.text)
  }, [send, turns])

  return { error, pending, retry, send, turns }
}
