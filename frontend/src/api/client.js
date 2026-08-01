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

export function startRun(image, crop = 'tomato') {
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
  source.onmessage = (event) => handlers.onEvent?.(event.data)
  source.onerror = (event) => handlers.onError?.(event, source)
  return source
}

export function getHealth() {
  return request('/api/health')
}

export function resolveRunAsset(path) {
  if (!path || /^(blob:|data:|https?:\/\/)/.test(path)) return path
  return apiUrl(path.startsWith('/') ? path : `/${path}`)
}
