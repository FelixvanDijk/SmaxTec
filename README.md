# SmaxTec Workbench

A desktop application for collecting and analyzing authorized smaXtec herd data.
The product goal is simple: install, open, connect accounts, choose cows and their
periods, and receive a consolidated workbook and graphs. No developer tools or
separate dependency installations for the end user.

Version 0.14.0 keeps the official smaXtec Public API as the primary workflow. Its spacious
queue-first editor supports click-to-toggle, filtered bulk and pasted exact-number cow
selection, individual periods, and measurement assignment to one, several or every
queued target. Users can review the full queue and save direct raw JSON, a lossless
technical CSV, a graph-ready tidy CSV and optional Excel data without waiting for email.
The earlier browser/email workflow remains in a
labelled legacy tab. Every completed cow collection now adds a client-style
`client-analysis.xlsx` companion automatically. The guided study builder remains
available for reviewed mapping and advanced options; broader canonical calculations
and accepted analysis remain next.
See [current status](docs/PROJECT_STATE.md) for verified evidence and remaining gates;
implementation is not a claim that client acceptance or a production release is complete.

## Test on the current development computer

Double-click **Start SmaxTec.cmd** in the project folder. It opens the GUI using
the local environment already prepared for this project; no terminal commands or
additional installation are needed on this computer.

The app opens on **Direct data API**:

1. Enter your smaXtec email/password and choose **Connect**. The fields are masked;
   credentials and API session are not saved.
2. Choose a farm and browse **Cows**, **Animal groups** or **Devices**. Ordinary clicks
   toggle multiple rows without Ctrl. You can also select every filtered row or paste
   exact cow numbers such as `57, 203` (commas, spaces and new lines are accepted).
3. Choose From/To as `DD/MM/YYYY` and add the selected targets to the queue. Repeat
   for other farms or periods; the signed-in account card collapses to preserve space.
4. In **Download queue**, select one, several or every row. Keep **all available**
   measurements, or find the codes shared by the selected targets, uncheck anything
   unwanted, and apply that choice only to those rows. Edit any row's dates independently.
   For cow studies, optionally enter each cow's actual treatment/key-event **Study T0**
   as `DD/MM/YYYY HH:MM` in its farm timezone. Enter a shared value once and apply it
   to selected rows or the entire queue, or keep editing individual rows. Set From at least 14 days before T0
   and To at least five days after it to cover the baseline/recovery fields. Choose how
   many hours or days the automatic **Aligned data** sheet should show before and after
   T0 (24 hours before and 120 hours after by default). This report-only choice does not
   change downloaded dates. Then choose resolution, optional farm health index,
   destination, name and XLSX output.
5. Choose **Review & download**, inspect every target/date/metric row, and confirm.
   **Results** shows saved, partial, failed or cancelled targets and directly opens the
   graph-ready CSV, polished workbook, automatic client analysis or audit folder.

Each run creates a unique folder. It contains the original API response chunks,
`measurements.csv`, `analysis_ready.csv`, optional `<collection>.xlsx`, a cow-only
`client-analysis.xlsx` companion when source measurements are usable, and a hashed
`collection.json` manifest. Open `analysis_ready.csv` first for a readable one-observation-
per-row table with identity, metric/unit, local and UTC times, value and provenance.
The workbook starts with a branded collection overview, descriptive observation-count
chart, measurement index and data guide. Its measurement sheets preserve every original
column and value; technical lineage columns are merely hidden for readability and can be
unhidden. The existing `measurements.csv` and raw JSON remain unchanged as the lossless audit path.
See [Direct API data](docs/API_DATA.md) for the exact contract and known API ambiguities.

## Automatic client analysis and guided study workbook

Cow collections automatically create `client-analysis.xlsx` alongside the existing
files. Its first sheet remains the filterable, blue-banded client table with one
cow/case per row. The original columns keep their order; `Rdown` now follows Rback
and `RA1`–`RA5` finish the row. Its `To`
header is the client's spelling of T0 temperature, not the request end date. Proxy
and period-anchor explanations are attached as header notes, not extra tabs. The
automatic mapping uses the exact pairs in a representative saved collection:
`temp_normal_index · degree_celsius` (normal-temperature interpretation pending
client confirmation), `temp_without_drink_cycles · degree_celsius` for T fields,
`act · act`, and `rum_index · seconds` converted to minutes only in this derived
workbook. If normal index is absent, `temp · degree_celsius` is a disclosed fallback.
New collections also preserve smaXtec's documented animal lifecycle cycles: `Lact`
uses the cycle containing T0 and `DIM` is the farm-local calendar days since its
calving date. Tn, AN and Rn are calculated over the client's seven-/fourteen-day
pre-T0 windows; `%drop` is `1-Rl/Rn`. `Rback` is elapsed days from the first Rl
minimum to recovery at/above Rn; `Rdown` is elapsed days from T0 to Rl. `RA1`–`RA5`
are the mean rumination values in successive 24-hour windows after T0. Talert is the
maximum in the exact five days before T0. R20 counts readings strictly above
`Tn + 0.8 °C`; generic API events are not treated as alerts without a documented mapping.
An additive `Aligned data` sheet places each cow beside the others from -24 to +120
hours around its own T0 for temperature, six-hour mean activity and rumination. It
includes actual n, mean and lower/upper 95% confidence limits plus three cohort charts.
When Study T0 is not supplied, the workbook pivots exact points around the cow's
farm-local From date at 00:00, clearly labelled a **period anchor**, not treatment
time. Earlier baseline windows and later follow-up windows may still be blank when
outside the downloaded range. Enter actual T0 for treatment interpretation. The
source CSVs and raw responses still contain every requested measurement.

