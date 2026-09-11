# Project instructions for every agent

## Read before working

Read this file, `docs/PROJECT_STATE.md`, and `docs/ARCHITECTURE.md` first. Read
`docs/ROADMAP.md` for the current milestone and its acceptance criteria. These
files are the persistent project memory across sessions and agents.

## Product promise — the highest priority

Deliver a polished, intuitive, plug-and-play desktop application for nontechnical
users. A user downloads/installs the application, opens it, connects their
authorized smaXtec account, and works entirely through the GUI.
They must never need VS Code, Python, a terminal, package installation, browser
driver installation, configuration-file editing, or developer knowledge.
Runtime dependencies and the automation browser belong in the distribution.
Ease of installation and day-to-day use are architecture requirements now, not
cosmetic work deferred until the end. Windows is the initial target; isolate
platform-specific code so other desktop targets remain possible.

## Full intended workflow

1. The GUI collects farm, one or many target identifiers each with its own From/To
   period, measurements, output location, and calculation/report settings.
2. Sign into the official smaXtec Public API, discover authorized farms/cows/groups/
   devices and download selected data directly. Keep website/email collection as a
   compatibility path while direct API acceptance is pending.
3. Preserve raw API responses and provenance, then normalize the data, apply specified
   calculations, and combine
   all selected cows into one master Excel workbook with traceable provenance.
4. Produce the requested complex graphs and analyses from that same normalized
   dataset and configuration, so charts and workbook agree.
5. Later, evaluate API data using agreed, versioned anomaly heuristics;
   automatically select/request relevant data and reuse the SAME download,
   processing, workbook, and analysis pipeline.

Do not invent calculation formulas, thresholds, schemas, email providers,
clinical meanings, or website interactions that have not been established.

## Engineering rules

- Work incrementally against the current milestone. Plan future boundaries, but
  do not implement speculative features or a forest of empty abstractions.
- Keep UI, application orchestration, pure domain logic, and external adapters
  separate. UI code never contains website selectors or spreadsheet formulas.
- Use typed, small modules with explicit responsibilities. Add a seam when it
  serves a real boundary, not merely to add layers.
- Keep blocking browser, email, and file work off the GUI thread. Provide clear
  progress, bounded waits, cancellation, and actionable user-facing errors.
- Keep Playwright objects on their owning worker thread. Use semantic selectors
  and confirmed stable IDs; never depend on generated CSS class names.
- Retry read-only/transient operations deliberately. Never blindly repeat login
  submissions or export requests; duplicates and account lockouts matter.
- Credentials are entered through masked UI controls and kept in memory by
  default. Future optional persistence must use an OS credential vault. Never
  commit credentials, cookies, tokens, real farm data, downloaded workbooks,
  browser traces, authenticated screenshots, or raw website HTML.
- Do not emit raw Playwright exceptions, filled input values, or full callback/
  download URLs in logs or UI. Treat exported links as bearer credentials.
- Use isolated browser contexts. Do not interfere with a user's personal browser.
- Treat cow IDs as strings, preserve source files, record units/timezones and
  lineage, and validate before calculations. Schema and heuristic decisions need
  representative samples and explicit acceptance criteria.
- Never hardcode the contractor's account or assume inbox access alone grants
  access to smaXtec. Website and mailbox authorization are separate concerns.
- Package and exercise the application early. A source-only demo does not prove
  the no-install promise. Clearly distinguish local packaging proof from a signed,
  clean-machine-tested production installer.

## Verification and handover

- Use local, synthetic website fixtures for browser regression tests. Ordinary
  tests and CI must never log into the live site or request exports/emails.
- Exercise success, rejection, changed pages, timeouts, cancellation, and cleanup
  in proportion to the feature. Test business calculations with reviewed fixtures
  once those calculations exist.
- Use `apply_patch` for source/documentation edits. Preserve unrelated user work.
- After each substantial step, update `docs/PROJECT_STATE.md` (what works,
  verification, limitations, exact next step) and `CHANGELOG.md`. Update
  `docs/ARCHITECTURE.md` and decisions when boundaries or dependencies change.
- Record decisions and reasons, including alternatives and revisiting triggers.
  Distinguish planned, implemented, locally tested, live verified, and released.
- The user authorizes commits and GitHub pushes after major steps. Review staged
  changes for secrets/data and run relevant checks before committing. Do not
  overwrite remote history. Report a push failure honestly.
- Keep installation instructions for end users separate from developer setup.
  Do not call this production-ready until the release acceptance gates pass.

## Current scope

