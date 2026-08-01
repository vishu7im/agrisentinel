import { readdir, readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
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

assert(recordings.length === 3, 'Demo mode must expose exactly three keyboard cases')
assert(new Set(recordings.map((item) => item.shortcut)).size === 3, 'Demo shortcuts must be unique')
assert(recordings.map((item) => item.shortcut).join('') === '123', 'Demo shortcuts must be 1, 2, and 3')

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
  }

  await replay(recording)
  await replay(recording)
  console.log(`ok ${recording.shortcut}: ${recording.label} (${recording.events.length} events, replayed twice)`)
}

console.log('offline demo recordings verified')
