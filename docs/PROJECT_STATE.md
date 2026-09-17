# Project state — start here each session

Last updated: 2026-09-17. **Source preview 0.11.0 adds shared Study T0 entry and an
aligned cohort worksheet without changing the established Cow analysis table.** One
strict farm-local T0 can be applied atomically to selected queue rows or the complete
queue; per-row editing remains available. Lifecycle remains best-effort enrichment
per cow/cycle, so unsupported variants cannot reject the catalogue. New API
collections preserve documented animal lifecycle cycles, allowing `Lact` and
farm-local calendar-day `DIM` at T0. `Tn`, `AN`, `Rn` and `%drop` use the client's
agreed windows/formula; Rback follows the client's literal discrete-series wording,
from first post-T0 Rl to the first later reading at/above Rl. The original first sheet
remains exactly 28 A:AB headers in the client's order and one row per cow/case. A new
`Aligned data` sheet places cow traces side by side from -24 to +120 hours at six-hour
steps, reports actual n/mean/lower and upper 95% limits, and adds T/A/R charts. The guided
multi-sheet workbook and established direct-API raw responses, CSVs and descriptive
workbook are unchanged. The optional per-cow Study T0 is reviewed with each queue
row. With no T0, exact points are
pivoted around farm-local From 00:00, labelled a **period anchor**, never claimed as
treatment time. A representative saved direct-API collection confirms separate
`temp_normal_index`, `temp_without_drink_cycles`, `act`, and `rum_index` pairs.
Rumination seconds are converted to minutes in the derived workbook only. The
normal-index clinical interpretation remains an inference requiring client review.
The guided 0.9.0 builder remains available independently. All 432 offline tests
pass. Older collections remain readable but cannot retroactively supply lifecycle
metadata; a saved real collection
regenerated as `client-analysis-2.xlsx` with seven cow rows and available
T/AT/RT fields populated. Clinical and installer acceptance remain pending. See
Decisions 018–021 and `CLIENT_STUDY_WORKBOOK.md`.

0.11.0 verification: shared-T0 tests cover selected rows, the entire queue and
all-or-nothing validation. Automatic-workbook tests assert the original A2:AB table,
populated literal Rback, side-by-side cow values, actual confidence inputs and three
charts with valid references. The full suite passes with all 432 offline tests;
Ruff lint/format and dependency checks pass. PyInstaller assembled the complete
0.11.0 bundle, but this computer's existing policy again denied launching the unsigned
executable (`Access is denied`), so no local packaged-launch or archive claim is made.
No live API collection was run. The new alignment range/statistics and Rback wording
remain subject to client acceptance.

0.10.3 verification: the reported failure was isolated to the only new farm-load
boundary in 0.10.2. Synthetic API coverage now mixes valid cycles with invalid
container types, dates, lactation numbers and dry-off shapes and still loads every
cow. The targeted API/download/study suite passes. The full suite passes with all
429 offline tests, Ruff lint/format and dependency checks. Packaging
was not repeated because this adapter-only fix adds no dependency or bundle boundary;
live farm selection by the user remains the acceptance gate.

0.10.2 verification: the targeted API/download/study suite passed (24 tests), all
428 offline tests passed, and Ruff lint/format checks passed. Synthetic output
verifies lifecycle history transport, Lact 3, DIM 14, seven-/fourteen-day baseline
means, decimal `%drop`, an 88-hour Rback recovery and old-manifest compatibility.
PyInstaller assembled the 0.10.2 bundle, but this computer's existing policy again
denied launching the unsigned executable (`Access is denied`), so no local packaged
smoke is claimed and the final ZIP was not published. No live credentialed collection
was run for this slice; lifecycle semantics and Rback still need client acceptance.

0.10.1 verification: the targeted study/API suite passed (33 tests), all 427
offline tests passed, Ruff lint/format and dependency checks passed. The real
regenerated table has exactly one worksheet, TableStyleMedium2 row banding,
28 client headers and seven populated cow rows; source CSV/raw bytes were not
rewritten. PyInstaller assembled the full 0.10.1 Windows bundle locally; its
`Start-Process` smoke was denied by this machine's existing unsigned-executable
policy (`Access is denied`), so local packaged-launch proof is not claimed. The
prepared source launcher remains usable; CI preview artifact and clean-machine
acceptance still require separate checking after push.

Source preview 0.9.0 added an opt-in client-example study
workbook without changing the established 0.8.0 API download or audit files. Its
metric/event mapping, one-row-per-cow parameters, exact event-relative time points,
aligned cow values and 95% confidence charts have synthetic offline verification.
Real collection mapping, adequacy, client calculation/graph acceptance and release
proof are still pending. See `CLIENT_STUDY_WORKBOOK.md` and the M5 slice below.

