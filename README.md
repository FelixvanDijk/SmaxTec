# SmaxTec Workbench

A desktop application for collecting and analyzing authorized smaXtec herd data.
The product goal is simple: install, open, connect accounts, choose cows and their
periods, and receive a consolidated workbook and graphs. No developer tools or
separate dependency installations for the end user.

The first milestone is complete. The second adds dynamic farm selection, one or
more exact cow numbers, individual date ranges and measured-data export requests. Login and
the M2 website structure are live-verified; exports and failure paths are covered
against a synthetic site. Inbox integration, workbooks and analysis follow.
See [current status](docs/PROJECT_STATE.md) for evidence and limitations.

## Test on the current development computer

Double-click **Start SmaxTec.cmd** in the project folder. It opens the GUI using
the local environment already prepared for this project; no terminal commands or
additional installation are needed on this computer.

Connect with your smaXtec email and password and choose a farm. Enter a cow number
with its own From and To dates, then **Add cow** for each additional entry.
Choose **Review and request exports** and check the full table to submit one measured-
data export per exact cow and period. Complete any extra verification in the browser
if prompted. Choose **Disconnect** to close the session. The app does not collect
the resulting emails yet.

Enter both dates as complete `DD/MM/YYYY` values in each row. After five rows the
middle folds away; **Expand all** opens the full scrollable list, and **Compact view**
returns to the first and latest two rows. Every folded row is included and validated.
The review table shows the exact dates for every entry. Workbench verifies smaXtec's
date fields match each entry before clicking Export.

To use one period for everyone, open **Use the same dates for all**, fill its From/To
fields and click **Apply to all**. This changes existing and future rows; changing the
shared fields alone changes nothing. **Undo date change** restores prior individual
ranges until another row edit, addition or removal. Identical cow/period rows are
requested once; the same cow with a different period is a separate request.

After each completed or failed batch, Workbench closes the isolated browser. If
you review another batch with different cows, farm or dates, it opens a fresh
browser and signs in automatically. Your credentials remain only in application
memory until you disconnect or close Workbench.

The launcher is for this prepared working folder. It does not replace the bundled
distribution for other computers; a fresh source checkout needs developer setup.

## Download the packaged desktop preview

Download the `SmaxTec-Workbench-windows-preview` artifact from the latest successful
[Windows build](https://github.com/FelixvanDijk/SmaxTec/actions), extract both the
artifact wrapper and the included application ZIP, and open `SmaxTec Workbench.exe`.
Keep its `_internal` folder alongside it. The runtime and browser are included.
CI artifacts expire after 14 days; these are development previews, not releases.

This version signs into smaXtec and requests measured-data exports for the reviewed
farm, exact cow numbers and individual date ranges. Credentials are entered in the GUI and are
not saved. The unsigned executable was denied execution on the current development
computer, although it passed the independent Windows CI smoke test. Target-machine
approval/signing and the polished installer remain release work.

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
