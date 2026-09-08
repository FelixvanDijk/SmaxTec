# Project state — start here each session

Last updated: 2026-09-08. **0.3.0 individual cow/date editor verified locally and packaged on Windows CI.**
Next: client verifies individual periods and compact/expanded editing, then M3 email collection.

## User intent and scope

Build a beautifully packaged, plug-and-play desktop product for nontechnical
users. Full workflow: GUI farm/cow/time/report inputs → smaXtec exports → email
links → individual Excel downloads → one calculated/formatted master workbook →
graphs/analysis. Later, agreed anomaly heuristics select cows/periods and feed the
same pipeline automatically. Modularity and documentation across sessions matter.

The user explicitly wants incremental delivery and authorizes GitHub pushes after
substantial milestones. M1 was login; M2 is farm/cow/date selection and export
requests. Do not begin mailbox access or spreadsheet processing before its milestone.

## Repository

- Remote: `https://github.com/FelixvanDijk/SmaxTec.git`
- Branch: `main`, tracking `origin/main`. Foundation implementation: `9fd2c28`.
- No existing application or inherited architecture to preserve.

## Current implementation

- Implemented a Python/Qt desktop workspace with masked credentials, farm/cow/date
  request controls, progress, cancellation, disconnect, and orderly application close.
- The Playwright adapter opens the supplied entry route, presses `Go to log in`,
  verifies the identity origin/form destination, fills credentials, submits once,
  verifies authenticated navigation markers, and uses an isolated browser for
  serialized farm discovery and an export batch. Subsequent batches reconnect as below.
- Credentials are in memory only. Export requests are implemented; session persistence,
  mailbox access, downloaded files, workbook calculations, graphs and anomaly detection
  are not implemented yet.
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
  submits one export per cow. Email retrieval remains unimplemented.
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

## Verification and packaging evidence

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
2. Confirm individual-period 0.3.0 requests, compact/expanded editing and consecutive
   batches without credential re-entry; check email counts and inclusive date semantics.
3. Inbox provider and delegated/shared mailbox behavior; sender/correlation fields
   from sanitized example export emails; approved download hosts/link lifetime.
4. Representative sanitized Excel files: schema, units, timezones, missing values.
5. Exact calculations, workbook layout, graph types, and configuration controls.
6. Versioned anomaly rules, validation cases, execution schedule and review policy.

## Next-session handover

1. Check current Git/CI state and the packaged launch limitation above.
2. Record the client's per-cow-date result: individually reviewed periods, folded
   row editing, automatic reconnection, workbook boundaries and email timing without
   committing credentials, message links, personal data or source workbooks.
3. Begin M3 from the existing `SessionWorker`/`SmaxtecLoginSession` boundary. Add
   persistent job/correlation state before automated retries or inbox polling.
4. Request sanitized email/Excel examples when reaching the relevant milestone;
   do not select an inbox provider or invent schemas early.
5. Before distribution beyond development, resolve signing/installation on the
   target computers and pass the gates in `RELEASING.md`.

Always consult the latest Git history and working tree before starting; do not
assume planned items work. No credentials need to be recovered from this repository:
enter an authorized account through the GUI when running the application.
