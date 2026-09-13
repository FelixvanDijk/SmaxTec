# Monday presentation hardening plan

Date: 2026-09-13. Target: a confident client demonstration on Monday while preserving
the proven 0.7.0 direct-API workflow. Rollback tag:
`presentation-baseline-2026-09-13` (`14fab69`).

## Non-negotiable safety boundary

- Do not change authentication, endpoint routes, query serialization, date conversion,
  target identity, metric selection, raw JSON, either CSV schema, or manifest format.
- Keep `measurements.csv` compatible and `analysis_ready.csv` lossless/tidy.
- Preserve the existing Excel measurement worksheets and columns. Presentation changes
  may add worksheets, formatting, filters, hidden-by-default technical columns and
  descriptive counts; they may not alter source values or add clinical interpretation.
- Every improvement must pass the complete offline suite and a clean packaged Windows
  executable smoke before it becomes the presentation build.

## Official API/SDK assessment

The live Swagger 2 contract and the current official `smaxtec/sxapi` main branch were
rechecked on 2026-09-13. In addition to the implemented farms, animals, groups, devices,
metrics, time series and optional health index, documented read routes include events,
attentions, todos, lists/reports, behaviour KPI, health-events KPI and DIM chart series.

Do not add those routes to the Monday build. The Swagger still leaves the sensor point
payload untyped, event dates are undocumented integers, several KPI structures need
product interpretation, and none of those routes has representative client acceptance.
The SDK remains a beta/minimal wrapper: its current transport sends credentials in query
parameters, sends JSON bodies with GET requests, and does not provide Workbench's bounded
responses or cooperative cancellation. The existing fixed-origin adapter remains safer.

Revisit additional read datasets after Monday with explicit client priorities and one
sanitized accepted sample per route. The first candidates are farm behaviour and health
events because their date parameters are documented; events remain blocked on timestamp
units.

## Delivery plan

### 1. Preserve the working build

- Confirm `main` and `origin/main` are identical and clean.
- Push an annotated rollback tag before edits. **Complete.**

### 2. Make the proven GUI easier to present

- Add clear labels to account and herd browsing controls.
- Make the review dialog name every generated output, including the graph-ready CSV.
- Turn Results into a useful handoff area with direct actions for the graph-ready CSV,
  optional Excel workbook and complete collection folder.
- Retain independent scroll areas and all existing selection/queue behavior.

**Complete in source.** The constrained-window regression also verifies that the three
Results actions stay inside the visible page with no horizontal scroll or clipping.

### 3. Make the Excel output presentation-ready

- Keep `Collection summary` first, but turn it into a branded overview.
- Keep every `Measurements NNN` column/value and sheet name; freeze/filter the table and
  hide only technical lineage columns by default so users see the useful fields first.
- Add a `Measurement index` with source metric/unit observation counts and a descriptive
  top-measurements chart. Counts are not health conclusions.
- Add a `Data guide` explaining every file and staging column, including how to unhide
  provenance and where graph-ready data lives.

**Complete in source.** The original measurement worksheet headers/values are unchanged.

### 4. Presentation confidence

- Add focused workbook/UI regressions, including output-action state and short-screen
  non-overlap.
- Run dependency integrity, lint, format, all tests and source smoke.
- Render and inspect the main direct-API states at presentation dimensions.
- Push a versioned preview and require clean Windows CI packaging/executable smoke.
- Record the exact artifact, remaining live-data gates and a concise presenter runbook.

**In progress.** All 410 local tests/checks pass, themed screens were inspected and the
bundle assembled. Local packaged launch is blocked by the computer's known unsigned-EXE
policy; Windows CI packaging/executable smoke and final artifact recording remain.

## Monday acceptance checklist

- Existing credentials still connect through the same adapter.
- Existing farm/cow/group/device discovery and exact cow selection are unchanged.
- Existing individual dates, metric assignment, review and cancellation are unchanged.
- A synthetic direct collection still produces identical raw/staging/tidy records.
- Optional Excel opens first on a polished overview and still contains all technical data.
- Results gives an obvious next click without requiring File Explorer knowledge.
- The packaged executable starts on clean CI with no external Python/packages/browser.
