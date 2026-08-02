# Phase B8 presentation checklist

Automated repository work is separated from physical evidence and rehearsal so synthetic assets cannot be mistaken for completed field validation.

## Implemented and machine-checked

- [x] Three recorded runs with timer replay
- [x] Backend-free auto-start and keyboard shortcuts `1`, `2`, `3`
- [x] PASS/REWRITE and BLOCK paths represented
- [x] Recording invariant and replay-order verifier
- [x] Root setup README and screenshot section
- [x] Nine-slide Markdown deck with Dev A artifact references

## Real field evidence — human task

- [ ] Collect 30–50 original crop photos into `demo/field_photos/`
- [ ] Record crop, location context, date, device, and consent/ownership for every photo batch
- [ ] Stitch and replace the light-infection mosaic
- [ ] Stitch and replace the heavy-infection mosaic
- [ ] Stitch and replace the clean-field mosaic
- [ ] Hand the original field-photo set to Dev A for an untouched real-field evaluation
- [ ] Put the measured lab-vs-field gap on slide 7; never infer or invent it

## Visual end-to-end run log — human task

| Case | Pass 1 | Pass 2 | Flaky issue / action |
|---|---|---|---|
| Light infection | [ ] | [ ] | |
| Heavy infection | [ ] | [ ] | |
| Clean / unsupported BLOCK | [ ] | [ ] | |

- [ ] Run the table once with the real backend
- [ ] Run the table once with the backend stopped and `VITE_DEMO_MODE=true`
- [ ] Confirm key `1`, `2`, and `3` each restart the active replay
- [ ] Confirm BLOCK exposes no dosage, schedule, cost, or rescan date

## Presentation capture — human task

- [ ] Capture `docs/screenshots/dashboard.png` from a real-field run
- [ ] Record the backup demo video immediately after the first clean rehearsal
- [ ] Confirm the video plays locally with wifi disabled and audible narration
- [ ] Rehearse the three-minute sequence with Dev A three times
- [ ] Replace slide 8's pending safety metric after running the adversarial test matrix
