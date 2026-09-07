# Project state — start here each session

Last updated: 2026-09-07. **M1 — foundation and website login: complete.**
Next: M2, awaiting the user's farm/cow navigation instructions.

## User intent and scope

Build a beautifully packaged, plug-and-play desktop product for nontechnical
users. Full workflow: GUI farm/cow/time/report inputs → smaXtec exports → email
links → individual Excel downloads → one calculated/formatted master workbook →
graphs/analysis. Later, agreed anomaly heuristics select cows/periods and feed the
same pipeline automatically. Modularity and documentation across sessions matter.

The user explicitly wants incremental delivery, starting with login only, and
authorizes GitHub pushes after substantial milestones. Do not advance into export
requests, email access, or farm/cow selection during the first increment.

## Repository

- Remote: `https://github.com/FelixvanDijk/SmaxTec.git`
- Branch: `main`, tracking `origin/main`. Foundation implementation: `9fd2c28`.
- No existing application or inherited architecture to preserve.

## Current implementation

- Implemented a Python/Qt desktop sign-in screen with masked credentials, progress,
  a responsive worker, cancellation, disconnect, and orderly application close.
- The Playwright adapter opens the supplied entry route, presses `Go to log in`,
  verifies the identity origin/form destination, fills credentials, submits once,
  and verifies authenticated navigation markers. It then keeps the browser open
  until disconnect/browser close/application close. It performs no farm selection.
- Credentials are in memory only. No session persistence, mailbox access, exports,
  downloaded files, workbook calculations, graphs or anomaly detection yet.
- `Start SmaxTec.cmd` in the repository root opens the GUI with the existing local
  `.venv` so the user can test by double-clicking. It installs nothing and applies
  only to a prepared developer working folder, not fresh end-user installations.
- Windows/Python 3.13 hash-pinned dependency lock, offline browser/Qt regression
  tests, a PyInstaller spec with bundled full Chromium, build/smoke scripts, and a
  GitHub Windows CI/artifact workflow are implemented.

## Verification and packaging evidence

- 21 local tests passed; lint/format and dependency checks passed.
- Live verification succeeded twice: initial structure inspection confirmed the
  fields were filled; the implemented adapter then emitted every expected stage
  through `connected`. Both sessions stopped after sign-in, with no export requests.
- GUI was rendered and visually checked on native Windows. Source smoke test
  passed (Qt + Chromium, offline).
- The local double-click launcher was verified from a different working directory:
  it opened a responsive Workbench window. The extra test window was closed while
  preserving the user's already-open preview. No live login was run for this check.
- The Windows executable and full directory bundle were built. On this computer,
  `Start-Process` returned **Access is denied** for the unsigned generated EXE.
  File permissions allow execution; the precise machine policy/cause is not yet
  established. No security controls were changed. This local launch limitation
  remains open; the developer-source GUI does run and was opened for the user.
- **GitHub Windows CI passed** for `9fd2c28`: locked dependency installation,
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

## Open questions for later milestones

1. Confirm deployment OS coverage, distribution audience, branding, and signing.
2. Actual farm/cow navigation, identifier meanings, date controls, export limits.
3. Inbox provider and delegated/shared mailbox behavior; sender/correlation fields
   from sanitized example export emails; approved download hosts/link lifetime.
4. Representative sanitized Excel files: schema, units, timezones, missing values.
5. Exact calculations, workbook layout, graph types, and configuration controls.
6. Versioned anomaly rules, validation cases, execution schedule and review policy.

## Next-session handover

1. Check current Git/CI state and the packaged launch limitation above.
2. Continue with M2 only when the user supplies the next farm/cow selection step:
   inspect the navigation in the authorized account, agree selection identifiers
   and date semantics, then extend the owning worker without moving selectors into UI.
3. Reuse `SmaxtecLoginSession` for the browser boundary. The current worker stays
   alive to preserve the session but has no command queue yet; introduce a small
   serialized worker command mechanism when adding actual farm/export actions.
4. Request sanitized email/Excel examples when reaching the relevant milestone;
   do not select an inbox provider or invent schemas early.
5. Before distribution beyond development, resolve signing/installation on the
   target computers and pass the gates in `RELEASING.md`.

Always consult the latest Git history and working tree before starting; do not
assume planned items work. No credentials need to be recovered from this repository:
enter an authorized account through the GUI when running the application.
