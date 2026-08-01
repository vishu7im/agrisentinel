import { useRef, useState } from 'react'

const ACCEPTED_TYPES = ['image/jpeg', 'image/png']

export default function UploadZone({ disabled, error, onImage }) {
  const [dragging, setDragging] = useState(false)
  const [validationError, setValidationError] = useState(null)
  const inputRef = useRef(null)

  function chooseFile(file) {
    if (!file) return
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setValidationError('Choose a JPEG or PNG field image.')
      return
    }
    setValidationError(null)
    onImage(file)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    chooseFile(event.dataTransfer.files?.[0])
  }

  return (
    <div>
      <button
        className={`group flex min-h-72 w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 text-center transition ${
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
        <span className="grid size-16 place-items-center rounded-2xl border border-emerald-300/20 bg-emerald-400/10 text-3xl text-emerald-300 transition group-hover:scale-105">
          ↥
        </span>
        <span className="mt-5 text-lg font-semibold text-white">Drop a field image here</span>
        <span className="mt-2 max-w-sm text-sm leading-6 text-slate-400">
          Upload a drone mosaic or crop photo. Scanning starts automatically.
        </span>
        <span className="mt-5 rounded-full border border-field-border px-4 py-2 text-xs font-medium uppercase tracking-widest text-slate-300">
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
      {(validationError || error) && (
        <p className="mt-3 rounded-lg border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-200" role="alert">
          {validationError || error}
        </p>
      )}
    </div>
  )
}
