# Packaging and release

## Development preview

```powershell
./scripts/build_windows.ps1
```

The build runs checks, bundles the application with Chromium, starts the executable
with Python removed from PATH and an unavailable external browser cache, and
produces `dist/SmaxTec-Workbench-0.9.0-windows-x64.zip`.
Assembly uses a fresh validated system-temporary staging directory, smoke-tests that
exact bundle, then publishes only the versioned ZIP. This avoids stale files and does
not require replacing an older OneDrive-synchronized `dist/SmaxTec Workbench` folder.
The spec includes distribution metadata/license notices for olefile, defusedxml,
pywin32, MSAL and its direct/transitive runtime dependencies. This does not replace
the product-wide license inventory/release review.

Unzip the complete folder and open `SmaxTec Workbench.exe`; `_internal` must stay
beside it. `START_HERE.txt` explains the preview in user terms. The binary/archive
are generated artifacts; never commit them to the source repo. CI uploads the
archive as a temporary build artifact, not a published production release.

For a rebuild immediately after the same source passed its checks, `-SkipChecks`
avoids duplicating tests. `-SkipArchive` builds/smoke-tests without making a ZIP.
Build on Windows; PyInstaller does not make another platform's binaries from a
single build host. Only full Chromium is shipped; its headless mode runs the
offline smoke test. Browser updates require rebuilding the application.

The 0.9.0 smoke resolves representative IANA farm timezones and imports the direct XLSX
writer plus email/XML/MSAL parsers and Windows COM runtime modules without creating
Outlook. It checks private helper IPC with an invalid action rejected before
the helper imports COM or accesses Outlook. It does not prove a
configured Graph registration/consent, permitted COM access or live downloads. The helper uses
the same bundled executable via `--outlook-helper`; users do not install Python or pywin32.
Classic Outlook itself must already be installed/configured for automatic inbox access.
New-Outlook/Outlook-Web users use the Graph connector after the release's Entra app is
approved, or saved-email import. Workbench does not bypass corporate account, consent,
programmatic-access or link-protection policies.

## Production release gates — still outstanding

- Confirm supported Windows versions/architectures and minimum hardware with the
  user; test on a clean standard-user machine without Python, VS Code, Node,
  Playwright, or a development browser cache.
- Provide a polished installer, shortcuts, application icon/branding, version
  metadata, upgrades and uninstall. Preserve user jobs/settings through upgrades.
- Choose code-signing and distribution ownership; sign and timestamp binaries
  and installer and verify downloaded artifacts and checksums.
- Include an inventory of bundled dependencies and required third-party notices.
  Review the Qt distribution/licensing choice before external distribution; do
  not assign an open-source license to this contracted project's code without
  the owner's instruction.
- Include `olefile` (BSD), `defusedxml` (PSF), `pywin32` (PSF), MSAL (MIT), requests,
  PyJWT, cryptography, cffi, charset-normalizer, idna, urllib3, certifi and XlsxWriter
  (BSD-2-Clause), plus `tzdata` (Apache-2.0), alongside
  Qt, Playwright and Chromium in that inventory, checking exact locked versions and
  bundled transitive notices. A minimal OLE MSG reader replaced the initially
  considered GPL full-MSG dependency; verify removed packages do not remain in the
  final distribution. This inventory note is not a legal compatibility determination.
- Test scaling, keyboard navigation, contrast, long names, screen sizes, and user
  comprehension with nontechnical users; provide support and recovery instructions.
- Validate account onboarding, mailbox authorization, enterprise proxy behavior,
  offline/errors, cancellation, shutdown, and upgrade behavior on actual targets.
- Exercise direct API sign-in, farm/target/metric discovery, representative native and
  aggregated periods, DST/date boundaries, large queues, partial failure and output on
  a standard-user client. Confirm data retention and classification expectations.
