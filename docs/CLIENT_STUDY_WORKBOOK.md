# Client study workbook contract (2026-09-15)

Sources inspected locally, read-only: the client-provided `Analysis sheet.xlsx` (five
worksheets, 28-column ASPI and Ketofen tables, normal-value table, separate analysis
with line charts and mean/SD/95% confidence summaries) and the two-page
`parameters to be logged (given as an option).pdf`. Neither source file belongs in Git.

## Source-of-truth layout and definitions

The ASPI and Ketofen tables use one row per cow/case. Columns A:AB are `No`, `Cow`,
`Lact`, `DIM`, `Tn`, `Talert`, `T0` (the example types this `To`), `T6`, `T12`, `T18`,
`T24`, `R20`, `AN`, `AT0`, `AT6`, `AT12`, `AT18`, `AT24`, `Rn`, `Rl`, `%drop`, `Rback`,
`RT0`, `RT24`, `RT48`, `RT72`, `RT96`, `RT120` (the example types `R120`).
`Normal values` separately repeats per-cow `Tn`, `AN`, `Rn`. The example's
`Analysis` sheet shows absolute and baseline-relative temperature/activity/rumination
means with 95% confidence bands; some existing chart references are broken (`#REF!`),
so reproduce the intent with valid chart sources rather than copying those errors.

Client definitions:

- **Time zero:** the user-supplied product administration/key event timestamp for
  each cow. Date-range From/To is a collection boundary, not time zero.
- **Tn:** mean of the source **normal temperature** metric over `[T0-7d,T0)`.
- **Talert proxy:** maximum **temperature without drinking cycles** over
  `[T0-5d,T0)`. It is not an actual alert measurement and must be labelled proxy.
- **T0/T6/...:** source temperature without drinking cycles at exactly T0 + the
  named number of elapsed hours. No nearest-sample substitution or silent meaning
  change when the API aggregation is hourly/daily.
- **R20 proxy:** number of distinct, valid temperature-without-drinking-cycles
  measurements strictly above `Tn + configured Celsius differential` during
  `[T0,T0+configured days)`. It is not an alert-event count.
- **AN:** mean source activity over `[T0-14d,T0)`.
- **AT0:** mean source activity over `[T0-6h,T0)`; `AT6`: mean over `[T0,T0+6h)`;
  later `ATn` windows are successive six-hour windows ending at named n.
- **Rn:** mean source rumination over `[T0-7d,T0)`; **Rl:** minimum over
  `[T0,T0+5d)`; **%drop:** Excel stores `1-Rl/Rn` when Rn > 0 and formats it as
  a percentage (for example, `0.4` displays `40%`). This matches the example's
  `1-(Rl/Rn)` formula and percentage semantics.
- **RT0/RT24/...:** absolute source rumination at exactly the named elapsed hour.
- **Rback:** withheld pending clarification. The PDF says time until the series
  first hits Rl *again* after dropping to Rl, which is internally ambiguous; do
  not substitute an unapproved return-to-normal definition.
- **Lact/DIM:** withheld unless the user explicitly supplies reviewed values or a
  documented, accepted source is available. The current measurement API collection
  does not establish their values at time zero.

The core A:AB layout stays close to the example. Add adjacent event/farm/date/status columns
to make periods, metric units and lineage auditable. Provide a separate aligned sheet
for each metric with cow/case columns side-by-side around time zero, per-offset n,
mean, sample SD and 95% confidence limits; separate absolute/relative n is needed
when some cows lack baselines. Both absolute and baseline-relative views are useful
because the example analyses both. Use `1.96 * sample SD / sqrt(n)` for the normal
95% half-width as in its `CONFIDENCE.NORM` examples; use the actual available n at each
offset, not a fixed herd count. n<2 has no interval, not a zero-width interval.

## Safety and acceptance boundary

- Produce a separate, opt-in workbook from a completed local direct-API collection.
  Never change current authentication, download, raw, staging CSV, tidy CSV, manifest
  or original workbook. Never read/write client files inside the repository.
- Mapped metric roles must be chosen from the exact discovered `(code, source unit)` pairs.
  Do not infer meaning from a string fragment or merge units. The normal-temperature
  role is separate from temperature without drinking cycles. A role not present in
  the collection may remain unmapped; every dependent column/chart stays blank and
  Definitions states this. At least one role must be mapped. The R20 differential
  requires Celsius source units for both temperature roles and is blank without Tn.
- Derive numeric/time values only when the source is unambiguous. Preserve raw input.
  For duplicate same-timestamp/metric/unit measurements, collapse *identical* values
  in this derived workbook with an explicit QC count; conflicting values remain blank
  and flagged. The audit CSV/raw responses are never deduplicated.
- Use exact elapsed time in UTC for T/RT points and aligned rows, while displaying
  each cow's farm-local time zero. Reject ambiguous/nonexistent local time zero.
  Missing intervals, uncertain metric roles, truncated coverage, daily resolution,
  invalid values and per-target failures remain visible in QC, not silently estimated.
- The client must review real source metric codes/units, baseline adequacy, formula
  interpretations, Rback, thresholds, horizon, and aligned graph appearance before
  claiming clinical acceptance.
