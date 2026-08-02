/**
 * Reading the two-model cross-check off the event stream.
 *
 * The backend cannot hand this to us as a field: `contract/run_state.schema.json` is frozen and
 * sets `additionalProperties: false` everywhere, so `events[]` — typed as a bare array of
 * strings, with a description that explicitly blesses new prefixes — is the only channel there
 * is. Everything the Observer and the Consensus agent decided arrives as dotted event strings.
 *
 * Pure, no React, importable from Node so `demo/verify-demo.mjs` can assert against it.
 *
 * **It degrades on purpose.** If `consensus.cnn.*` never arrives — an older backend, a run that
 * died early, a replay recorded before the events existed — the classifier's side is recomputed
 * from `runState.tiles` and flagged `derived`. The panel then renders correctly against a
 * backend that knows nothing about any of this, which is what keeps a deployment-order mistake
 * from turning into a blank screen.
 */

/** `late_blight` -> `Late blight`. Also the fallback for anything unrecognised. */
export function humaniseLabel(value) {
  if (!value) return 'Unknown'
  const words = String(value).replaceAll('_', ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** `tomato__septoria_leaf_spot` -> `{crop:'tomato', disease:'septoria_leaf_spot'}`. */
export function splitClassKey(key) {
  if (!key) return { crop: null, disease: null }
  const [crop, disease] = String(key).split('__')
  return disease ? { crop, disease } : { crop: null, disease: crop }
}

function numberFrom(text, suffix) {
  const match = String(text).match(new RegExp(`(-?\\d+(?:\\.\\d+)?)${suffix}$`))
  return match ? Number(match[1]) : null
}

/**
 * The classifier's own reading, recomputed from the tiles.
 *
 * The fallback for a missing `consensus.cnn.*`, and it has to use the same denominator the
 * schema defines for `spread.pct_affected` — scored tiles, skipped ones excluded — or the two
 * numbers on screen disagree for a reason no viewer could work out.
 */
export function deriveCnnFromTiles(tiles) {
  const scored = (tiles ?? []).filter(
    (tile) => tile.label && tile.label !== 'pending' && !tile.label.startsWith('skipped'),
  )
  if (!scored.length) return null

  const counts = new Map()
  let infected = 0
  for (const tile of scored) {
    if (tile.label === 'healthy') continue
    infected += 1
    counts.set(tile.label, (counts.get(tile.label) ?? 0) + 1)
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]
  return {
    derived: true,
    disease: top ? top[0] : 'healthy',
    pct: Math.round((infected / scored.length) * 100),
    tiles: top ? top[1] : 0,
  }
}

const OUTCOME_PREFIXES = [
  ['consensus.contested.', 'contested'],
  ['consensus.not_crop', 'contested'],
  ['consensus.relabel.', 'relabelled'],
  ['consensus.agree.', 'agree'],
  ['consensus.vision_only.', 'vision-only'],
  ['consensus.low_confidence_vision.', 'unsure'],
  ['consensus.vision_clean.', 'unsure'],
  ['consensus.no_disease_opinion', 'no-opinion'],
  ['consensus.crop_scoped_out.', 'no-opinion'],
  ['consensus.not_field_but_foliage', 'not-a-field'],
  ['consensus.skipped.no_vision', 'unavailable'],
]

/**
 * @returns {{
 *   state: 'idle'|'observing'|'agree'|'relabelled'|'contested'|'unsure'|'vision-only'
 *          |'no-opinion'|'not-a-field'|'unavailable',
 *   observer: {crop, classKey, disease, pct, confidence, note, isCropField},
 *   cnn: {disease, pct, tiles, derived}|null,
 *   relabel: {from, to, tiles}|null,
 *   reason: string|null, unavailableReason: string|null, gap: number|null,
 * }}
 */
export function deriveConsensus(events = [], runState = null) {
  const observer = {
    classKey: null,
    confidence: null,
    crop: null,
    disease: null,
    isCropField: true,
    note: '',
    pct: null,
  }
  let cnn = null
  let relabel = null
  let state = 'idle'
  let reason = null
  let unavailableReason = null
  let gap = null
  let requested = false

  for (const event of events) {
    if (event === 'observer.requested') {
      requested = true
      state = 'observing'
    } else if (event.startsWith('observer.note|')) {
      // The one event carrying free text — Gemini's own sentence about what it can see.
      observer.note = event.slice('observer.note|'.length).slice(0, 240)
    } else if (event.startsWith('observer.sees.')) {
      observer.classKey = event.slice('observer.sees.'.length)
      const { crop, disease } = splitClassKey(observer.classKey)
      if (crop) observer.crop = crop
      observer.disease = disease
    } else if (event.startsWith('observer.pct.')) {
      observer.pct = numberFrom(event, 'pct')
    } else if (event.startsWith('observer.crop.')) {
      observer.crop = event.slice('observer.crop.'.length)
    } else if (event === 'observer.not_crop_photo') {
      observer.isCropField = false
    } else if (event.startsWith('observer.unavailable.')) {
      unavailableReason = event.slice('observer.unavailable.'.length)
    } else if (event.startsWith('consensus.cnn.')) {
      const body = event.slice('consensus.cnn.'.length)
      const cut = body.lastIndexOf('.')
      cnn = {
        derived: false,
        disease: cut === -1 ? body : body.slice(0, cut),
        pct: cut === -1 ? null : numberFrom(body.slice(cut + 1), 'pct'),
        tiles: null,
      }
    } else if (event.startsWith('consensus.relabel.')) {
      const body = event.slice('consensus.relabel.'.length)
      const [pair, count] = [body.slice(0, body.lastIndexOf('.')), body.slice(body.lastIndexOf('.') + 1)]
      const [from, to] = pair.split('_to_')
      relabel = { from, tiles: Number.parseInt(count, 10) || 0, to }
    } else if (event.startsWith('consensus.pct_gap.')) {
      gap = numberFrom(event, 'pp')
    }

    for (const [prefix, outcome] of OUTCOME_PREFIXES) {
      if (event.startsWith(prefix)) {
        state = outcome
        if (outcome === 'contested') {
          reason = event === 'consensus.not_crop' ? 'not_crop' : event.split('.')[2] ?? 'disagreement'
        }
        break
      }
    }
  }

  if (unavailableReason && state !== 'contested') state = 'unavailable'
  // No consensus.cnn.* on the log: recompute it, so the left-hand card is never empty just
  // because the backend is older than this file.
  if (!cnn) cnn = deriveCnnFromTiles(runState?.tiles)
  if (!requested && !unavailableReason && state === 'idle') state = 'idle'
  if (gap === null && cnn?.pct != null && observer.pct != null) {
    gap = Math.abs(cnn.pct - observer.pct)
  }

  return { cnn, gap, observer, reason, relabel, state, unavailableReason }
}

/**
 * Was this run's crop identified, or guessed?
 *
 * The same test `reporter.crop_is_guessed` applies on the backend, against the same events, so
 * the brief's hedged wording and the UI's offer to correct it can never disagree. Read here
 * rather than sent as a field because `run_state.schema.json` is frozen and `events[]` already
 * carries it.
 *
 * `observer.crop.*` means the whole-image model read the crop off the photograph.
 * `diagnose.crop_uncertain.*` / `crop_unresolved.*` mean the tile probe voted, and it is
 * measured wrong on 4 of 4 real photographs.
 */
export function cropWasGuessed(events = []) {
  if (events.some((event) => event.startsWith('observer.crop.'))) return false
  return events.some(
    (event) =>
      event.startsWith('diagnose.crop_uncertain.') || event.startsWith('diagnose.crop_unresolved.'),
  )
}

/** Copy for each outcome: a short chip label and one sentence of explanation. */
export const CONSENSUS_COPY = {
  agree: {
    label: 'Both agree',
    tone: 'pass',
    text: 'The tile classifier and the whole-image check reached the same diagnosis independently.',
  },
  contested: {
    label: 'Contested',
    tone: 'block',
    text: 'The two checks disagree about whether this field is diseased. No treatment is recommended until that is settled.',
  },
  'no-opinion': {
    label: 'No second opinion',
    tone: 'neutral',
    text: 'The whole-image check saw something it could not name from the fourteen classes this system knows.',
  },
  'not-a-field': {
    label: 'Not a field photo',
    tone: 'neutral',
    text: 'The whole-image check reads this as foliage rather than a field — a mosaic or a close-up. The scan continues on the tile evidence.',
  },
  observing: {
    label: 'Cross-checking',
    tone: 'vision',
    text: 'A second model is looking at the whole photograph.',
  },
  relabelled: {
    label: 'Relabelled',
    tone: 'rewrite',
    text: 'Both checks see disease and disagree on which. The whole-image check supplies the name; the tile grid keeps the map.',
  },
  unavailable: {
    label: 'Cross-check unavailable',
    tone: 'neutral',
    text: 'The second opinion could not be obtained. The scan below is the tile classifier alone.',
  },
  unsure: {
    label: 'Noted',
    tone: 'neutral',
    text: 'The whole-image check disagreed, but not confidently enough to act on.',
  },
  'vision-only': {
    label: 'Vision only',
    tone: 'neutral',
    text: 'The whole-image check sees disease the tile classifier did not. Not enough on its own to raise an alarm.',
  },
}

/** Why the cross-check was unavailable, in words a judge can read. */
export const UNAVAILABLE_COPY = {
  disabled: 'Cross-check switched off for this run',
  malformed: 'The second model returned an unreadable answer',
  no_key: 'No API key configured — running fully offline',
  rate_limited: 'API quota exhausted',
  timeout: 'The second model did not answer in time',
  too_large: 'Image too large to send',
  unreachable: 'No network route to the second model',
}
