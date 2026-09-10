# Developer setup

These instructions are for contributors only. End users receive a bundled desktop
application and must never be sent here to install runtime dependencies.

Use Windows x64 and Python 3.13 for the current verified toolchain. The package
declares Python 3.12–3.13; the checked-in dependency lock targets Windows/Python
3.13. Re-resolve and verify a separate lock before claiming another target works.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
$env:PLAYWRIGHT_BROWSERS_PATH = '0'
.\.venv\Scripts\python.exe -m playwright install --no-shell chromium
.\.venv\Scripts\python.exe -m smaxtec
```

Run module entry points through the environment's Python; activation is optional.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m smaxtec --smoke-test
```

Tests run an HTTP site on an ephemeral loopback port with synthetic credentials.
They do not call smaXtec, Outlook or request emails. Collection tests use synthetic
COM objects, mail messages, network responses and workbook packages. Qt tests run
offscreen. The smoke test opens the application and bundled Chromium against
in-memory content, verifies XML/OLE/Windows COM imports, and exercises private helper
IPC with an invalid action rejected before mailbox access. Live checks stay opt-in.

## Dependency changes

Change `pyproject.toml`, regenerate the hash-pinned lock on the supported target,
then reinstall, test and rebuild. Check Playwright's Chromium revision and repeat
the packaged browser smoke test whenever Playwright changes. Build backend and
lock must agree on the setuptools version.

M3 uses `olefile` for a deliberately narrow MSG root-stream reader, `defusedxml`
for XLSX XML and Windows-only `pywin32` for classic Outlook. No full MSG/RTF parser,
Excel installation, Graph app or mailbox password is needed for saved-email import.
Keep third-party notices in the bundle when changing these dependencies.

```powershell
.\.venv\Scripts\python.exe -m piptools compile --extra dev --generate-hashes --strip-extras --allow-unsafe --output-file requirements-dev.lock pyproject.toml
```

## Opt-in live verification

Only use the following when the current task authorizes real account sign-in.
Credentials are masked prompts, never command-line arguments or `.env` files.

```powershell
.\.venv\Scripts\python.exe scripts/check_login.py
```

It verifies the login, prints stage identifiers only, and closes the session.
`--headless` is available for a known account flow without human verification.
It does not select farms/cows, request exports, or access a mailbox. Never run it
in CI or loop failed authentication attempts. Do not enable Playwright debug
traces while handling real credentials.

## Handover discipline

Read `AGENTS.md` and the current state before edits. Update state, decisions,
changelog and tests as behavior changes. Keep private observations out of Git;
record stable selector names and structural behavior, not account/farm content.