- Register/approve the production public-client Entra application, localhost redirect
  and delegated `Mail.Read` in every supported tenant. Embed its non-secret app ID,
  verify publisher/consent presentation and confirm disconnect/upgrade token handling.
- Establish redacted diagnostic export, retention rules, output backups and atomic
  writes as soon as real job/data storage is introduced.
- Exercise collection from direct and inline-forwarded mail in both organisations,
  Safe Links and enterprise proxies, classic Outlook prompts, saved `.eml`/`.msg`,
  cancellation and same-user restart recovery. Confirm accepted labeling policy:
  current collection preserves original labels and does not assign Public.

A successful local smoke test is evidence that the bundle works on the development
computer. It is not evidence that a signed, production-ready installer or clean
machine acceptance test exists.

## M1 evidence and machine limitation

The [first Windows CI run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34126534604)
passed all checks, built the executable, ran its offline smoke test with developer
PATH and external browser cache excluded, and uploaded the archive (about 276 MiB;
the extracted directory bundle is about 623 MiB). GitHub's artifact download wraps
the application ZIP in another ZIP; extract the inner application ZIP as well.

The local development computer returned `Access is denied` when starting the
generated unsigned executable. File permissions appear to allow execution; the
specific policy/cause is unconfirmed. Source-mode Qt and live browser automation
work. Do not disable security controls to work around this; resolve the target
distribution/signing requirements before external rollout. The independent CI
smoke result is useful evidence, but does not resolve this machine's restriction.

## M2 evidence

The [M2 Windows CI run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34133099879)
passed 36 tests and all checks, built version 0.2.0, ran the packaged GUI/browser
smoke test, and uploaded the approximately 276 MiB
[Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34133099879/artifacts/10022998252).
The same unsigned-preview and clean-target-machine limitations above still apply.

The [0.2.1 repeat-batch run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34136225129)
subsequently passed 37 tests, rebuilt the application with the fresh-browser
reconnection fix, passed the bundled-browser smoke test, and uploaded its
[Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34136225129/artifacts/10024193848).

The [0.2.2 strict-date run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34138257607)
passed 44 tests, rebuilt and smoke-tested the bundled application, and uploaded
its [Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34138257607/artifacts/10024967792).

The [0.3.0 individual cow/date run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34233762511)
passed 59 tests and checks, rebuilt and smoke-tested the bundled application, and
uploaded its approximately 277 MiB
[Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34233762511/artifacts/10059101566).
Client acceptance of individual periods and expanded/compact editing remains pending;
the synthetic tests do not establish live workbook date-boundary semantics.

## M3 evidence

Version 0.4.1 passes 384 local tests plus dependency/lint/format/source smoke checks.
Its Windows directory bundle and approximately 288 MiB archive build with MSAL and
transitives included. This development machine still denies execution of the unsigned
EXE from both the OneDrive workspace and a fresh temporary directory, so local packaged
smoke is not claimed. The independent [0.4.1 Windows CI run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34489046168)
passed locked installation, checks, executable build, packaged smoke and uploaded the
[temporary preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34489046168/artifacts/10157102934).
Entra app configuration/consent and live Graph acceptance remain pending.

The [0.4.0 email collection run](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34443805870)
passed the locked install, regression and code checks, built the executable and passed
the packaged Qt/Chromium/parser/COM-helper smoke. The approximately 282 MiB
[Windows preview artifact](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34443805870/artifacts/10139046476)
is retained for 14 days. Local verification passed 366 tests and collected the two
provided forwarded-message samples through the production pipeline with independent
B3 naming, duplicate detection and hash-verified resume. No Outlook/Excel installation
was used by CI to open an actual mailbox or workbook: COM-module import and private
helper IPC were tested without creating Outlook. Configured profile, corporate policy,
Inbox access, signing and clean-client-machine acceptance remain separate gates.

## 0.9.0 client-study preview evidence

