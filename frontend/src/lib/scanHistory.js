const STORAGE_KEY = 'agrisentinel.completed-scans.v1'
const HISTORY_LIMIT = 8

function finiteNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function sanitiseSpread(spread) {
  if (!spread || typeof spread !== 'object') return null

  const pctAffected = finiteNumber(spread.pct_affected)
  const clusters = finiteNumber(spread.clusters)
  const yieldLoss = finiteNumber(spread.est_yield_loss_pct)
  if (pctAffected === null || clusters === null || yieldLoss === null) return null

  return {
    clusters: Math.max(0, Math.round(clusters)),
    direction: typeof spread.direction === 'string' ? spread.direction : null,
    est_yield_loss_pct: Math.max(0, yieldLoss),
    pct_affected: Math.min(100, Math.max(0, pctAffected)),
  }
}

function sanitiseSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return null
  const spread = sanitiseSpread(snapshot.spread)
  if (!spread || typeof snapshot.run_id !== 'string' || !snapshot.run_id) return null

  return {
    crop: typeof snapshot.crop === 'string' ? snapshot.crop : null,
    file_name: typeof snapshot.file_name === 'string' ? snapshot.file_name : '',
    recorded_at: typeof snapshot.recorded_at === 'string' ? snapshot.recorded_at : null,
    run_id: snapshot.run_id,
    source: 'device',
    spread,
  }
}

export function createScanSnapshot({ crop, fileName, recordedAt, runId, spread }) {
  return sanitiseSnapshot({
    crop,
    file_name: fileName,
    recorded_at: recordedAt,
    run_id: runId,
    spread,
  })
}

export function readScanHistory(storage = globalThis.localStorage) {
  try {
    const parsed = JSON.parse(storage.getItem(STORAGE_KEY) ?? '[]')
    if (!Array.isArray(parsed)) return []
    return parsed.map(sanitiseSnapshot).filter(Boolean).slice(0, HISTORY_LIMIT)
  } catch {
    return []
  }
}

export function findPreviousScan(history, runId) {
  return history.find((snapshot) => snapshot.run_id !== runId) ?? null
}

export function storeCompletedScan(snapshot, storage = globalThis.localStorage) {
  if (!snapshot) return false

  try {
    const history = readScanHistory(storage)
    const nextHistory = [snapshot, ...history.filter((item) => item.run_id !== snapshot.run_id)]
      .slice(0, HISTORY_LIMIT)
    storage.setItem(STORAGE_KEY, JSON.stringify(nextHistory))
    return true
  } catch {
    return false
  }
}
