# Monday client demonstration

Use this short runbook for the 0.8.0 presentation preview. It is a live-product demo,
not a production-release claim. Keep the known-good 0.7.0 rollback tag
`presentation-baseline-2026-09-13` available, but present 0.8.0 after its Windows build
has passed.

## Prepare before the meeting

1. On this prepared development computer, double-click `Start SmaxTec.cmd`. On another
   computer that permits unsigned previews, extract both ZIP layers from the 0.8.0
   artifact, keep `_internal` beside `SmaxTec Workbench.exe`, and launch it once before
   the meeting. If Windows policy blocks that EXE, do not troubleshoot for the first time
   in the meeting—use the already-preflighted prepared computer.
2. Confirm the presentation computer has network access to `api.smaxtec.com`, adequate
   free disk space and Microsoft Excel or another approved XLSX viewer.
3. Agree one active cow and a short, known date period with the account owner. Also
   prepare a second cow if you want to demonstrate multi-selection. Do not guess which
   metric has clinical meaning.
4. Create an approved empty presentation output folder. Close any earlier workbook with
   the same collection name.
5. Run one small collection before the meeting and check its target, dates, row count,
   measurement codes/units, graph-ready CSV and workbook. Keep that approved collection
   as an honestly labelled **previously collected fallback** if venue connectivity fails.
6. Do not share the screen while typing credentials. Start sharing after Connect has
   succeeded and the credential controls have collapsed.

## Five-minute presentation flow

1. **Lead with the promise.** “One desktop workflow discovers the farms and data already
   authorized for this account; it does not wait for emailed exports.”
2. **Browse herd.** Show the live farm selector, switch between Cows/Groups/Devices, use
   search, then demonstrate ordinary click-to-toggle and exact-number paste.
3. **Build a real queue.** Select two targets, choose a short From/To period, and add them.
   Point out that each row retains its own dates and can be edited independently.
4. **Choose measurements deliberately.** Select one or all queue rows, show
   **Find common measurements**, then apply a small set or leave **all available**. The
   displayed codes and units are source metadata, not invented interpretations.
5. **Review before access.** Set a clear collection name, keep Excel enabled, select the
   approved destination, choose **Review & download**, and show the immutable target/date/
   measurement review before confirming.
6. **Show progress and result states.** Explain that success, partial, failed and cancelled
   targets are retained separately; cancellation keeps completed work.
7. **Finish with the three outputs.** Open the workbook directly from Results. Show
   `Collection summary`, the observation-count chart, `Measurement index`, `Data guide`
   and a filtered `Measurements 001` table. Then mention `analysis_ready.csv` as the
   graph-ready input and the complete collection as the audit trail.

## What to say about the next milestone

- The current chart counts source observations; it is deliberately not a health chart.
- Raw responses, two CSV views, workbook and hashes already come from one collection.
- The next step is to approve representative schemas, units, duplicate/time policies,
  calculations and chart definitions, then generate the master workbook and graphs from
  that single canonical dataset.
- The Public API exposes more read routes, including behaviour and health-event KPI data,
  but those should be added only after the client chooses priorities and validates a
  representative response. This avoids impressive-looking but incorrect interpretation.

## Recovery during the meeting

- **Network or API unavailable:** state that the live service is unavailable, then open
  the pre-checked previously collected folder. Do not describe it as a live run.
- **One target has no sensor data:** keep the row visible and use the target-specific
  status to demonstrate partial-result handling; choose the known active cow for the main
  run.
- **Large run is slow:** cancel safely and show the completed files, then use the short
  preflighted collection. Do not rerun a broad collection repeatedly.
- **Workbook viewer warning:** keep the workbook closed, open `analysis_ready.csv`, and
  show the same collection through the complete folder. Source files remain intact.

## End-of-demo questions to capture

Record which targets and periods the client considers representative, the metrics/units
they actually use, required graphs/calculations, treatment of duplicate or missing points,
and preferred workbook layout. Do not record credentials, bearer tokens or raw client data
in the repository.
