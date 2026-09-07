# SmaxTec Workbench

A desktop application for collecting and analyzing authorized smaXtec herd data.
The product goal is simple: install, open, connect accounts, choose cows and a
period, and receive a consolidated workbook and graphs. No developer tools or
separate dependency installations for the end user.

The first milestone is complete: a desktop sign-in screen and live-verified
website login, with 21 passing tests and a successful packaged Windows smoke test
in GitHub CI. Exports, inbox integration, workbooks, and analysis follow.
See [current status](docs/PROJECT_STATE.md) for evidence and limitations.

## Try the desktop preview

Download the `SmaxTec-Workbench-windows-preview` artifact from the latest successful
[Windows build](https://github.com/FelixvanDijk/SmaxTec/actions), extract both the
artifact wrapper and the included application ZIP, and open `SmaxTec Workbench.exe`.
Keep its `_internal` folder alongside it. The runtime and browser are included.
CI artifacts expire after 14 days; these are development previews, not releases.

This version signs into smaXtec and stops there. Credentials are entered in the
GUI and are not saved. The unsigned executable was denied execution on the current
development computer, although it passed the independent Windows CI smoke test.
Target-machine approval/signing and the polished installer remain release work.

## Project memory

- [Instructions for all agents](AGENTS.md)
- [Architecture and decisions](docs/ARCHITECTURE.md)
- [Current state and next session](docs/PROJECT_STATE.md)
- [Milestones and acceptance criteria](docs/ROADMAP.md)
- [Developer setup](docs/DEVELOPMENT.md)
- [Packaging and release requirements](docs/RELEASING.md)
- [Change history](CHANGELOG.md)

The application is an independent integration project; its name does not imply
vendor endorsement. No account credentials or farm data belong in this repository.
