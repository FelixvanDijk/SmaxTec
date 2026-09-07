# Changelog

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
