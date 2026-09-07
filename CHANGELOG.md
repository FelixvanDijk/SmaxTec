# Changelog

## 0.2.0 — 2026-09-07 (development preview)

- Added dynamic farm discovery after every login; currently observed farms appear
  automatically and future additions require no GUI code change.
- Added farm selection, multiple cow-number entry, native From/To date controls,
  a review confirmation and per-cow progress to the desktop GUI.
- Added serialized worker commands so login, farm navigation and export actions
  stay on the browser-owning thread without blocking the interface.
- Added exact Animal number matching, row-scoped export controls, explicit Measured
  data selection and one final export submission per cow.
- Added partial completion reporting, cancellation boundaries and in-memory guards
  against repeating an attempted export during the same session.
- Live-verified farm discovery through the final export dialog without sending an
  email. Added synthetic end-to-end coverage for export submissions and failures.

## 0.1.0 — 2026-09-07 (development preview)

- Added a double-click launcher for the prepared local preview and simple GUI
  testing instructions. Other computers still use the bundled distribution.
- Established the product requirements, agent instructions, architecture decisions,
  phased roadmap, and persistent handover documents.
- Selected a Windows-first Python/Qt desktop application with a separate Playwright
  browser adapter and bundled-runtime distribution strategy.
- Added a styled desktop login screen, masked in-memory credentials, responsive
  progress, cancel/disconnect, and browser cleanup on shutdown.
- Verified real smaXtec login; stable form selectors and authenticated navigation
  checks are isolated in the browser adapter. Login submits once without retries.
- Added synthetic browser and GUI tests, a hash-pinned dependency lock, Windows CI,
  and a Chromium-inclusive PyInstaller build with offline executable smoke checks.
- Built the Windows directory bundle. GitHub Windows CI passed all 21 tests and
  the packaged GUI/Chromium smoke check, then uploaded the preview archive.
- Local execution of the generated EXE was denied by this computer; the source GUI
  works. This machine-specific launch issue and production installer/signing remain
  tracked release work.
