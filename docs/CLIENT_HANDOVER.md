# Send the client this installer

Ready on 2026-10-15: [client-test release v0.14.2-client-preview.1](https://github.com/FelixvanDijk/SmaxTec/releases/tag/v0.14.2-client-preview.1).
The verified files are also on this development computer under
`dist/client-handover/v0.14.2-client-preview.1/`. Every local file matches its published
GitHub SHA-256 digest. The installer is 209,388,457 bytes (about 209 MB).

Send these two files from that folder:

- `SmaxTec-Workbench-Setup-0.14.2-windows-x64.exe`
- `SmaxTec-Workbench-Quick-Start.html` (optional; also installed automatically)

Installer SHA-256 for the support record:
`fc06bf6239c7285724612360786a3fc1e6d86e90614b746f3a877cac73db2389`.
[Windows verification and release publication passed](https://github.com/FelixvanDijk/SmaxTec/actions/runs/38770624949).

The client-test package is built from the unchanged 0.14.2 application. Send the exact
verified **SmaxTec-Workbench-Setup-0.14.2-windows-x64.exe**, optionally accompanied by
**SmaxTec-Workbench-Quick-Start.html**. The same guide is installed with the application.
The client needs Windows x64, internet access and an authorised smaXtec account. Python,
VS Code, Outlook and browser-driver installation are unnecessary for Direct data API.

## Release owner

1. Open the versioned **client-test** GitHub prerelease and download its Setup executable,
   checksum and Quick Start. Do not use a source ZIP or an expired Actions artifact.
2. Put the unchanged executable and guide in an approved organisation OneDrive/SharePoint
   folder, grant the intended recipients access, and send that link. The repository is
   private; ordinary clients cannot use its release URL without repository access.
3. Keep the `.sha256`, dependency inventory, release tag/source commit and successful
   Actions URL with the support record. Every published preview gets a new tag; never
   replace an existing preview's executable silently.
4. The release is an **unsigned client-test preview**. If the organisation blocks it,
   arrange approved deployment/signing with its IT owner. A final signed rollout and a
   clean standard-user client acceptance test remain outstanding.

## Suggested message

> Please download and open the SmaxTec Workbench Setup installer from the shared folder.
> Choose “Install for me only”, finish setup and open SmaxTec Workbench from the Start menu.
> Connect using your smaXtec credentials in Direct data API. You do not need to install
> Python, Outlook or browser tools. The Quick Start guide explains cow selection, dates,
> T0, measurements and Excel reports. This is our client-test preview; please report the
> version and displayed error if you encounter an issue. If Windows blocks installation,
> contact your IT/support contact for approved deployment.

## Short client acceptance check

- Install using an ordinary Windows account, then open from the Start menu.
- Sign in, select the expected farm and one known cow, assign measurements and Native
  resolution, set a known T0 and adequate From/To dates, then download to a user folder.
- Open the collection and client-analysis workbook; compare a few known observations.
- Close/reopen and reconnect. Run a newer installer when supplied; confirm saved data
  remains. Uninstall through Settings → Apps and confirm output collections remain.

For subsequent versions, use **Actions → Windows checks and desktop build → Run workflow**,
enable **publish_preview**, and provide a fresh `v<application-version>-client-preview.<n>`
tag. The publish job runs only after all checks, portable smoke, installed smoke,
same-version replacement and uninstall pass. Publishing uses the workflow's short-lived
GitHub token; users do not configure tokens or credentials for installation.
