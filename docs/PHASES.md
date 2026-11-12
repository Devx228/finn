# Phase gates — evidence log

One entry per phase gate (spec §16), with the real output that showed it passing. Newest last.

## Phase 0a — local skeleton ✅ 2026-11-12
- Gate: app opens on a phone over Wi-Fi with data from the API, and from the snapshot when the
  API is stopped.
- Evidence: CDP-emulated 390×844 iPhone at `http://172.23.70.20:3000` — API up: badge
  "Live · as of 12 Nov, 14:37 IST", `scrollWidth` 390; API process killed: badge "Snapshot · as
  of 12 Nov, 14:37 IST". Owner then confirmed on their own phone ("yup it works").
- Checks: API 5 tests, web 5 tests, ruff/mypy/eslint/tsc clean, `next build` ok; API Docker image
  runs against local Postgres.

## Phase 0b — deployed ✅ 2026-11-12
- Gate: same on the public URLs.
- Evidence: `https://finn-api-mxni.onrender.com/health` → `{"status":"ok","env":"render","db":"ok"}`
  (Neon); CORS header `access-control-allow-origin: https://finn-tawny-nine.vercel.app`; emulated
  phone on `https://finn-tawny-nine.vercel.app` → "Live · as of 12 Nov, 16:38 IST"; with
  `*onrender.com*` blocked → "Snapshot · as of 12 Nov, 14:37 IST"; no horizontal scroll.

## Phase 1 — data plumbing (in progress)
- Gate: `finn ingest all` fills the DB for the demo companies without manual steps; row counts
  printed.
