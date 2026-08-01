/**
 * Phase 0 placeholder. Deliberately not a layout — B1 builds the real three-panel shell.
 *
 * All this does is prove the scaffold is wired: Tailwind compiles (including the custom
 * `field-*` colours), and the env var actually resolves. If VITE_API_URL shows as "unset"
 * below, copy .env.example to .env before starting B1.
 */
export default function App() {
  const apiUrl = import.meta.env.VITE_API_URL
  const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'

  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <div className="w-full max-w-lg rounded-lg border border-field-border bg-field-panel p-8">
        <h1 className="text-2xl font-semibold text-slate-100">AgriSentinel</h1>
        <p className="mt-1 text-sm text-slate-400">
          Autonomous field health agent — frontend scaffold
        </p>

        <dl className="mt-6 space-y-2 font-mono text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-slate-500">VITE_API_URL</dt>
            <dd className={apiUrl ? 'text-tile-healthy' : 'text-verdict-block'}>
              {apiUrl || 'unset — copy .env.example to .env'}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-slate-500">VITE_DEMO_MODE</dt>
            <dd className="text-slate-300">{String(demoMode)}</dd>
          </div>
        </dl>

        <p className="mt-6 border-t border-field-border pt-4 text-xs text-slate-500">
          Start the mock server with{' '}
          <code className="text-slate-400">node contract/mock_server.mjs --fast</code>, then
          begin Phase B1.
        </p>
      </div>
    </main>
  )
}
