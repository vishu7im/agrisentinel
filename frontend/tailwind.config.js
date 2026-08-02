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
          severe: '#dc2626',   // both models call this tile diseased
          skipped: '#4b5563',
        },
        // Verifier verdicts. Amber for BLOCK, never red: a refusal is a decision, not an error.
        verdict: {
          pass: '#22c55e',
          rewrite: '#eab308',
          block: '#f59e0b',
        },
        // The whole-image vision cross-check. Its own hue on purpose: emerald already means
        // "the tile classifier" and "healthy" everywhere else, so a second opinion drawn in
        // emerald would read as agreement before a word of it had been read.
        vision: {
          DEFAULT: '#38bdf8',
          dim: '#0ea5e9',
        },
      },
      // Four roles, not a scale. Every panel already pairs an uppercase tracked eyebrow with a
      // semibold title; naming them stops the pairing being retyped, and `display` is the one
      // genuinely new size — the app had nothing big enough to read from the back of a room.
      fontSize: {
        eyebrow: ['0.6875rem', { letterSpacing: '0.2em', lineHeight: '1rem' }],
        display: ['clamp(2rem,6vw,3.75rem)', { lineHeight: '1.04', letterSpacing: '-0.02em' }],
        stat: ['clamp(1.75rem,4vw,3rem)', { lineHeight: '1', letterSpacing: '-0.02em' }],
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
