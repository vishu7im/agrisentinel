import baseRun from '../../../contract/mock_run.json'

const recordingModules = import.meta.glob(
  '../../../demo/recorded_runs/*.json',
  { eager: true, import: 'default' },
)
const imageModules = import.meta.glob(
  '../../../demo/field_mosaics/*.svg',
  { eager: true, import: 'default', query: '?url' },
)

function findImage(imageName) {
  const match = Object.entries(imageModules).find(([path]) => path.endsWith(`/${imageName}`))
  if (!match) throw new Error(`Missing demo mosaic: ${imageName}`)
  return match[1]
}

function buildTiles(recording) {
  const infected = new Set(recording.infected_tile_ids)
  const escalated = new Set(recording.escalated_tile_ids)

  return baseRun.tiles.map((tile) => {
    if (tile.label.startsWith('skipped')) return { ...tile }
    const isInfected = infected.has(tile.id)
    const isEscalated = escalated.has(tile.id)

    return {
      ...tile,
      confidence: isEscalated ? 0.79 : isInfected ? 0.88 : 0.94,
      escalated: isEscalated,
      label: isInfected ? recording.diagnosis_label : 'healthy',
    }
  })
}

function hydrateRecording(recording) {
  const state = {
    ...baseRun,
    ...recording.state,
    events: recording.events,
    tiles: buildTiles(recording),
  }

  if (recording.state.verification) {
    state.verification = {
      ...baseRun.verification,
      ...recording.state.verification,
    }
  }

  return {
    ...recording,
    previewUrl: findImage(recording.image),
    runState: state,
  }
}

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'
export const DEMO_CASES = Object.values(recordingModules)
  .map(hydrateRecording)
  .sort((left, right) => Number(left.shortcut) - Number(right.shortcut))
export const DEMO_CASE_SUMMARIES = DEMO_CASES.map(({ id, label, shortcut }) => ({
  id,
  label,
  shortcut,
}))