The 0.8.0 presentation baseline preserves the proven 0.7.0 direct-API
request and data contracts while adding presentation-safe UI and workbook polish for the
Monday client demonstration.** The default workspace
signs in, discovers farms/cows/groups/devices/metrics, queues individual periods, reviews
them, and writes direct raw JSON + compatible staging CSV + graph-ready tidy CSV +
optional XLSX + hashed provenance without browser exports or email. All 410 offline
tests pass; read-only auth/catalog/metric
discovery was live-verified, and authentication requests still reach the live JSON
endpoint correctly. Representative direct downloads, client date/unit/UI acceptance,
and a signed clean-machine release
remain pending. The 0.8.0 bundle assembles locally, but this computer's existing policy
still denies launching unsigned executables; clean GitHub Windows packaging and
packaged-executable smoke pass. The
working 0.7.0 baseline is preserved on GitHub as
`presentation-baseline-2026-09-13` (`14fab69`). The
website/email workflow remains available in a legacy tab and its Graph deployment work
is paused.

## User intent and scope

Build a beautifully packaged, plug-and-play desktop product for nontechnical users.
Primary workflow: GUI farm/target/time/metric/report inputs → direct smaXtec API raw
collection → canonical normalized data → one calculated/formatted master workbook →
graphs/analysis. Later, agreed anomaly heuristics select cows/periods and feed the same
pipeline automatically. Modularity and documentation across sessions matter.

The user explicitly wants incremental delivery and authorizes GitHub pushes after
substantial milestones. M1/M2 were browser login/export requests. M3 implemented
email collection but is now a compatibility path. M4 is the direct API vertical slice.
Do not invent calculations or clinical meanings in M4.

## M5/M6 client-study workbook preview and acceptance boundaries

- Source 0.10.0 adds one optional Study T0 (`DD/MM/YYYY HH:MM` in farm-local time)
  to each cow's reviewed direct-API queue row, stored as immutable UTC metadata.
  Date filters, API requests and raw/tidy source rows are unchanged. A completed
  usable cow collection automatically produces a separate `client-analysis.xlsx`
  and exposes an **Open client analysis** Results action; the guided builder still
  produces `client-study.xlsx` when requested. The manifest records optional T0,
  derived file/hash and any nonfatal companion error.
- A representative saved collection, inspected read-only outside Git, contains exact
  `temp_normal_index/degree_celsius`, `temp_without_drink_cycles/degree_celsius`,
  `act/act`, and `rum_index/seconds` pairs. The normal-index meaning is inferred
  from code, unit and observed baseline stability, not independently vendor-
  confirmed. `temp/degree_celsius` is a disclosed fallback only if normal index is
  absent; it is never substituted for T/temperature-without-drink-cycles. The
  derived rumination values divide source seconds by 60, with raw CSV unchanged.
  A missing T0 uses a labelled From-midnight period anchor for pivoting, not a
  treatment claim. Source 0.10.2 captures official lifecycle cycles; Lact selects
  the cycle containing T0 and DIM counts farm-local calendar days since calving.
  Tn/AN/Rn and `%drop` use the supplied definitions. Source 0.11.0 interprets Rback
  literally as first Rl to the first later observed value at/above Rl.
- Source 0.10.1 replaces **only the automatic XLSX presentation** with one
  `Cow analysis` sheet matching the ASPI table's 28 exact headers, blue row stripes,
  filter arrows and compact widths. It has no dashboard or extra workbook tabs;
  source lineage remains in manifest/raw/CSVs. `To` is the client's spelling of
  T0 temperature; a header note makes that distinction explicit. Talert/R20 are
  still proxies, not actual alert counts. `%drop` displays `0.13` for 13%, matching
  the example. The guided 0.9.0 builder retains normal/aligned/analysis/charts/QC.
  Drug-specific ASPI/Ketofen/ASPI LIQUID labels are not assigned without product
  data because doing so would misclassify cows.
- Twelve obsolete GitHub Actions preview ZIP artifacts were explicitly removed on
  2026-09-15 to relieve storage pressure; only the working 0.8.0 and 0.7.0 previews
  remain. This deletion is irreversible for those ZIP files, but every source commit
  remains and can rebuild them. GitHub may take 6–12 hours to recalculate usage.

- The client-provided `Analysis sheet.xlsx` has five worksheets. ASPI and Ketofen
  tables use 28 core columns with one cow/case per row. Its Normal values and
  Analysis sheets motivate the separate baseline, aligned and graph views; the
  example has broken chart references, which are not replicated. The companion
  two-page PDF defines the event-relative fields. The files were inspected
  read-only outside Git; no farm/client data was committed.
- Source 0.9.0 adds **Create study workbook** from a completed local format-2 API
  collection in the Results area. A guided, scrollable modal discovers the exact
  source code/unit pairs, lets the user assign normal temperature, temperature
  without drinking cycles, activity and rumination, and enter a farm-local study
  time zero per cow/case. The shared-event button copies a timestamp only on an
  explicit action. File scanning/writing stays off the Qt thread and can be stopped.
- The separate, non-overwriting `client-study.xlsx` holds client-style parameters
  A:AB, source/event columns, Normal values, configurable exact T/RT points, three
  side-by-side cow alignment sheets, a Study graphs sheet with absolute/relative
  temperature/activity/rumination mean, separate absolute/relative available-cow n,
  sample SD and 95% limits, Definitions and QC.
  Elapsed time is UTC; exact T/RT points never become nearest samples. The tidy
  CSV SHA-256 is rechecked before generation; raw responses, both CSVs, manifest
  and existing optional API workbook are unchanged.
