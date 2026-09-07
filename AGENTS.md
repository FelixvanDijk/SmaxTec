# Project instructions for every agent

## Read before working

Read this file, `docs/PROJECT_STATE.md`, and `docs/ARCHITECTURE.md` first. Read
`docs/ROADMAP.md` for the current milestone and its acceptance criteria. These
files are the persistent project memory across sessions and agents.

## Product promise — the highest priority

Deliver a polished, intuitive, plug-and-play desktop application for nontechnical
users. A user downloads/installs the application, opens it, connects their
authorized website and email accounts, and works entirely through the GUI.
They must never need VS Code, Python, a terminal, package installation, browser
driver installation, configuration-file editing, or developer knowledge.
Runtime dependencies and the automation browser belong in the distribution.
Ease of installation and day-to-day use are architecture requirements now, not
cosmetic work deferred until the end. Windows is the initial target; isolate
platform-specific code so other desktop targets remain possible.

## Full intended workflow

1. The GUI collects farm, date/time period, one or many cow identifiers, output
   location, and user-defined calculation/report settings.
2. Sign into smaXtec and navigate the authorized farm/cow/export workflow.
3. Request exports, which produce emails containing Excel download links.
4. Match incoming emails to the correct request, securely download individual
   workbooks, and handle delayed, duplicated, missing, or expired messages.
5. Validate and normalize the data, apply specified calculations, and combine
   all selected cows into one master Excel workbook with traceable provenance.
6. Produce the requested complex graphs and analyses from that same normalized
   dataset and configuration, so charts and workbook agree.
7. Later, evaluate website data using agreed, versioned anomaly heuristics;
   automatically select/request relevant exports and reuse the SAME download,
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

Milestone 1: establish the repository and desktop foundation; open the supplied
login URL, press **Go to log in**, and fill the username/password fields. Verify
authenticated entry if the login flow allows it, then stop before farm/cow
selection. Export requests, email access, downloads, and analysis are later work.

No additional agents are required by this file. Delegate only if the user or
applicable higher-priority instructions explicitly authorize parallel agents.
