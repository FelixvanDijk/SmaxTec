# Packaging and release

## Development preview

```powershell
./scripts/build_windows.ps1
```

The build runs checks, bundles the application with Chromium, starts the executable
with Python removed from PATH and an unavailable external browser cache, and
produces `dist/SmaxTec-Workbench-0.1.0-windows-x64.zip`.

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
