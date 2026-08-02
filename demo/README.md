# Demo operations

## Offline insurance path

Keep the backend stopped, then run:

```bash
cd frontend
VITE_DEMO_MODE=true npm run dev
```

Demo mode imports `demo/recorded_runs/*.json` at build time and replays each event through the same event hook used by live SSE. It never calls `POST /api/run`, `GET /api/run/{id}`, or `GET /api/run/{id}/events`.

| Key | Case | Expected outcome |
|---|---|---|
| `1` | Light tomato late blight | REWRITE then PASS, moderate severity, action plan |
| `2` | Heavy tomato late blight | REWRITE then PASS, severe severity, action plan |
| `3` | Clean basil field | BLOCK because basil is outside the supported corpus |

The replay JSON files are compact recordings: each stores its event log, tile classification inputs, and final-state overrides on top of the frozen `contract/mock_run.json`. The two supported tomato cases also include an explicitly synthetic seven-day comparison baseline; it demonstrates the trend view without claiming real longitudinal field evidence. Run `npm run verify:demo` from `frontend/` after every edit.

## Honest asset boundary

The SVG files in `field_mosaics/` are synthetic, clearly labelled offline fixtures. Replace them with stitched mosaics from real photos before the judged demo; do not use them as accuracy evidence. Keep the filenames, or update the matching `image` value in each recording.

Use `field_photos/` for the 30–50 original photos and preserve their provenance. Do not retouch away blur, clutter, lighting changes, or background soil—the difficult conditions are the point of the honesty slide.

## Presenter sequence

1. Start with key `1` and narrate progressive tiles plus the Verifier rewrite.
2. Press `2` to show severity and schedule adaptation.
3. Press `3` to show a safe refusal, not an application crash.
4. If the real backend is healthy, leave demo mode off and upload the matching real mosaic instead.
5. If anything becomes unstable, switch to the offline command above and continue without apologising for the fail-safe.
