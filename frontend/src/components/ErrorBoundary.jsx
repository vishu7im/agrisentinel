import { Component } from 'react'

/**
 * A thrown render must never blank the page.
 *
 * The realistic thrower is `MarkdownPlan`, a hand-rolled block parser fed model output live on
 * stage. Wrapped twice on purpose: once around the whole app, and once around the plan panel on
 * its own, so a plan that fails to render costs one panel and leaves the heatmap, the
 * cross-check and the severity read on screen. A demo that loses a panel is a demo; a demo that
 * loses the page is over.
 *
 * A class component because that is still the only way to catch a render error in React.
 */
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Kept out of the UI and put where it is useful. The panel says what broke; the console
    // has the stack for whoever is fixing it afterwards.
    console.error('[AgriSentinel] render failed', error, info)
  }

  render() {
    const { children, label = 'This section' } = this.props
    const { error } = this.state
    if (!error) return children

    return (
      <section
        className="rounded-2xl border border-verdict-block/40 bg-verdict-block/[0.06] p-5 text-sm lg:col-span-2"
        role="alert"
      >
        <p className="text-eyebrow font-semibold uppercase text-amber-300/80">Display error</p>
        <h2 className="mt-1 text-lg font-semibold text-white">{label} could not be drawn</h2>
        <p className="mt-2 max-w-prose leading-relaxed text-slate-300">
          The rest of the scan is unaffected and still on screen. This is a display fault, not a
          problem with the field analysis.
        </p>
        <p className="mt-3 break-words font-mono text-xs text-amber-200/80">{String(error?.message ?? error)}</p>
        <button
          className="mt-4 min-h-11 rounded-lg border border-field-border bg-white/5 px-4 text-sm font-medium text-white transition hover:border-emerald-400/50"
          onClick={() => this.setState({ error: null })}
          type="button"
        >
          Try drawing it again
        </button>
      </section>
    )
  }
}
