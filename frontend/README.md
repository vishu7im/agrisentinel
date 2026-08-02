# AgriSentinel frontend

React 19 + Vite + Tailwind console for the frozen run-state contract in `../contract/`.

## Live or mock API

```bash
cp .env.example .env
npm install
npm run dev
```

Set `VITE_API_URL` to the backend or start `node ../contract/mock_server.mjs --fast` on the default port 8000.

## Backend-free demo

```bash
VITE_DEMO_MODE=true npm run dev
```

Recorded cases from `../demo/recorded_runs/` auto-play through the normal event consumer. Use keys `1`, `2`, and `3` to switch or restart cases.

## Previous scan comparison

In live mode, completed PASS results are kept in browser-local storage so the next scan can show affected-area, cluster, direction, and estimated yield-loss changes. The prior filename is always shown; if it differs, the UI asks the operator to confirm both images belong to the same field. BLOCK results are never stored as comparison baselines.

Demo cases `1` and `2` use clearly labelled synthetic seven-day baselines. Case `3` demonstrates that a BLOCK result cannot enter the comparison history.

## Shareable farmer brief

When a farmer brief is ready, choose English or Hindi and select **Share brief**. AgriSentinel creates a 1200-pixel PNG containing the selected brief, field filename, export date, and verification state. Devices with file sharing support open the native share sheet; other browsers download the PNG. The image is rendered entirely in the browser and is not uploaded to another service.

## Checks

```bash
npm run lint
npm run build
npm run verify:demo
```

See the root `README.md` and `../demo/README.md` for the complete setup and presentation runbook.