The guided builder remains available for exact role selection and advanced study
windows. It writes a separate `client-study.xlsx` and never overwrites the automatic
file.

If Lact/DIM remain blank after a cow collection, Results enables **Add Lact / DIM
from website**. Workbench reuses the successful API sign-in details held only for the
current connected session, opens its isolated browser, matches each farm and exact
Animal number, and reads available `Number of lactations` / `Days in milk` values from
the cow diagram. Disabled diagrams are skipped. A new numbered `client-analysis` copy
is created; the prior workbook and source collection remain unchanged. These values
are the website's **current snapshot when the button is run**, not historical Lact/DIM
calculated at Study T0, and are identified as such in cell notes.

After downloading cow data, open **Results → Create study workbook**. You can also
choose an earlier completed direct-API collection folder. Match the four source
measurement codes and units to normal temperature, temperature *without drinking
cycles*, activity and rumination; the app does not guess these roles. Enter the
actual administration/key-event time for **each cow** as `DD/MM/YYYY HH:MM` in its
farm timezone. If the time is genuinely shared, enter it above the table and press
**Apply to every cow**, then review the rows. Choose the temperature differential,
follow-up days and optional extra/aligned time steps, then **Create study workbook**.

The separate `client-study.xlsx` appears in that collection folder; repeated runs
get numbered names and leave all original API files untouched. Its main sheet has
one row per cow in the client's T/AT/RT parameter order. Further sheets contain
normal values, exact configurable timepoints, cow data aligned around their own
time zero, an Analysis summary, absolute/relative mean and 95% confidence charts,
and Definitions/QC.
**T6 always means an actual reading exactly six elapsed hours later**, even when
the chosen download interval was hourly/daily; if there is no exact reading it
stays blank. Talert and R20 are explicitly labelled estimates. Lact/DIM use lifecycle
metadata in new collections; Rback uses the disclosed recovery-to-Rn definition.
Review the QC sheet before using the numbers. See
[client study contract](docs/CLIENT_STUDY_WORKBOOK.md).
This is a synthetic-tested analytical preview, not a clinically accepted report.

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

The retained [0.8.0 Windows preview](https://github.com/FelixvanDijk/SmaxTec/actions/runs/34731198778)
does **not** include automatic client analysis. The 0.9.0 Windows checks passed
tests, bundle build and packaged executable smoke, but artifact upload was rejected
by GitHub Actions storage quota. Twelve older temporary ZIP artifacts have been
removed, retaining only the two latest working 0.8/0.7 previews; quota recovery
and a downloadable 0.14.0 preview still need CI confirmation. For now, use
`Start SmaxTec.cmd` on this prepared development computer. Once a successful
0.14.0 artifact appears, download its `SmaxTec-Workbench-windows-preview` ZIP,
extract both the artifact wrapper and the included application ZIP, and open
`SmaxTec Workbench.exe`.
Keep its `_internal` folder alongside it. The runtime and browser are included.
CI artifacts expire after 14 days; these are development previews, not releases.

Website credentials are entered in the GUI and are not saved. The unsigned
executable was denied execution on the current development computer; 0.8.0 passed
independent Windows CI smoke tests. Consult current status for the 0.14.0 build
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
- [Client-study workbook contract](docs/CLIENT_STUDY_WORKBOOK.md)
- [Monday client demonstration](docs/DEMO_RUNBOOK.md)
- [Microsoft 365 one-time IT setup](docs/MICROSOFT_365_SETUP.md)
- [Developer setup](docs/DEVELOPMENT.md)
- [Packaging and release requirements](docs/RELEASING.md)
- [Change history](CHANGELOG.md)

The application is an independent integration project; its name does not imply
vendor endorsement. No account credentials or farm data belong in this repository.