- Talert and R20 are *labelled proxies*, not actual alerts. Lact/DIM use lifecycle
  metadata in new collections; Rback uses the disclosed Rl-level interpretation.
  Older collections keep unavailable fields blank. 95% limits use the
  available n per offset; missing/conflicting points remain blank, not estimated.
  Baseline/follow-up coverage shortfalls and duplicate counts appear in QC.
- This is an analytical **preview**, not a general canonical master or a clinically
  accepted report. A representative saved API collection has been inspected read-
  only and confirms the exact source code/unit pairs and 10-minute time fields, but
  no client-approved study event or clinical metric interpretation has been supplied.
  Exact source meaning, timestamp behavior,
  date coverage, formulas, Rback meaning and chart appearance require client review.
  See `CLIENT_STUDY_WORKBOOK.md` for precise window contracts and source limitations.

## M4 direct API implementation and acceptance boundaries


- The **Direct data API** tab is the default workspace. Credentials are masked and
  cleared from the GUI; credentials/token remain in memory only until Disconnect/close.
- Farms, current/archived cows, groups, devices, metric codes and available units come
  from the signed-in account dynamically. Cow number selection uses exact equality.
- Browse offers ordinary click-to-toggle rows without Ctrl, select-all over the current
  filter, and pasted comma/space/newline-separated exact cow numbers. The credential
  form collapses after successful connection and the inventory remains the dominant,
  tall scroll surface.
- One queue may contain multiple farms/types and repeated targets with different dates.
  Every row owns its From/To/metrics and appears in an explicit immutable review.
- Measurements are assigned in Download queue to one, several or every selected row.
  Discovery shows only codes common to the frozen selected targets; changing selection
  invalidates stale discovery. Applying all available remains per target, while checked
  common codes change only selected rows.
- Whole farm-local dates are converted to half-open UTC instants with DST support. The
  API is asked for ISO UTC values. Native/10-minute reads use 31-day chunks, hourly 180
  and daily 730; raw response shape and every chunk boundary are preserved.
- Each unique output folder contains raw per-target chunks and metadata, the compatible
  `measurements.csv` audit table, a tidy `analysis_ready.csv`, optional XlsxWriter workbook
  and `collection.json` format 2 with SHA-256 hashes/status. Both CSVs come from the same
  observation record. The tidy view adds local/UTC time columns only for timezone-aware
  ISO source values and preserves duplicates/order; it does not guess ambiguous times,
  coerce values, convert units or pivot metrics. Output never includes credentials/tokens.
  Cancellation retains partial/completed work.
- Results provides separate, direct actions for `analysis_ready.csv`, the optional
  workbook and the complete audit folder. The workbook adds a branded summary,
  descriptive source-observation chart, measurement index and data guide. Every staging
  value/column remains present; technical lineage columns are hidden only by default.
- Optional weekly farm health-index data is implemented from its documented route.
  Events are withheld because Swagger does not define its integer date unit. Preferred-
  unit conversion, transformations, background jobs and emailed reports are not exposed.
- The current synchronous API has fixed origin, rejected redirects, 45-second socket/
  90-second response bounds and 32 MiB response limits. It never automatically retries.
- An authorized read-only probe confirmed JSON-body sign-in, user/farm discovery,
  organization catalogues and metric discovery for an active animal. No account/farm/
  animal identifiers, token or response data are retained in Git. One unavailable-sensor
  case returned 400 and is handled as a target failure. No live write was performed.
- `docs/API_DATA.md` is the detailed research, implementation and output contract.
- The 2026-09-13 live Swagger and official SDK review found additional event, attention,
  todo, report/template and KPI reads. They remain outside 0.8.0 because point/event
  schemas or clinical meanings are undocumented or not client-accepted. See
  `docs/PRESENTATION_PLAN.md`.
- Acceptance still requires representative live downloads across target types/periods,
  explicit boundary/units/output review, corporate proxy testing and packaged CI proof.

## M3 implementation and acceptance boundaries

- Microsoft 365 delegated sign-in is now the preferred cross-edition connector. It
  uses the system browser/MFA and Graph, so it works independently of new Outlook,
  Outlook on the web or classic Outlook. The code and synthetic tests are complete;
  an approved Entra public-client ID, localhost redirect and tenant `Mail.Read`
  consent are still required before live use. No email password/client secret is used.
- Release packaging now validates `SMAXTEC_MICROSOFT_CLIENT_ID` at build time and
  embeds it as generated package data. Frozen applications ignore runtime overrides;
  ordinary users never configure the ID. No approved ID exists in this workspace or
  its environment yet, so the existing preview cannot perform live Graph sign-in.
- Classic Outlook and manual `.eml`/`.msg` import remain explicit fallbacks. Corporate
  programmatic-access policies are never disabled or bypassed.
- Collection is independent of website login. Connect with Microsoft 365 or classic
  Outlook, explicitly choose an Inbox, find the latest N matching messages, review
  and download. No automatic polling or changes to read flags/messages. Counts include
  duplicates and problematic matching emails; failures do not substitute older messages.
