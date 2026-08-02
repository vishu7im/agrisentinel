const configuredBaseUrl = import.meta.env.VITE_API_URL?.replace(/\/+$/, '')

function apiUrl(path) {
  if (!configuredBaseUrl) {
    throw new Error('VITE_API_URL is missing. Copy .env.example to .env and restart Vite.')
  }
  return `${configuredBaseUrl}${path}`
}

async function request(path, options) {
  const response = await fetch(apiUrl(path), options)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // Keep the status-based message when the server did not return JSON.
    }
    throw new Error(message)
  }
  return response.json()
}

// 'auto' asks the backend to vote on the crop from the image itself. It is the default because
// the previous one — 'tomato' — was never overridden by anything, so every upload was scanned
// as tomato whatever it showed. The vote is unreliable on real photographs, which is why the
// upload screen offers an explicit choice: a crop the user picks is always obeyed.
export function startRun(image, crop = 'auto') {
  const body = new FormData()
  body.append('image', image)
  body.append('crop', crop)
  return request('/api/run', { method: 'POST', body })
}

export function getRun(runId) {
  return request(`/api/run/${encodeURIComponent(runId)}`)
}

export function openRunEvents(runId, handlers = {}) {
  const source = new EventSource(apiUrl(`/api/run/${encodeURIComponent(runId)}/events`))
  source.onopen = () => handlers.onOpen?.(source)
  source.onmessage = (event) => handlers.onEvent?.(event.data)
  source.onerror = (event) => handlers.onError?.(event, source)
  return source
}

export function getHealth() {
  return request('/api/health')
}

/**
 * One follow-up question about a finished run.
 *
 * Stateless on the server: the transcript lives here and is posted back each time, because
 * `run_state.schema.json` is frozen and there is nowhere legal in a run to keep a conversation.
 * Resolves to `{answer, sources, grounded, refused, provider}`. A refusal is a 200 with
 * `refused` set to a short token, not an error — the system deciding not to answer is an
 * outcome, the same argument the pipeline makes for a BLOCK completing rather than erroring.
 */
export function askAdvisor(runId, question, history = [], signal) {
  return request(`/api/run/${encodeURIComponent(runId)}/chat`, {
    body: JSON.stringify({ history: history.slice(-12), question }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
    signal,
  })
}

export function resolveRunAsset(path) {
  if (!path || /^(blob:|data:|https?:\/\/)/.test(path)) return path
  return apiUrl(path.startsWith('/') ? path : `/${path}`)
}
