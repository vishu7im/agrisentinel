const IMAGE_WIDTH = 1200
const SIDE_PADDING = 88
const BODY_FONT = '42px system-ui, "Noto Sans", "Noto Sans Devanagari", sans-serif'
const BODY_LINE_HEIGHT = 64

function roundedRect(context, x, y, width, height, radius) {
  const corner = Math.min(radius, width / 2, height / 2)
  context.beginPath()
  context.moveTo(x + corner, y)
  context.arcTo(x + width, y, x + width, y + height, corner)
  context.arcTo(x + width, y + height, x, y + height, corner)
  context.arcTo(x, y + height, x, y, corner)
  context.arcTo(x, y, x + width, y, corner)
  context.closePath()
}

export function wrapCanvasText(context, text, maxWidth) {
  const paragraphs = String(text).trim().split(/\n+/)
  const lines = []

  paragraphs.forEach((paragraph, paragraphIndex) => {
    const words = paragraph.trim().split(/\s+/).filter(Boolean)
    let line = ''

    words.forEach((word) => {
      const candidate = line ? `${line} ${word}` : word
      if (!line || context.measureText(candidate).width <= maxWidth) {
        line = candidate
      } else {
        lines.push(line)
        line = word
      }
    })

    if (line) lines.push(line)
    if (paragraphIndex < paragraphs.length - 1) lines.push('')
  })

  return lines
}

export function briefImageFileName(fieldName, language) {
  const stem = String(fieldName || 'field')
    .replace(/\.[^.]+$/, '')
    .normalize('NFKD')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .toLowerCase()
    .slice(0, 48) || 'field'

  return `agrisentinel-${stem}-brief-${language}.png`
}

function formatExportDate(value) {
  const date = value instanceof Date ? value : new Date(value)
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function fitCanvasText(context, text, maxWidth) {
  const value = String(text)
  if (context.measureText(value).width <= maxWidth) return value

  let fitted = value
  while (fitted && context.measureText(`${fitted}…`).width > maxWidth) fitted = fitted.slice(0, -1)
  return `${fitted.trimEnd()}…`
}

function canvasToBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('The brief image could not be created.'))
    }, 'image/png')
  })
}

// Badge states. Amber for anything withheld — a refusal is a decision, not an error.
function badgeFor(blocked, crossCheck) {
  if (blocked) return { fill: '#78350f', ink: '#fcd34d', text: 'ADVICE WITHHELD' }
  if (crossCheck === 'contested') return { fill: '#78350f', ink: '#fcd34d', text: 'MODELS DISAGREE' }
  if (crossCheck === 'agree') return { fill: '#064e3b', ink: '#6ee7b7', text: 'VERIFIED · CROSS-CHECKED' }
  return { fill: '#064e3b', ink: '#6ee7b7', text: 'VERIFIED OUTPUT' }
}

const CROSS_CHECK_LINE = {
  agree: 'Whole-image cross-check agrees',
  contested: 'Whole-image cross-check disagrees',
  relabelled: 'Diagnosis corrected by whole-image cross-check',
  unavailable: 'Whole-image cross-check unavailable',
}