- Read-only live diagnosis discovered two local Inbox choices. One had no inspected
  items; the populated Inbox scanned 445 items over 30 days and found 10 generic
  `Excel export ... successfully created` subjects. Outlook blocked Body, HTMLBody
  and sender on all 332 recent mail items, so none had a readable link. Version 0.4.1
  now returns those 10 as `content blocked` problem rows instead of falsely showing
  zero. It does not read around the guard; Graph sign-in or saved import is required.
- The four supplied saved emails (two forwarded examples in EML and MSG) matched
  two unique exports. The actual production pipeline followed their Safe Links,
  smaXtec API and exact storage-bucket redirects, downloaded two original XLSX files,
  read two different B3 identities, named each correctly, reported the other two
  messages as duplicates, then resumed the same folder with hash verification.
- Live samples revealed legitimate internal `../comments` and `../drawings` OOXML
  references. The reader now resolves these inside the package while rejecting
  above-root escapes; ZIP member traversal and external/active content remain rejected.
- No original direct email was supplied: direct-mail recognition is synthetically
  verified only. Inline forwards of forwards are recognized by a fully validated
  smaXtec link even when outer sender/subject wording changes. Attached-message
  forwards/RTF-only MSG are unsupported; use a saved standalone message/EML.
  Forwarded arrival time does not renew the stated 24-hour link.
- Output defaults to OS Documents/SmaxTec Workbench/Collections, with Browse and a
  unique folder per collection. SQLite lives in Qt AppLocalDataLocation. Durable state
  stores source hashes, status, B3 and file hashes, never bodies, URLs or remote export
  basenames (which are bearer capabilities too). Resume requires the same ordered
  selection, same user/computer journal and original folder; it never overwrites files.
- Excel is never opened; raw bytes and existing labels remain unchanged. This does
  **not** apply Public. Tenant-approved classification details are required if that
  capability is mandatory. Protected or unsupported workbooks fail visibly.
- B3 is an animal name, not independently verified Animal number/farm/date correlation.
  This milestone does not confirm website date semantics or perform calculations.
- Runtime dependencies include defusedxml, olefile, Windows-only pywin32 and MSAL
  plus its HTTP/crypto transitives; the hash lock and packaging metadata list are
  updated. A full MSG parser was not retained due to distribution licensing/dependency
  scope. The complete production license review remains a release gate.
- Read `EMAIL_COLLECTION.md` and architecture Decisions 009–012 before extending this.

## Repository

- Remote: `https://github.com/FelixvanDijk/SmaxTec.git`
- Branch: `main`, tracking `origin/main`. Foundation implementation: `9fd2c28`.
- No existing application or inherited architecture to preserve.

## Current implementation

- Version 0.7.0 has a primary top-level **Direct data API** tab and preserves the
  earlier website/email UI as **Legacy website + email**. API, browser and email
  workers are independent; close waits for cancellation/session cleanup across all.
- API module map: `ui/api_panel.py` owns account/discovery/queue/review/results;
  `application/api_data.py` owns immutable contracts and DST-safe dates;
  `application/api_downloads.py` owns raw/CSV/XLSX/manifest output; and
  `adapters/smaxtec/api.py` owns fixed-origin bounded HTTP and memory-only token state.
- Implemented a Python/Qt desktop workspace with masked credentials, farm/cow/date
  request controls, progress, cancellation, disconnect, and orderly application close.
- The Playwright adapter opens the supplied entry route, presses `Go to log in`,
  verifies the identity origin/form destination, fills credentials, submits once,
  verifies authenticated navigation markers, and uses an isolated browser for
  serialized farm discovery and an export batch. Subsequent batches reconnect as below.
- Website credentials are in memory only. Export requests, read-only Microsoft 365/
  classic Outlook selection, saved-email import and validated downloads are implemented.
  Graph deployment configuration, canonical API normalization/calculations, graphs and
  anomaly detection remain later work.
- `Start SmaxTec.cmd` in the repository root opens the GUI with the existing local
  `.venv` so the user can test by double-clicking. It installs nothing and applies
  only to a prepared developer working folder, not fresh end-user installations.
- Windows/Python 3.13 hash-pinned dependency lock, offline browser/Qt regression
  tests, a PyInstaller spec with bundled full Chromium, build/smoke scripts, and a
  GitHub Windows CI/artifact workflow are implemented.
- GUI has a dynamically populated farm dropdown, individual cow/From/To rows,
  strict `DD/MM/YYYY` date fields, scrollable review, per-entry progress,
  partial-failure reporting and within-session duplicate prevention.
- The worker now holds a serialized command queue on the browser-owning thread.
  The adapter scans farms after login, selects one exactly, opens Animals, searches
  only Animal number, confirms an exact row, selects Measured data, fills dates and
  submits one export per cow. Independent collection is available in the third GUI card.
- Version 0.2.1 closes the browser after every completed or failed export batch.
  The next reviewed request automatically signs into a fresh isolated browser using
  credentials retained only in worker memory. Farm choices refresh, selected farms
  are preserved, and no-retry fingerprints span the replacement browser sessions.
- Version 0.2.2 replaces the error-prone segmented date editors with strict masked
  `DD/MM/YYYY` fields. Parsed dates are visibly summarized, confirmed before side
  effects, serialized once, and verified exactly in smaXtec before Export is clicked.
