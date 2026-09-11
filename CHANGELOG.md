# Changelog

## 0.6.0 — 2026-09-11 (development preview)

- Redesign Direct data API around a spacious target browser and queue-first measurement
  workflow. Successful sign-in collapses the credential form, cow rows are taller, and
  the herd inventory receives substantially more scrollable space while the queue grows
  from a compact small-job view into a taller large-batch viewport.
- Make multiple selection work with ordinary row clicks—no Ctrl required—and add both
  **Select all filtered** and pasted exact-number selection for large cow lists.
- Move metric assignment out of Browse. In Download queue, select one, several or every
  row, discover measurement codes common to those targets, and apply checked codes or
  per-target **all available** only to the selected rows.
- Split queue operations into clearly labelled **Selected rows** and **Whole queue**
  controls, expand the measurement chooser, and consolidate output options into one
  readable collection-settings card without removing any existing download capability.
- Add synthetic regressions for click-friendly multi-selection, common-metric intersection,
  selected-row-only application, collapsed account state and short-window layout.

## 0.5.1 — 2026-09-11 (development preview)

- Fix unusable overlap and vertically clipped controls in the Direct data API Browse
  and Download queue tabs on short laptop/window layouts.
- Give Browse, Queue and Results independent vertical scroll surfaces, preserve full
  Qt control size hints, and add deliberate spacing within queue actions and option cards.
- Add a constrained 760×560 GUI regression proving scrolling activates and the table,
  action, exact-number, date, measurement and output rows remain separated. A themed
  render was also inspected at the user's short-screen content dimensions. All 404
  tests plus dependency, lint, formatting and source-smoke checks pass locally.
- Pass clean GitHub Windows packaging and executable smoke and publish the corrected
  approximately 288 MiB 0.5.1 preview artifact.

## 0.5.0 — 2026-09-11 (development preview)

- Make the official smaXtec Public API v2 the default collection workspace. Sign in
  directly, discover authorized farms/cows/groups/devices, inspect metric codes/units,
  select exact Animal numbers and build a multi-farm queue with individual dates.
- Add an explicit full-queue review, native/10-minute/hourly/daily resolution, optional
  documented weekly farm health index, output folder/name and optional Excel controls.
  Keep the previous website/email workflow available under a labelled legacy tab.
- Add a fixed-origin, redirect-rejecting API adapter with live-verified JSON-body sign-in,
  memory-only bearer token, catalog identity checks, 45-second network waits, overall
  response/size bounds, cooperative cancellation and curated target-specific errors.
- Preserve every direct response as bounded raw JSON chunks and metadata. Build a staging
  CSV plus optional multi-sheet XLSX and SHA-256 `collection.json`; retain completed/
  partial targets on cancellation and never overwrite an earlier collection.
- Convert each reviewed whole farm-local From/To period to explicit half-open UTC bounds
  with DST support. Record local dates, chunk numbers and UTC boundaries without silently
  assuming API To-date inclusivity or undocumented point semantics.
- Withhold events, transformations and server-side background jobs until their missing
  date/lifecycle semantics are confirmed. No API mutations or emailed reports are called.
- Add XlsxWriter to the locked/bundled runtime and cover the API client, downloader,
  queue/review, exact identity, date/DST, partial failure and output behavior synthetically.
  All 403 offline tests pass; read-only authentication/catalog/metric discovery was also
  live-verified. Representative download/client acceptance remains pending.
- Stage every Windows build in a fresh validated system-temporary directory before smoke
  and ZIP publication, avoiding stale/ACL-protected OneDrive bundle directories. Local
  assembly succeeds; this machine still blocks unsigned EXE execution. GitHub's clean
  Windows runner passed packaged smoke and uploaded the approximately 288 MiB preview ZIP.
- Bundle the IANA `tzdata` database explicitly so farm-local date handling works on clean
  Windows computers, which do not provide this database through the operating system.

- Make Microsoft 365 deployment plug-and-play after central approval: validate and
  embed the approved Entra public-client ID during Windows packaging, support a GitHub
  Actions repository variable, and prevent frozen end-user builds from accepting a
  substituted runtime client ID. No approved ID is committed or included yet.
- Record that a classic-Outlook scan containing only `content blocked` messages fails
  M3 acceptance and must be resolved through approved Graph access, not by disabling
  enterprise controls.

## 0.4.1 — 2026-09-10 (development preview)

- Add a preferred **Sign in with Microsoft 365** route using delegated Graph access,
  Microsoft system-browser sign-in/MFA and memory-only tokens. It works independently
  of new Outlook, Outlook on the web or classic Outlook. An approved public-client
  application ID, localhost redirect and tenant `Mail.Read` consent are still required
  before live deployment; no email password or client secret is collected.
- Keep Graph Inbox access read-only and newest-first. Bound HTTP calls, pages, bodies,
  responses, total items and time; validate every opaque pagination URL before sending
  the bearer token. Store only one-way message keys and clear the session on Disconnect.
