# SmaxTec Workbench

A desktop application for collecting and analyzing authorized smaXtec herd data.
The product goal is simple: install, open, connect accounts, choose cows and their
periods, and receive a consolidated workbook and graphs. No developer tools or
separate dependency installations for the end user.

Version 0.5.1 makes the official smaXtec Public API the primary workflow. Users can
discover their farms, cows, groups, devices and available measurements; assign an
individual period to every target; review the full queue; and save direct raw JSON,
CSV and optional Excel data without waiting for email. The earlier browser/email
workflow remains in a labelled legacy tab. Canonical calculations and analysis are next.
See [current status](docs/PROJECT_STATE.md) for verified evidence and remaining gates;
implementation is not a claim that client acceptance or a production release is complete.

## Test on the current development computer

Double-click **Start SmaxTec.cmd** in the project folder. It opens the GUI using
the local environment already prepared for this project; no terminal commands or
additional installation are needed on this computer.

The app opens on **Direct data API**:

1. Enter your smaXtec email/password and choose **Connect**. The fields are masked;
   credentials and API session are not saved.
2. Choose a farm and browse **Cows**, **Animal groups** or **Devices**. Filter the
   table, select visible rows, or enter exact cow numbers such as `57, 203`.
3. Choose From/To as `DD/MM/YYYY`, optionally use **Explore measurements**, and add
   the selected targets to the queue. Repeat for other farms or periods.
4. In **Download queue**, edit any row's dates independently. Choose resolution,
   optional farm health index, destination, collection name and whether to create XLSX.
5. Choose **Review & download**, inspect every target/date/metric row, and confirm.
   **Results** shows saved, partial, failed or cancelled targets and opens the folder.

Each run creates a unique folder. It contains the original API response chunks,
`measurements.csv`, optional `<collection>.xlsx`, and a hashed `collection.json`
manifest. Raw data and UTC chunk boundaries are retained for the next normalization/
graph milestone. See [Direct API data](docs/API_DATA.md) for the exact contract and
known API ambiguities.

## Legacy website export requests

Open **Legacy website + email** only when the direct API cannot supply the required
data. Connect with your smaXtec email and password and choose a farm. Enter a cow number
with its own From and To dates, then **Add cow** for each additional entry.
Choose **Review and request exports** and check the full table to submit one measured-
data export per exact cow and period. Complete any extra verification in the browser
if prompted. Choose **Disconnect** to close the website session.

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

## Legacy emailed Excel collection

This compatibility path works independently of website sign-in. When the emails have arrived,
use **Go to collection** or scroll to **3. Collect your emailed exports**.

1. Select **Sign in with Microsoft 365**. Your browser opens Microsoft's normal
   work-account sign-in and MFA, then Workbench offers that account's Inbox. This
   route works regardless of whether you use new Outlook, Outlook on the web or
   classic Outlook. Workbench never asks for your email password or a copied token.
   Your organisation may need to approve this app's delegated `Mail.Read` permission.
   **Connect classic Outlook** remains a local fallback where company policy permits it.
2. Choose **Latest** matching email count and the received-time lookback in days,
   then **Find export emails**. This counts matching exports, not arbitrary inbox mail.
   **Import saved emails** remains available for selected `.eml` or `.msg` files;
   that imports the chosen files, not the latest N.
3. Review the full list, including duplicates and warnings. Change the output root
   with **Browse** if needed, then **Download reviewed emails**. New arrivals and
   failures cannot silently replace items in this reviewed selection.
4. Choose **Open collection folder**. Every workbook uses its own B3 identifier:
   `203 (new girl)` becomes `cow-203.xlsx`, while another cow gets its own filename.
   Further files for the same cow receive numbered suffixes and never overwrite.

The default root is your Windows Documents folder under
`SmaxTec Workbench/Collections`; each collection gets its own timestamped folder.
`collection.json` records file status, identity and hashes without email links.
Use **Retry incomplete downloads** for the same collection. After restarting on
the same user/computer, re-select the same emails and use **Resume existing collection**
to choose their original folder. New collections are independent, not globally deduplicated.

No emails are marked read, moved or deleted. An email forwarded as an attachment
must first be saved/extracted as its own `.eml` or `.msg`. Link expiry remains tied
to the original export, not when it was forwarded. Blocked security checks are not bypassed.
Excel is not opened and labels are **unchanged**, not automatically set to Public.
B3 is an animal name; collection does not verify the website farm, Animal number
or requested date period. Check these before later analysis.

## Download the packaged desktop preview

Download the `SmaxTec-Workbench-windows-preview` artifact from the latest successful
[0.5.1 Windows build](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34555178268), extract both the
artifact wrapper and the included application ZIP, and open `SmaxTec Workbench.exe`.
Keep its `_internal` folder alongside it. The runtime and browser are included.
CI artifacts expire after 14 days; these are development previews, not releases.

Website credentials are entered in the GUI and are not saved. The unsigned
executable was denied execution on the current development computer; prior versions
passed independent Windows CI smoke tests. Consult current status for 0.5.1 build
evidence rather than assuming a successful earlier artifact includes this feature.
Target-machine approval/signing, third-party license review and the polished
installer remain release work. If the legacy Microsoft 365 route is retained, its
application registration and tenant-consent gate still need completion.

## Project memory

- [Instructions for all agents](AGENTS.md)
- [Architecture and decisions](docs/ARCHITECTURE.md)
- [Current state and next session](docs/PROJECT_STATE.md)
- [Milestones and acceptance criteria](docs/ROADMAP.md)
- [Email collection design and prerequisites](docs/EMAIL_COLLECTION.md)
- [Direct API research and data contract](docs/API_DATA.md)
- [Microsoft 365 one-time IT setup](docs/MICROSOFT_365_SETUP.md)
- [Developer setup](docs/DEVELOPMENT.md)
- [Packaging and release requirements](docs/RELEASING.md)
- [Change history](CHANGELOG.md)

The application is an independent integration project; its name does not imply
vendor endorsement. No account credentials or farm data belong in this repository.
