import { useRef, useState } from 'react'

const ACCEPTED_TYPES = ['image/jpeg', 'image/png']

// Auto first, because most people will not touch this and the model guessing is better than a
// hardcoded crop. But the explicit options matter more than they look: the classifier's crop
// vote is reliable on clean imagery and close to a coin toss on a real phone photo, so telling
// it what you planted is the single biggest thing a user can do for the result.
const CROPS = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'tomato', label: 'Tomato' },
  { value: 'potato', label: 'Potato' },
  { value: 'corn', label: 'Corn' },
]

export default function UploadZone({ disabled, error, onImage }) {
  const [dragging, setDragging] = useState(false)
  const [validationError, setValidationError] = useState(null)
  const [crop, setCrop] = useState('auto')
  const inputRef = useRef(null)

  function chooseFile(file) {
    if (!file) return
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setValidationError('Choose a JPEG or PNG field image.')
      return
    }
    setValidationError(null)
    onImage(file, crop)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    chooseFile(event.dataTransfer.files?.[0])
  }

  return (
    <div>
      <button
        className={`group flex min-h-60 w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed px-5 py-8 text-center transition sm:min-h-72 sm:px-6 sm:py-12 ${
          dragging
            ? 'border-emerald-300 bg-emerald-400/10'
            : 'border-field-border bg-black/10 hover:border-emerald-400/50 hover:bg-emerald-400/5'
        } disabled:cursor-wait disabled:opacity-60`}
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
        type="button"
      >
        <span className="grid size-14 place-items-center rounded-2xl border border-emerald-300/20 bg-emerald-400/10 text-3xl text-emerald-300 transition group-hover:scale-105 sm:size-16">
          ↥
        </span>
        <span className="mt-4 text-lg font-semibold text-white sm:mt-5"><span className="sm:hidden">Choose a field image</span><span className="hidden sm:inline">Drop a field image here</span></span>
        <span className="mt-2 max-w-sm text-sm leading-6 text-slate-400">
          Upload a drone mosaic or crop photo. Scanning starts automatically.
        </span>
        <span className="mt-5 inline-flex min-h-11 items-center rounded-full border border-field-border px-4 py-2 text-xs font-medium uppercase tracking-widest text-slate-300">
          Browse JPEG or PNG
        </span>
      </button>
      <input
        ref={inputRef}
        accept="image/jpeg,image/png"
        className="sr-only"
        disabled={disabled}
        onChange={(event) => chooseFile(event.target.files?.[0])}
        type="file"
      />
      <fieldset className="mt-4" disabled={disabled}>
        <legend className="text-xs font-medium uppercase tracking-widest text-slate-400">
          Crop
        </legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {CROPS.map((option) => (
            <button
              key={option.value}
              aria-pressed={crop === option.value}
              className={`min-h-11 rounded-full border px-4 py-2 text-sm transition disabled:opacity-60 ${
                crop === option.value
                  ? 'border-emerald-400/60 bg-emerald-400/15 font-medium text-emerald-200'
                  : 'border-field-border text-slate-300 hover:border-emerald-400/40 hover:text-white'
              }`}
              disabled={disabled}
              onClick={() => setCrop(option.value)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500">
          {crop === 'auto'
            ? 'The model will guess the crop from the image. Pick one if the result looks wrong — the guess is unreliable on real field photos.'
            : `Scanning as ${CROPS.find((option) => option.value === crop).label.toLowerCase()}. Only this crop's diseases will be considered.`}
        </p>
      </fieldset>
      {(validationError || error) && (
        <p className="mt-3 rounded-lg border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-200" role="alert">
          {validationError || error}
        </p>
      )}
    </div>
  )
}