- Fix classic Outlook's misleading zero result under corporate programmatic-access
  protection. A read-only live scan now exposes 10 recognizable export subjects as
  `content blocked` problem rows while leaving the blocked bodies and links untouched.
- Recognize inline forwards of forwards from their fully validated smaXtec export link
  even when outer subject/sender wording has changed. Forward-as-attachment remains an
  explicit saved-email import case.
- Add synthetic Graph authentication/pagination/failure/cancellation tests, classic
  protection and nested-forward regressions, Microsoft-first GUI controls, MSAL runtime
  dependency locking and bundled dependency metadata. All 384 tests and source smoke
  pass locally; independent Windows executable build and packaged smoke also pass in
  CI. Live Graph/tenant acceptance is recorded separately in `docs/PROJECT_STATE.md`.

## 0.4.0 — 2026-09-10 (development preview)

- Add a separate, manually triggered collection section below website requests.
  Connect an existing classic Outlook profile and explicitly select its Inbox, or
  import saved `.eml`/`.msg` messages without signing into smaXtec.
- Review the newest N matching direct/forwarded emails within a received-time window.
  Freeze selection; report problematic messages and duplicate links without topping
  up with older messages. Saved-file import is explicitly manual, not an inbox scan.
- Download through the confirmed smaXtec/Safe Links route, validate every redirect,
  and reject unsupported hosts, blocked interstitials and non-workbook responses.
- Inspect XLSX packages without opening Excel, read consistent visible-sheet B3
  identifiers, and name each original workbook from its own cow number. Ignore a
  parenthesized annotation, preserve text leading zeroes and avoid file overwrites.
- Add per-user collection folders, a local SQLite journal and redacted JSON manifest.
  Retry incomplete downloads or re-select the same emails after restart and resume
  the existing collection; verify completed file hashes before reusing them.
- Isolate classic Outlook COM in a bounded helper process; keep collection jobs off
  the GUI thread and wait for both website and email workers during application close.
- Add synthetic parser/download/workbook/storage/UI regression coverage and offline
  helper/packaging checks. All 366 tests and source smoke pass locally. Two supplied
  forwarded exports were collected successfully, named independently and resumed with
  hash checks. GitHub Windows executable build/smoke passed; the preview artifact and
  pending client Inbox acceptance are recorded in `docs/PROJECT_STATE.md`.
- Keep sensitivity labels unchanged. Public assignment, Graph sign-in, automatic
  website-request correlation, consolidation and analysis are not implemented.

### Earlier M3 discovery

- Documented the requested manual newest-N email collection workflow, direct/forwarded
  link handling, B3-based names, per-user output folders and durable download state.
- Compared corporate Graph sign-in with classic Outlook integration and recorded
  tenant/Outlook prerequisites, Safe Links safeguards and sensitivity-label boundaries.
- Inspected the supplied workbook read-only and documented outstanding email samples.
  That initial design-only step kept runtime 0.3.0 unchanged before this implementation.

## 0.3.0 — 2026-09-08 (development preview)

- Each cow row now has its own From and To dates, Add cow and remove controls.
- Show all of the first five rows, then fold the middle behind an explicit count;
  expand into a bounded scrollable list to edit hundreds of entries.
- Add optional Apply to all dates with Undo; validate folded rows as well as visible ones.
- Review every cow and its dates in a scrollable confirmation table; freeze the
  reviewed values for submission and disable editing while the batch runs.
- Carry immutable cow/date targets through the worker, website adapter, results,
  partial failures and duplicate guards across browser reconnections. The same cow
  with another period is distinct; identical targets are deduplicated.
- Collapse the credential fields after connection to leave more room for requests.
- Add editor stress coverage and real-browser offline tests tracing individual
  dates through GUI submission, subsequent batches and partial-failure recovery.

## 0.2.2 — 2026-09-07 (development preview)

- Replaced segmented date widgets with strict masked `DD/MM/YYYY` entry after a
  reported request visibly retained an unintended 2024 start year.
- Added exact parsing, real-calendar validation, range ordering, pre-2000 and
  future-date safeguards, plus an always-visible confirmed-range summary.
- Kept the reviewed date range as immutable date values and serialize it once for
  smaXtec; abort before Export if either website date field changes that value.
- Added GUI-to-request-to-browser-endpoint tests for `01/09/2026`, invalid dates,
  and a simulated website mutation from 2026 to 2024.

## 0.2.1 — 2026-09-07 (development preview)

- Fixed subsequent export batches failing against stale website/browser state.
- Close the isolated browser after every export batch and automatically create a
  fresh authenticated session when the user confirms another batch.
- Retain credentials only in worker memory for the connected application session;
  clear them on disconnect/close and never persist or log them.
- Preserve farm selection when the refreshed farm list arrives after reconnection.
- Keep no-retry fingerprints across replacement browsers so identical farm/cow/date
  targets and uncertain export clicks cannot be duplicated during the app session.

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
