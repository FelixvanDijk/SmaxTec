# Packaging and release

## Development preview

```powershell
./scripts/build_windows.ps1
```

The build runs checks, bundles the application with Chromium, starts the executable
with Python removed from PATH and an unavailable external browser cache, and
produces `dist/SmaxTec-Workbench-0.3.0-windows-x64.zip`.

Unzip the complete folder and open `SmaxTec Workbench.exe`; `_internal` must stay
beside it. `START_HERE.txt` explains the preview in user terms. The binary/archive
are generated artifacts; never commit them to the source repo. CI uploads the
archive as a temporary build artifact, not a published production release.

For a rebuild immediately after the same source passed its checks, `-SkipChecks`
avoids duplicating tests. `-SkipArchive` builds/smoke-tests without making a ZIP.
Build on Windows; PyInstaller does not make another platform's binaries from a
single build host. Only full Chromium is shipped; its headless mode runs the
offline smoke test. Browser updates require rebuilding the application.

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
- Test scaling, keyboard navigation, contrast, long names, screen sizes, and user
  comprehension with nontechnical users; provide support and recovery instructions.
- Validate account onboarding, mailbox authorization, enterprise proxy behavior,
  offline/errors, cancellation, shutdown, and upgrade behavior on actual targets.
- Establish redacted diagnostic export, retention rules, output backups and atomic
  writes as soon as real job/data storage is introduced.

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