- Version 0.3.0 gives every cow its own immutable date range. Add/remove cow rows,
  auto-fold after five, expand into a bounded scrollable list, and optionally Apply
  dates to all with one-step Undo. Hidden rows are included and validated. The same
  cow with different dates remains distinct through reconnection and partial failures.
- Module map: `application/exports.py` defines `CowExport` and batch/result types;
  `ui/cow_editor.py` owns editable rows and folding; `ui/export_review.py` displays
  the complete frozen batch; `ui/widgets.py` shares plain-text and strict date fields.
- Collection module map: `ui/collection_panel.py` and `collection_worker.py` own the
  independent review/worker lifecycle; `application/collection*.py` own contracts,
  orchestration and SQLite state; `adapters/mail/graph.py` owns Microsoft sign-in and
  Graph paging, while the same folder owns the Outlook helper, message parsing and
  bounded downloads; `adapters/workbooks.py` owns read-only ZIP/XML B3 validation.
- Study module map: `application/study_workbook.py` owns hashed collection loading,
  reviewed event/role settings, exact series selection, baseline/proxy calculations,
  automatic exact-pair mapping, single-sheet client table and guided chart/QC generation;
  `ui/study_dialog.py` owns the retained guided event editor and cancellable worker.
  `ui/api_panel.py` owns optional queue T0 entry/review and Results file actions;
  `application/api_downloads.py` invokes the automatic companion after audit output
  publication and isolates its failure from the direct collection.

## Verification and packaging evidence

- 0.10.0 source: **424 offline tests passed** locally on 2026-09-15, including
  automatic companion with/without T0, exact role mapping, client-layout/Analysis
  chart checks, per-cow queue association and derived-output soft failure that
  retains the direct collection. Ruff lint, format, `pip check` and source offline
  smoke pass. Local PyInstaller assembled the complete 0.10.0 Windows bundle,
  but this computer's existing policy again denied `Start-Process` of the unsigned
  executable during packaged smoke (`Access is denied`); the build script cleaned
  its validated temporary stage and did not publish a local archive. No real
  cow-data request or clinical comparison was performed. A clean GitHub Windows
  bundle smoke **and successful artifact upload** are still needed before a
  downloadable 0.10.0 ZIP can be recommended to users.
