import { readdir, readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { deriveConsensus } from '../frontend/src/lib/consensus.js'
import { replayRecordedEvents } from '../frontend/src/lib/demoReplay.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const RECORDINGS = join(HERE, 'recorded_runs')

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function replay(recording) {
  const received = []
  const statuses = []

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`${recording.id}: replay timed out`)), 2000)
    replayRecordedEvents(recording.events, {
      intervalMs: 1,
      onEvent(eventName) {
        received.push(eventName)
        if (eventName === 'run.complete' || eventName === 'run.error') {
          clearTimeout(timeout)
          setTimeout(resolve, 0)
        }
      },
      onStatus(status) {
        statuses.push(status)
      },
    })
  })

  assert(JSON.stringify(received) === JSON.stringify(recording.events), `${recording.id}: replay order changed`)
  assert(statuses[0] === 'live' && statuses.at(-1) === 'complete', `${recording.id}: bad replay status`)
}

const files = (await readdir(RECORDINGS)).filter((file) => file.endsWith('.json')).sort()
const recordings = await Promise.all(files.map(async (file) => (
  JSON.parse(await readFile(join(RECORDINGS, file), 'utf8'))
)))

assert(recordings.length === 4, 'Demo mode must expose exactly four keyboard cases')
assert(new Set(recordings.map((item) => item.shortcut)).size === 4, 'Demo shortcuts must be unique')
assert(recordings.map((item) => item.shortcut).join('') === '1234', 'Demo shortcuts must be 1 to 4')

// The cross-check has to be exercised by the recordings, because that is the path the demo
// falls back to when the vision API is rate limited — which it was for most of A10.
const outcomes = recordings.map((item) => deriveConsensus(item.events, item.state).state)
for (const wanted of ['agree', 'relabelled', 'contested', 'unavailable']) {
  assert(outcomes.includes(wanted), `No recorded run demonstrates the "${wanted}" cross-check state`)
}

for (const recording of recordings) {
  const state = recording.state
  const diagnosisEvents = recording.events.filter((event) => event.startsWith('diagnose.tile.'))
  const verdictEvent = `verify.${state.verification?.status?.toLowerCase() ?? 'pass'}`

  assert(recording.infected_tile_ids.length <= 38, `${recording.id}: too many diagnosed tiles`)
  assert(diagnosisEvents.length === 38, `${recording.id}: expected all 38 scored tile events`)
  assert(recording.events[0] === 'run.start', `${recording.id}: run.start must be first`)
  assert(recording.events.at(-1) === 'run.complete', `${recording.id}: run.complete must be last`)
  assert(recording.events.includes(verdictEvent), `${recording.id}: verdict event does not match state`)

  if (state.status === 'blocked') {
    assert(state.plan_draft === null && state.schedule === null, `${recording.id}: BLOCK leaked actions`)
    assert(state.verification.status === 'BLOCK', `${recording.id}: blocked run lacks BLOCK verdict`)
    assert(!recording.previous_scan, `${recording.id}: BLOCK must not expose a trend baseline`)
  } else {
    const previous = recording.previous_scan
    assert(previous?.age_days > 0, `${recording.id}: missing previous scan age`)
    assert(previous?.file_name === recording.file_name, `${recording.id}: baseline field filename changed`)
    assert(Number.isFinite(previous?.spread?.pct_affected), `${recording.id}: invalid previous affected area`)
    assert(Number.isFinite(previous?.spread?.clusters), `${recording.id}: invalid previous clusters`)
    assert(typeof previous?.spread?.direction === 'string', `${recording.id}: invalid previous direction`)
    assert(Number.isFinite(previous?.spread?.est_yield_loss_pct), `${recording.id}: invalid previous yield loss`)
  }

  await replay(recording)
  await replay(recording)
  console.log(`ok ${recording.shortcut}: ${recording.label} (${recording.events.length} events, replayed twice)`)
}

console.log('offline demo recordings verified')
