import { useEffect, useState } from 'react'
import {
  createScanSnapshot,
  findPreviousScan,
  readScanHistory,
  storeCompletedScan,
} from '../lib/scanHistory.js'

export function useScanHistory({ crop, enabled, fileName, phase, runId, spread, verificationStatus }) {
  const [previousScan, setPreviousScan] = useState(null)

  useEffect(() => {
    if (!enabled) {
      setPreviousScan(null)
      return
    }
    if (!runId) return

    setPreviousScan(findPreviousScan(readScanHistory(), runId))
  }, [enabled, runId])

  useEffect(() => {
    if (!enabled || phase !== 'complete' || verificationStatus !== 'PASS') return

    const history = readScanHistory()
    const existing = history.find((snapshot) => snapshot.run_id === runId)
    const snapshot = createScanSnapshot({
      crop,
      fileName,
      recordedAt: existing?.recorded_at ?? new Date().toISOString(),
      runId,
      spread,
    })
    if (!snapshot) return

    setPreviousScan(findPreviousScan(history, runId))
    storeCompletedScan(snapshot)
  }, [crop, enabled, fileName, phase, runId, spread, verificationStatus])

  return previousScan
}