- 0.9.0 source: all **419 offline tests** passed locally on 2026-09-15. The new
  study tests check numerical client fields, UTC exact-hour selection, aligned
  sheets/valid charts, unmapped roles, source hash/DST, non-overwrite and Qt
  review/short-screen operation and 300-cow row/cohort preservation. Focused
  study/API panel tests passed. Dense 10-minute, long-period hundreds-cow
  performance remains unverified and may exceed the current 3-million-row bound.
  `pip check`, Ruff lint/format and the source app's offline smoke passed. Local
  PyInstaller assembly succeeded, but this development computer's existing
  executable policy denied `Start-Process` of the unsigned bundle during packaged
  smoke; the build script safely removed its temporary stage and did not publish
  a local archive. GitHub clean Windows CI/preview artifact is the required
  independent executable proof. [GitHub Windows run 35019228025](https://github.com/FelixvanDijk/SmaxTec/actions/runs/35019228025)
  for source commit `7bef047` completed all **419 tests**, dependency/lint/format
  checks, bundle build and packaged executable smoke successfully, then failed
  **only** at `upload-artifact`: the repository's Actions artifact storage quota
  was full. No 0.9.0 ZIP was published. On 2026-09-15, after explicit user
  approval, 12 obsolete preview ZIPs were removed; only the latest working 0.8.0
  and 0.7.0 artifacts remain. GitHub says usage recalculation takes 6–12 hours
  after quota changes, so an immediate retry may still fail.
- 0.8.0 source: all **410 tests**, dependency integrity, Ruff, formatting and focused
  API/export/UI checks pass locally. Synthetic workbook regression proves the existing
  measurement sheet and technical columns remain while the summary chart, measurement
  index and data guide are present. The 760×560 UI regression now covers Results actions
  and zero horizontal clipping; themed Browse, Queue and Results renders were inspected
  at presentation dimensions. PyInstaller assembled the complete bundle, but local
  packaged smoke was denied at process launch by the known unsigned-executable policy,
  before archive publication. **GitHub Windows CI passed** for `2fe5845`: clean locked
  install, all checks, bundle build, packaged executable smoke and artifact upload.
  [Verified 0.8.0 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34731198778).
  The [0.8.0 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34731198778/artifacts/10309481262)
  is approximately 288 MiB and retained through 2026-09-27.
- 0.7.0 source: all **410 tests**, dependency integrity, Ruff, formatting and source
  smoke pass locally. Focused direct-collection tests prove the compatible staging file and
  hashed tidy companion contain the same observations; aware timestamps receive correct
  DST-sensitive UTC/local values, while duplicate and ambiguous timestamps are retained
  without inference. **GitHub Windows CI passed** for `5939c51`: clean locked install,
  all checks, bundle build, packaged executable smoke and artifact upload.
  [Verified 0.7.0 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34612732347).
  The [0.7.0 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34612732347/artifacts/10269370832)
  is approximately 288 MiB and retained through 2026-09-25.
- 0.6.1 source: failed-connection regression passes and preserves the exact curated
  sign-in error without launching a second disconnect worker. A status-only live probe
  with a nonexistent diagnostic identity confirmed the JSON auth route responds with
  JSON `401`, establishing that the request format is still accepted without touching
  the user's account or retaining a response body. All **409 tests**, dependency
  integrity, Ruff, formatting and source smoke pass locally. **GitHub Windows CI passed**
  for `4237d12`: clean locked install, all checks, bundle build, packaged executable
  smoke and artifact upload. [Verified 0.6.1 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34605927646).
  The [0.6.1 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34605927646/artifacts/10266586824)
  is approximately 288 MiB and retained through 2026-09-25.
- 0.6.0 source: **408 tests pass** locally. New API UI regressions cover ordinary-click
  multi-selection, filtered/exact selection paths, common-metric intersection, selected-
  row-only assignment, collapsed connected-account controls and short-window scrolling.
  Dependency integrity, Ruff, formatting and source smoke pass. Synthetic themed Browse
  and Queue renders were inspected at the user's short-screen content dimensions; the
  inventory/adaptive queue spacing and independent scrolling no longer overlap controls.
  **GitHub Windows CI passed** for `660f094`: clean locked install, all 408 tests/checks,
  bundle build, packaged Qt/Chromium/API/XLSX/timezone/MSAL/Outlook-helper smoke and
  artifact upload. [Verified 0.6.0 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34559455530).
  The [0.6.0 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34559455530/artifacts/10183887532)
  is approximately 288 MiB and retained through 2026-09-25. Client usability acceptance
  and representative direct downloads remain pending.
- 0.5.1 source: **404 tests pass** locally. A constrained 760×560 API panel proves
  Browse and Queue become vertically scrollable before styled controls are compressed,
  and asserts the table/action/exact-cow/date/measurement/output rows do not overlap.
  Themed Browse and Queue renders were inspected at the user's short-screen content
  dimensions. Dependency integrity, Ruff and source smoke pass. **GitHub Windows CI
  passed** for `99dfd76`: clean locked install, all 404 tests/checks, bundle build,
  packaged Qt/Chromium/API/XLSX/timezone/MSAL/Outlook-helper smoke and artifact upload.
  [Verified 0.5.1 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34555178268).
  The [corrected Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34555178268/artifacts/10182379206)
  is approximately 288 MiB and retained through 2026-09-25.
- 0.5.0 source: **403 tests passed** locally, including API JSON-body
  authentication/redaction, fixed route/query shapes, exact identity, target-specific
  failures, independent dates, DST conversion, bounded chunking, raw-point lineage,
  cancellation/partial retention, hashed manifests, CSV/XLSX output, GUI review and
  primary/legacy tab composition. Dependency integrity, Ruff and source smoke pass.
  Live read-only auth/catalog/metrics evidence is recorded above. PyInstaller assembled
  the API-first bundle from clean temporary staging, but local unsigned EXE launch was
  denied by the existing machine policy, so packaged smoke/archive are not claimed.
  The first GitHub Windows run exposed a missing clean-Windows IANA timezone database;
  `tzdata` is now an explicit locked/bundled runtime dependency and packaged smoke checks
  UK and New Zealand zones. **Replacement GitHub Windows CI passed** for `2bd0edd`:
  locked clean install, all 403 tests/checks, temporary-stage bundle build, packaged
  Qt/Chromium/API/XLSX/timezone/MSAL/Outlook-helper smoke and artifact upload.
  [Verified 0.5.0 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34553441787).
  The [0.5.0 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34553441787/artifacts/10181765281)
  is approximately 288 MiB and retained for 14 days. It remains unsigned and is not a
  production release; representative API downloads and client acceptance remain pending.
- 0.4.1: **384 tests passed** locally (119 seconds), with dependency integrity,
  lint, formatting and source smoke passing. Coverage includes
  system-browser MSAL parameters, memory-only token representation, exact Graph
  endpoint/paging validation, curated HTTP failures, cancellation/disconnect, nested
  inline forwards and protected classic messages. The
  populated classic Inbox was rescanned read-only after the fix: 445 inspected,
  10 recognizable/problem rows, zero ready links because Outlook blocks content.
  No messages were changed and no links/downloads were emitted. A 0.4.1 Windows
  directory bundle and approximately 288 MB archive built locally with MSAL included,
  but this machine again denied execution of the unsigned EXE both in the workspace
  and a fresh temporary folder. **GitHub Windows CI passed** for `0ac21b6`: locked
  install, all checks, executable build, packaged Qt/Chromium/MSAL/Outlook-helper
  smoke and artifact upload. [Verified 0.4.1 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34489046168).
  The [0.4.1 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34489046168/artifacts/10157102934)
  is approximately 288 MiB and retained for 14 days. Live Graph sign-in, app consent,
  signing and clean-client acceptance remain pending; this is not a released build.
- 0.4.0: **366 tests passed** locally (116 seconds), with lint, formatting,
  dependency checks and source smoke passing. Coverage includes direct/forwarded
  parsing, Safe Links, bounds/cancellation, exact newest-N selection, per-file B3,
  real OOXML relationship resolution, file collisions, frozen-selection resume,
  interrupted publication/hash guards, helper IPC and both-worker GUI shutdown.
  **GitHub Windows CI passed** for implementation commit `8886ebe`: locked install,
  regression/lint checks, executable build, Qt/Chromium/parser/COM-helper smoke and upload.
  [Verified 0.4.0 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34443805870).
  [0.4.0 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34443805870/artifacts/10139046476)
  is approximately 282 MiB, retained for 14 days. It remains unsigned; client-machine
  installation/Inbox acceptance and production signing are not proven by this CI run.
  The production sample-download and profile-discovery results above are live verified.
  Native Windows collection UI was visually checked at 1020px minimum width, including
  local received timestamps, a bounded preview and visible status columns. Source smoke
  (Qt, Chromium, XML/OLE parsers, COM-module imports and private helper IPC) passed.
- Version 0.3.0: all **59 tests passed** locally (121 seconds), plus lint, formatting,
  dependency checks and the source Qt/Chromium smoke test. Coverage includes
  individual date preservation, 300-row editing/review, shared-date apply/undo,
  invalid folded rows, cancelled review, real-browser offline submissions,
  reconnection and partial-failure recovery. Native Windows compact, expanded,
  shared-date and review views were visually checked, including 1020px-wide layout.
  No live exports or emails were requested for this change.
- **GitHub Windows CI passed** for the 0.3.0 individual-date editor at `1c961fc`:
  all 59 tests and checks, executable build, bundled Chromium smoke and archive upload.
  [Verified 0.3.0 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34233762511).
- [0.3.0 Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34233762511/artifacts/10059101566):
  approximately 277 MiB and retained for 14 days by CI. Existing unsigned-preview,
  local EXE restriction and clean-client-machine acceptance limits still apply.
- Live verification succeeded twice: initial structure inspection confirmed the
  fields were filled; the implemented adapter then emitted every expected stage
  through `connected`. Both sessions stopped after sign-in, with no export requests.
- GUI was rendered and visually checked on native Windows. Source smoke test
  passed (Qt + Chromium, offline).
- The local double-click launcher was verified from a different working directory:
  it opened a responsive Workbench window. The extra test window was closed while
  preserving the user's already-open preview. No live login was run for this check.
- M2 live read-only verification passed: discovered `Maes Gwyrdd LTD` and
  `TYB Farms LTD`, selected Maes Gwyrdd, opened Animals, matched animal number `57`
  exactly among partial matches, and confirmed the export dialog has two date fields,
  an accessible Measured data choice, and enabled final EXPORT button. The dialog
  was closed with the browser; no real export/email was produced by this check.
- The user's first live export batch succeeded in 0.2.0. A subsequent batch with
  new filters failed with “The website connection ended unexpectedly,” motivating
  the fresh-browser lifecycle in 0.2.1. Consecutive live batches remain to be retested.
- A user reported expecting a 2026 start but receiving 2024 data; their screenshot
  visibly showed `02/09/2024` in the GUI. Automated keyboard entry reproduced that
  Qt's segmented control could retain an old value instead of accepting a complete
  typed replacement. The strict 0.2.2 path is synthetically verified; live output
  date semantics remain to be checked by the user.
- M2 synthetic tests submit full export requests and cover multiple cows, explicit
  measured-data selection, exact/partial/not-found behavior, missing farms, date
  validation, cancellation, partial failure, duplicate exact rows and same-session
  duplicate prevention.
- **GitHub Windows CI passed** for M2 commit `557b010`: all 36 tests and checks,
  executable build, packaged GUI + bundled Chromium smoke, and archive upload.
  [Verified M2 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34133099879).
- [M2 Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34133099879/artifacts/10022998252):
  approximately 276 MiB; retained for 14 days by CI. It is an unsigned preview.
- **GitHub Windows CI passed** for the 0.2.1 repeat-batch fix at `8d3ea91`:
  all 37 tests, executable build, bundled Chromium smoke and archive upload.
  [Verified 0.2.1 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34136225129).
- [0.2.1 Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34136225129/artifacts/10024193848):
  approximately 276 MiB and retained for 14 days by CI.
- **GitHub Windows CI passed** for the 0.2.2 strict-date fix at `75c8a00`:
  all 44 tests, executable build, bundled Chromium smoke and archive upload.
  [Verified 0.2.2 run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34138257607).
- [0.2.2 Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34138257607/artifacts/10024967792):
  approximately 276 MiB and retained for 14 days by CI.
- The Windows executable and full directory bundle were built. On this computer,
  `Start-Process` returned **Access is denied** for the unsigned generated EXE.
  File permissions allow execution; the precise machine policy/cause is not yet
  established. No security controls were changed. This local launch limitation
  remains open; the developer-source GUI does run and was opened for the user.
- **The initial GitHub Windows CI passed** for `9fd2c28`: locked dependency installation,
  all 21 tests, lint/format checks, executable build, packaged GUI + bundled Chromium
  smoke with developer PATH/cache excluded, and preview archive upload.
  [Verified run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34126534604).
- [Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34126534604/artifacts/10020421580):
  approximately 276 MiB download / 623 MiB extracted; retained for 14 days by CI.
  This is an unsigned preview, not a production installer or permanent release.
- CI is an independent bundle execution check, not the final clean-machine/user
  acceptance test. Signing, installer, target-machine restrictions and production
  release gates remain outstanding in `RELEASING.md`.

## Confirmed website information

- Entry: `https://web.smaxtec.com/login?callbackUrl=%2F`
- Entry button: accessible name `Go to log in`.
- Identity form: `input#username` and `input#password`.
- Supplied credentials are private, session-provided information. They must not
  be copied here, into fixtures, into code, or into Git history.
- Identity origin: `https://sso.smaxtec.com`; observed Keycloak realm route:
  `/realms/smaxtec-live/protocol/openid-connect/auth` (query intentionally omitted).
- Submit: `input#kc-login[type=submit]`, accessible name `Sign In`.
- Verified authenticated UI: expected application origin, route outside `/login`
  and `/api/auth`, visible `data-testid="navigationHeader"` and `data-testid="menuItems"`,
  and no visible username input. This was observed on the live account.
- Rejection/challenge selectors follow Keycloak structures and are verified with
  synthetic pages only. No deliberate failed logins or real MFA challenges were
  performed against the live account.
- Navigation/launch calls are bounded to 15 seconds; element waits check cancellation
  every 250 ms; form actions are bounded to 5 seconds. Verification waits 60 seconds,
  or 120 seconds after recognizing a challenge. No automatic login retries.
- Farm switch: visible `[aria-label="Change herd"]` tooltip button; farms:
  `search-modal-list-item`; search modal input: `search-modal-input`.
- Animals navigation uses the current visible `/animals?orgId=…` link rather than
  a stored organisation ID. Animal number search is scoped by `orderByMark`.
- Exact result is read from `animalTable-row` → `mark-link` → `sxText`; row export
  uses its `[aria-label="Export data"]` control. Generated React IDs/classes are ignored.
- Export dialog: two ordered `datePicker` inputs labelled by visible From/To text,
  accessible `Measured data` radio, and exact `EXPORT` button. Live structure was
  confirmed; final click has only been exercised against the synthetic site so far.

## Open questions for later milestones

1. Confirm deployment OS coverage, distribution audience, branding, and signing.
2. Client-test direct API data for representative cows, groups and devices: date boundary
   behavior, units, native/aggregated volume, unavailable sensors and output usability.
3. Obtain owner/IT approval for a public-client Entra application ID with localhost
   redirect and delegated `Mail.Read` in both organisations. Embed that non-secret ID,
   then client-test the legacy Microsoft browser/MFA and newest-N path if it is retained.
   Also confirm enterprise proxies, shared-mailbox needs and classification requirements.
4. Representative sanitized API collections: point shapes, units, timestamps, missing
   intervals, duplicate chunk-boundary behavior and identity reconciliation.
5. Exact calculations, canonical schema, master layout, graph types and controls.
6. Versioned anomaly rules, validation cases, execution schedule and review policy.

## Next-session handover

1. Check the 0.11.0 Git/CI state and packaged launch limitation above. Use
   `docs/DEMO_RUNBOOK.md` for the established API path and retain the earlier
   presentation rollback tag. The prepared source launcher includes the unchanged
   automatic client table, additive aligned cohort sheet and guided study UI; the retained 0.8.0 artifact does not.
   Quota cleanup is complete, but upload success and recalculation are unverified.
2. Read `API_DATA.md` and `CLIENT_STUDY_WORKBOOK.md`. The user's saved real
   collection was checked read-only, then a separate
   `client-analysis-2.xlsx` was generated outside Git; all seven cow rows had
   populated T0/T6/T24, AT6 and RT0/RT24 values. Exact pair names are documented
   above. Run a future small
   collection across adequate prior baseline and later follow-up dates, with a
   known actual treatment/key-event T0 in each queue row. Preserve identifiers
   and data outside Git. Use Results' rebuild action for old collection folders.
3. Compare both `client-analysis.xlsx` sheets and the guided
   `client-study.xlsx` advanced Analysis/alignments/charts/QC against
   the client's example and reviewed manual
   calculations. Ask whether the implemented literal Rback interpretation (first Rl
   to the first later reading at/above Rl) is correct, or whether recovery to Rn or
   another threshold is intended. Confirm
   Talert/R20 proxies and 95% interval interpretation before any clinical use.
4. Exercise a multi-cow/farm collection, unavailable-sensor failure, cancellation,
   longer chunked periods and health KPI. Confirm corporate proxy behavior and report
   performance with hundreds of cows. General canonical master/other studies are
   later M5 work, not covered by this client-example preview.
5. Return to `EMAIL_COLLECTION.md`/Graph deployment only if the legacy route remains
   required after direct API acceptance. No polling or Public assignment is implied.
6. Before distribution beyond development, resolve signing/installation on the
   target computers and pass the gates in `RELEASING.md`.

Always consult the latest Git history and working tree before starting; do not
assume planned items work. No credentials need to be recovered from this repository:
enter an authorized account through the GUI when running the application.
