/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Dark agricultural palette. Named by role, not by hue, so B1's layout work
        // doesn't have to rename anything when the shade is tuned.
        field: {
          bg: '#0d1410',      // page background
          panel: '#141d17',   // panel surfaces
          border: '#243329',
        },
        // Heatmap tile states — B2 reads these directly.
        tile: {
          healthy: '#4ade80',
          diseased: '#f97316',
          severe: '#dc2626',
          skipped: '#4b5563',
        },
        // Verifier verdicts. Amber for BLOCK, never red: a refusal is a decision, not an error.
        verdict: {
          pass: '#22c55e',
          rewrite: '#eab308',
          block: '#f59e0b',
        },
      },
      fontFamily: {
        // Devanagari fallback for report.hi — without this, Hindi renders as tofu boxes
        // on machines that resolve the default sans to something Latin-only.
        sans: ['system-ui', 'Segoe UI', 'Noto Sans', 'Noto Sans Devanagari', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
