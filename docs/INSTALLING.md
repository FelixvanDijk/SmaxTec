# Install SmaxTec Workbench on Windows

This page is for end users. You do not need Python, VS Code, browser drivers or an
administrator account for the default per-user installation.

## Install a reviewed build

1. Obtain `SmaxTec-Workbench-Setup-<version>-windows-x64.exe` from the release owner or
   approved organisation software location. Do not use GitHub's **Code > Download ZIP**;
   that is developer source code.
2. If a `.sha256` file is supplied, your support or IT contact can use it to confirm the
   installer arrived unchanged.
3. Close an older SmaxTec Workbench window, then open the installer.
4. Keep **Install for me only** unless your IT department directs otherwise. This is the
   default and does not require administrator rights.
5. Optionally select the desktop shortcut and finish the installer.
6. Open **SmaxTec Workbench** from the Start menu.

The application runtime, supported libraries and isolated Chromium browser are included.
Keep downloaded farm data in an approved user or organisation folder, not the installation
folder.

After installation, **Getting started** in the Workbench Start-menu folder opens the
included quick-start guide. **Third-party notices** opens the bundled notice and inventory
information. An internet connection and your authorised smaXtec account are required for
data collection. Outlook is not required for the Direct data API workspace.

The client-test installer can be shared as a single `.exe` through your organisation's
approved OneDrive/SharePoint location. A private GitHub release requires repository access;
ask the person supplying the installer for an organisation download link if needed.

## Update

Close Workbench and run the newer reviewed installer. Its stable application identity
updates the existing installation rather than creating an unrelated second product.
Output collections selected elsewhere on the computer are not installation files and are
not removed by an update.

## Uninstall

Open **Windows Settings > Apps > Installed apps**, find **SmaxTec Workbench**, and choose
**Uninstall**. The uninstaller removes installed program files and shortcuts. It does not
delete collection/output folders that the user chose elsewhere.

## Current preview warning

The installer pipeline exists, but the current installer and bundled application are an
**unsigned preview** until the release owner supplies an organisation-controlled
code-signing identity and completes clean-machine acceptance. Corporate Windows policy may
block an unsigned preview. Do not disable security controls; use an approved/signed build
supplied by the release owner.

## Getting help

Record the Workbench version, Windows version, operation being attempted and the exact
user-facing error. Never send passwords, access tokens, bearer download links or raw farm
data through an unapproved support channel.
