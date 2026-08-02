import { useState } from 'react'
import { createFarmerBriefImage, shareFarmerBriefImage } from '../lib/farmerBriefImage.js'
import LoadingSkeleton, { SkeletonBlock } from './LoadingSkeleton.jsx'

const LANGUAGES = [
  { code: 'en', label: 'EN', name: 'English' },
  { code: 'hi', label: 'हि', name: 'हिन्दी' },
]

const EXPORT_LABELS = {
  cancelled: 'Share cancelled',
  downloaded: 'PNG downloaded',
  error: 'Export failed',
  idle: 'Share brief',
  shared: 'Brief shared',
  working: 'Creating PNG…',
}

export default function FarmerBrief({ blocked, fieldName, loading, phase, report }) {
  const [language, setLanguage] = useState('en')
  const [exportState, setExportState] = useState('idle')
  const hasBrief = report?.en || report?.hi
  const activeBrief = report?.[language]

  function selectLanguage(code) {
    setLanguage(code)
    setExportState('idle')
  }

  async function exportBrief() {
    if (!activeBrief || exportState === 'working') return
    setExportState('working')

    try {
      const image = await createFarmerBriefImage({
        blocked,
        fieldName,
        language,
        text: activeBrief,
      })
      const outcome = await shareFarmerBriefImage(image)
      setExportState(outcome === 'cancelled' ? 'cancelled' : outcome)
    } catch {
      setExportState('error')
    }
  }

  return (
    <article className="order-first rounded-2xl border border-emerald-400/20 bg-gradient-to-br from-emerald-400/10 to-field-panel p-4 shadow-2xl shadow-black/20 sm:p-6 xl:order-none">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300/70">Farmer brief</p>
          <h2 className="mt-1 text-xl font-semibold text-white">Field result in plain words</h2>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
          <div className="flex shrink-0 rounded-lg border border-field-border bg-black/20 p-1" aria-label="Brief language">
            {LANGUAGES.map((option) => (
              <button
                aria-label={`Show brief in ${option.name}`}
                aria-pressed={language === option.code}
                className={`min-h-11 min-w-12 rounded-md px-3 py-2 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-50 ${language === option.code ? 'bg-emerald-400 text-emerald-950' : 'text-slate-400 hover:text-white'}`}
                disabled={!hasBrief}
                key={option.code}
                onClick={() => selectLanguage(option.code)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
          <button
            aria-label={`Share farmer brief in ${LANGUAGES.find((option) => option.code === language)?.name}`}
            className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs font-bold text-emerald-200 transition hover:border-emerald-300/60 hover:bg-emerald-400/15 disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none"
            disabled={!activeBrief || exportState === 'working'}
            onClick={exportBrief}
            type="button"
          >
            <span aria-hidden="true">{exportState === 'working' ? '◌' : '↗'}</span>
            {EXPORT_LABELS[exportState]}
          </button>
        </div>
      </div>

      <p className="sr-only" role="status" aria-live="polite">{exportState === 'idle' ? '' : EXPORT_LABELS[exportState]}</p>

      <div className="mt-5 min-h-52 rounded-xl border border-white/10 bg-black/15 p-4 sm:p-6">
        {hasBrief ? (
          <div className="result-enter grid">
            {LANGUAGES.map((option) => (
              <p
                aria-hidden={language !== option.code}
                className={`[grid-area:1/1] text-lg leading-8 text-slate-100 transition-opacity duration-200 ${language === option.code ? 'visible opacity-100' : 'invisible pointer-events-none opacity-0'}`}
                key={option.code}
                lang={option.code}
              >
                {report[option.code] || 'This brief is not available in the selected language.'}
              </p>
            ))}
          </div>
        ) : loading ? (
          <LoadingSkeleton className="pt-1" label="Preparing farmer brief">
            <SkeletonBlock className="h-4 w-2/3" />
            <SkeletonBlock className="mt-4 h-3 w-full" />
            <SkeletonBlock className="mt-3 h-3 w-11/12" />
            <SkeletonBlock className="mt-3 h-3 w-4/5" />
            <SkeletonBlock className="mt-7 h-3 w-3/4" />
          </LoadingSkeleton>
        ) : (
          <div className="flex min-h-40 items-center justify-center text-center">
            <div>
              <span className="mx-auto grid size-9 place-items-center rounded-full bg-emerald-400/10 text-emerald-300">अ</span>
              <p className="mt-3 text-sm font-medium text-slate-300">
                {phase === 'complete' ? 'No farmer brief was returned.' : 'Your farmer-friendly brief is being prepared.'}
              </p>
            </div>
          </div>
        )}
      </div>
    </article>
  )
}
