# Optional gimbal remote layout evidence

Source hashes and evidence hashes are in `manifest.json`. The UI-only slice is
on `feat/optional-gimbal-control-bench` with existing integration changes.

Commands from the repository root (npm commands use the dashboard directory):

```bash
cd dashboard
CI=true npm test -- --watchAll=false --runInBand
npm run build
cd ..
node reports/gimbal-remote-layout/browser_check.cjs
git diff --check
```

Results: 62 dashboard suites / 471 tests pass; production build succeeds.
`browser-events.json` records Chrome version and four passing viewport cases:
320, 390, 768 and 1280 pixels. Tests exercise custom settings, one-step taps,
mouse or touch holds, keyboard holds, release, directional placement, minimum
44-pixel controls and mobile overflow. Each case reports zero real camera actions.
Panel and dialog screenshots are included; they contain no room video.

The browser harness uses the saved offline status contract, mocks camera
availability in the browser and intercepts **all** `/api/v1/actions/**` calls.
It never forwards those actions. It expects the production dashboard on 3040
and the existing isolated backend on 5077 for ordinary non-action reads.
To reproduce, copy `browser_check.cjs` back to
`reports/gimbal-remote-layout/` (its relative Playwright import assumes that
location). The status fixture it reads is the previous movement-controls
`runtime-status.json`, also copied here as `status-fixture.json`.

No camera tests, mounting corrections, flight commands or cross-OS native
qualification are claimed. These tests ran in local Linux Chrome with mouse,
emulated mobile touch and keyboard input.