On 2026-09-15 all 415 offline tests, dependency/lint/format checks and the source
app's smoke passed locally. PyInstaller assembled the updated bundle, but this
development computer again refused to launch its unsigned executable for packaged
smoke; the staging folder was cleaned without publishing a local archive. Clean
[GitHub Windows run 35019228025](https://github.com/FelixvanDijk/SmaxTec/actions/runs/35019228025)
for source commit `7bef047` passed the locked install, all 419 tests, dependency/
lint/format checks, bundle build and packaged executable smoke. `upload-artifact`
then failed because the repository's Actions artifact storage quota is full.
Fourteen older temporary preview ZIPs total roughly 4 GiB and remain intact
pending user direction; no 0.9.0 artifact link should be advertised yet. GitHub
warns quota usage may take 6–12 hours to recalculate after deletion or other
storage changes. Retain the source rollback tag and do not confuse a built runner
bundle with a downloadable, signed production installer.
This only proves bundling/offline startup, not target-machine signing, real API
source mapping or client acceptance of the study calculations/charts.

## M4 direct API evidence

Version 0.8.0 preserves the 0.7.0 API request/CSV/manifest behavior and adds only
presentation-safe GUI/output improvements. All 410 tests plus dependency, lint and format
checks pass locally. Its complete bundle assembles locally, but this development computer
still denies unsigned executable launch. GitHub Windows CI passed the clean locked install,
all checks, bundle build, packaged executable smoke and artifact upload for
[`2fe5845`](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34731198778). The
approximately 288 MiB [0.8.0 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34731198778/artifacts/10309481262)
is retained through 2026-09-27. Client data acceptance remains pending.

Version 0.7.0 preserves the format-1 staging CSV columns and adds a tidy, hashed
`analysis_ready.csv` through collection manifest format 2. Focused synthetic tests cover
DST-aware local/UTC derivation, duplicate retention and non-inference for ambiguous
timestamps. All 410 local tests, dependency, lint, format and source smoke checks pass;
GitHub Windows CI passed clean packaging, packaged executable smoke and artifact upload
for [`5939c51`](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34612732347).
The approximately 288 MiB [0.7.0 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34612732347/artifacts/10269370832)
is retained through 2026-09-25. Client data acceptance remains pending.

Version 0.6.1 fixes connection failures being overwritten by a successful Disconnect
message. Its focused lifecycle regression and a status-only live JSON-auth route probe
pass. All 409 tests, dependency, lint, format and source smoke checks pass locally;
GitHub Windows CI passed the clean build and packaged executable smoke for
[`4237d12`](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34605927646). The
approximately 288 MiB [0.6.1 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34605927646/artifacts/10266586824)
is retained through 2026-09-25.

Version 0.6.0 passes 408 offline tests plus dependency, lint, format and source smoke
checks. Its queue-first multi-selection and metric-assignment UI has synthetic short-
window and state regressions plus themed visual inspection. GitHub Windows CI passed
the clean locked install, tests/checks, bundled executable smoke and artifact upload for
[`660f094`](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34559455530). The
approximately 288 MiB [0.6.0 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34559455530/artifacts/10183887532)
is retained through 2026-09-25. Client usability acceptance remains pending.

Version 0.5.1 passes 404 offline tests plus dependency, lint, format and source smoke
checks. An authorized read-only live check confirmed direct authentication, membership,
farm catalogue and metric discovery; no data mutation or emailed export was requested.
PyInstaller assembled the API-first bundle, including XlsxWriter and its metadata, in
fresh temporary staging. This development machine again denied execution of the unsigned
EXE with `Access is denied`, so local packaged smoke/archive publication is not claimed.
GitHub Windows CI passed the clean locked install, tests/checks, bundled executable smoke
and artifact upload for [`99dfd76`](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34555178268).
The approximately 288 MiB [0.5.1 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34555178268/artifacts/10182379206)
is retained through 2026-09-25. This proves packaging, not client-machine acceptance.
Representative direct measurement downloads, client boundary/unit review, code signing,
installer and clean standard-user-machine acceptance remain pending.