export async function createFarmerBriefImage({ blocked, crossCheck, fieldName, generatedAt = new Date(), language, text }) {
  if (!text) throw new Error('No farmer brief is available to export.')

  const canvas = document.createElement('canvas')
  canvas.width = IMAGE_WIDTH
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Image export is not supported in this browser.')

  context.font = BODY_FONT
  const lines = wrapCanvasText(context, text, IMAGE_WIDTH - (SIDE_PADDING * 2) - 72)
  const bodyHeight = Math.max(420, (lines.length * BODY_LINE_HEIGHT) + 160)
  canvas.height = 405 + bodyHeight + 225

  context.fillStyle = '#0d1410'
  context.fillRect(0, 0, canvas.width, canvas.height)

  const glow = context.createRadialGradient(1030, 80, 20, 1030, 80, 520)
  glow.addColorStop(0, 'rgba(52, 211, 153, 0.20)')
  glow.addColorStop(1, 'rgba(52, 211, 153, 0)')
  context.fillStyle = glow
  context.fillRect(0, 0, canvas.width, 620)

  context.fillStyle = '#34d399'
  roundedRect(context, SIDE_PADDING, 72, 70, 70, 20)
  context.fill()
  context.fillStyle = '#052e20'
  context.font = '700 38px system-ui, sans-serif'
  context.textAlign = 'center'
  context.fillText('◇', SIDE_PADDING + 35, 120)

  context.textAlign = 'left'
  context.fillStyle = '#ffffff'
  context.font = '700 42px system-ui, sans-serif'
  context.fillText('AgriSentinel', SIDE_PADDING + 94, 111)
  context.fillStyle = '#6ee7b7'
  context.font = '700 18px system-ui, sans-serif'
  context.fillText('AUTONOMOUS FIELD HEALTH', SIDE_PADDING + 95, 142)

  context.fillStyle = '#94a3b8'
  context.font = '600 22px system-ui, "Noto Sans Devanagari", sans-serif'
  context.fillText(language === 'hi' ? 'FARMER BRIEF · हिन्दी' : 'FARMER BRIEF · ENGLISH', SIDE_PADDING, 230)
  context.fillStyle = '#ffffff'
  context.font = '700 52px system-ui, "Noto Sans Devanagari", sans-serif'
  context.fillText('Field result in plain words', SIDE_PADDING, 292)

  // Three states, not two. This poster gets shared onward and read on its own, so a run where
  // the two models disagreed must not go out stamped VERIFIED OUTPUT — that badge would assert
  // exactly the certainty the system just declined to claim. Correctness, not decoration.
  const badge = badgeFor(blocked, crossCheck)
  context.font = '700 19px system-ui, sans-serif'
  const badgeWidth = context.measureText(badge.text).width + 48
  context.fillStyle = badge.fill
  roundedRect(context, SIDE_PADDING, 326, badgeWidth, 46, 23)
  context.fill()
  context.fillStyle = badge.ink
  context.fillText(badge.text, SIDE_PADDING + 24, 357)

  // One line naming the second opinion, so a reader of the poster alone knows a cross-check
  // happened and what it concluded.
  const crossLine = CROSS_CHECK_LINE[crossCheck]
  if (crossLine) {
    context.fillStyle = '#94a3b8'
    context.font = '400 17px system-ui, sans-serif'
    context.fillText(crossLine, SIDE_PADDING + badgeWidth + 18, 357)
  }

  const bodyTop = 405
  context.fillStyle = '#141d17'
  roundedRect(context, SIDE_PADDING, bodyTop, IMAGE_WIDTH - (SIDE_PADDING * 2), bodyHeight, 30)
  context.fill()
  context.strokeStyle = 'rgba(110, 231, 183, 0.22)'
  context.lineWidth = 2
  context.stroke()

  context.fillStyle = '#6ee7b7'
  context.font = '700 18px system-ui, "Noto Sans Devanagari", sans-serif'
  context.fillText(language === 'hi' ? 'खेत का परिणाम' : 'FIELD RESULT', SIDE_PADDING + 36, bodyTop + 58)

  context.fillStyle = '#f1f5f9'
  context.font = BODY_FONT
  lines.forEach((line, index) => {
    context.fillText(line, SIDE_PADDING + 36, bodyTop + 126 + (index * BODY_LINE_HEIGHT))
  })

  const footerTop = bodyTop + bodyHeight + 66
  context.fillStyle = '#ffffff'
  context.font = '700 24px system-ui, "Noto Sans Devanagari", sans-serif'
  context.fillText(
    fitCanvasText(context, fieldName || 'Field scan', IMAGE_WIDTH - (SIDE_PADDING * 2)),
    SIDE_PADDING,
    footerTop,
  )
  context.fillStyle = '#94a3b8'
  context.font = '500 20px system-ui, sans-serif'
  context.fillText(`Created ${formatExportDate(generatedAt)}`, SIDE_PADDING, footerTop + 38)

  context.fillStyle = '#64748b'
  context.font = '500 18px system-ui, "Noto Sans Devanagari", sans-serif'
  const safetyNote = blocked
    ? 'No treatment advice is included because this result was withheld by the safety verifier.'
    : 'Follow the verified plan, product label, and local extension guidance.'
  context.fillText(safetyNote, SIDE_PADDING, footerTop + 98)

  return {
    blob: await canvasToBlob(canvas),
    fileName: briefImageFileName(fieldName, language),
  }
}

export async function shareFarmerBriefImage({ blob, fileName }) {
  const file = typeof File === 'function' ? new File([blob], fileName, { type: 'image/png' }) : null
  const shareData = file ? { files: [file], title: 'AgriSentinel farmer brief' } : null
  let canShareFile = false

  try {
    canShareFile = Boolean(shareData && navigator.share && navigator.canShare?.(shareData))
  } catch {
    // Some partial Web Share implementations throw while checking file support.
  }

  if (canShareFile) {
    try {
      await navigator.share(shareData)
      return 'shared'
    } catch (error) {
      if (error?.name === 'AbortError') return 'cancelled'
      // Fall through to a local PNG when the platform share sheet fails.
    }
  }

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.rel = 'noopener'
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return 'downloaded'
}