Version 0.7.0 makes the official smaXtec Public API v2 the primary workspace. Read
`docs/API_DATA.md` before changing it. The UI dynamically discovers authorized farms,
cows, groups, devices and per-target metrics; queues immutable target/From/To/metric
combinations; explicitly reviews them; and downloads bounded JSON chunks into one
unique collection with CSV, optional XLSX, SHA-256 provenance and optional documented
farm health index. Credentials/tokens remain in memory. Only the fixed API origin and
read endpoints are allowed; redirects, raw errors and mutation/emailed-report routes
are excluded. A 400 while discovering one target's metrics is a target availability
failure, not an automatic account failure. Preserve Animal numbers as strings and use
exact equality. Convert whole farm-local reviewed days once into auditable half-open UTC
bounds, including DST, and retain both local dates and every API chunk boundary. Do not
silently deduplicate boundary points: API To-date inclusivity is not documented.
Raw response shapes win over guessed schemas. Do not invent metric meanings, preferred
units, transformations, event timestamp units or clinical interpretations. Events and
server-side background download jobs remain withheld until their semantics/lifecycle
are confirmed. Browse is for target identity and dates; measurement assignment belongs
in Download queue. Ordinary clicks toggle row selection without Ctrl, while filtered
bulk selection and exact-number paste are equivalent paths. Metric discovery operates
on the frozen selected queue targets, exposes only common codes, and is invalidated if
that selection changes. Applying metrics changes selected rows only; “all available” is
per target. Each API workflow page must scroll vertically before Qt compresses styled
controls below their size hints; short displays must never overlap or clip input, table,
action or option rows. A failed connection must preserve its curated authentication,
permission, network or response error; cleanup must never replace it with a successful
Disconnect message. Source 0.7.0 has synthetic verification and packaged Windows CI proof;
the underlying API path has read-only live auth/catalog/metric-discovery evidence.
Representative direct downloads and client acceptance remain pending. Direct collections
preserve the compatible
`measurements.csv` audit table and also create `analysis_ready.csv` from the same rows.
The tidy companion never deduplicates, pivots, converts units, coerces values or guesses
ambiguous timestamps. The next milestone is canonical normalization/calculations,
then graphs, using these preserved raw collections.

The previous website and email implementation remains under **Legacy website + email**
as a compatibility path; email work is paused, not deleted. Its constraints follow.

Milestones 1 and 2 implement login plus farm/cow/date selection and measured-data
export requests. Version 0.3.0 adds individual dates per cow; client acceptance of
this editor and live export dates remains pending. Each
login scans the account's current farm list. Cow lookup must use the Animal number
column and exact equality; a search for `57` must never select `657` or `257`.
Each cow is submitted separately after an explicit GUI review. Never retry an
ambiguous final export click. After a batch, close its browser; reconnect lazily
for the next reviewed batch using credentials held only in worker memory until
disconnect/close. Preserve attempted-export guards across those fresh browsers.
Dates must follow one auditable path: strict `DD/MM/YYYY` GUI input, real calendar
validation, immutable date values, explicit confirmation, one serialization, and
exact website-field verification before Export. Each immutable `CowExport` carries
its number and dates together through requests, results, errors and duplicate guards.
Never restore a single batch-wide range. Folding changes visibility only: validate
and include every row. Shared dates apply only on an explicit Apply to all action.
Review must list every unique cow/period; the same cow with another period is distinct.
M3 email collection began in runtime 0.4.0; 0.4.1 adds the preferred Microsoft 365
Graph connector and protected/nested-forward fixes. Consult `docs/PROJECT_STATE.md`
for its current verification/release evidence and read `docs/EMAIL_COLLECTION.md`
before changing it. Graph uses delegated `Mail.Read`, system-browser MSAL/MFA and
memory-only tokens; an approved public-client app ID/localhost redirect and tenant
consent are deployment prerequisites, not ordinary user configuration. Never add a
mailbox password, client secret, copied-token prompt, Outlook Web scraping or consent
bypass. Classic Outlook remains a bounded-helper fallback and may surface protected
messages without readable links; saved `.eml`/`.msg` import remains available.
Treat an Inbox scan whose relevant messages are all `content blocked` as a failed
acceptance route, not partial success. Persistently prioritize activating the centrally
approved Graph registration and consent in that environment; administrative controls
are deployment constraints to resolve with the application owner, never controls to
disable, evade, or conceal from the client.
Keep inboxes read-only; freeze the newest-N matching selection including duplicates
and problematic messages, without topping up. Preserve accepted workbook bytes.
Validate every redirect through the confirmed Safe Links/smaXtec/exact-bucket route.
The remote export object name itself is a bearer capability: never persist it,
even as an "original filename". Keep only irreversible link hashes, source keys,
received times, verified local filenames/B3 identity and file hashes in provenance.
Retry/resume only the same reviewed selection and verify completed file hashes;
never overwrite or automatically request replacement website exports. Resume uses
the same user/computer's journal; new collections are not globally deduplicated.
B3 animal name alone does not prove the requested Animal number, farm or dates.
Excel is not opened and labels remain unchanged; Public assignment is not implemented.
Analysis remains later work.

No additional agents are required by this file. Delegate only if the user or
applicable higher-priority instructions explicitly authorize parallel agents.
