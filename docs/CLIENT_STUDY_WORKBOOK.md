# Client study workbook contract (2026-09-16)

Sources inspected locally, read-only: the client-provided `Analysis sheet.xlsx` (five
worksheets, 28-column ASPI and Ketofen tables, normal-value table, separate analysis
with line charts and mean/SD/95% confidence summaries) and the two-page
`parameters to be logged (given as an option).pdf`. Neither source file belongs in Git.
The later representative saved direct-API collection was inspected read-only outside
Git. It contains exact `temp_normal_index · degree_celsius`,
`temp_without_drink_cycles · degree_celsius`, `act · act`, and
`rum_index · seconds` pairs. `temp · degree_celsius` also exists, but is not the
client's non-drinking-cycle T source. Normal-index meaning is inferred from its
code/unit and stable observed values; vendor/client confirmation is pending.
The example's ASPI/Ketofen/ASPI LIQUID tabs are treatment groups; smaXtec's
measurement collection does not establish product/group assignment, so a downloaded
collection must not relabel cows into those groups by guess.

## Source-of-truth layout and definitions

The ASPI and Ketofen tables use one row per cow/case. Columns A:AB are `No`, `Cow`,
`Lact`, `DIM`, `Tn`, `Talert`, `T0` (the example types this `To`), `T6`, `T12`, `T18`,
`T24`, `R20`, `AN`, `AT0`, `AT6`, `AT12`, `AT18`, `AT24`, `Rn`, `Rl`, `%drop`, `Rback`,
`RT0`, `RT24`, `RT48`, `RT72`, `RT96`, `RT120` (the example types `R120`). The
automatic workbook preserves that order, inserts requested `Rdown` beside Rback,
and appends `RA1`–`RA5`.
`Normal values` separately repeats per-cow `Tn`, `AN`, `Rn`. The example's
`Analysis` sheet shows absolute and baseline-relative temperature/activity/rumination
means with 95% confidence bands; some existing chart references are broken (`#REF!`),
so reproduce the intent with valid chart sources rather than copying those errors.

Client definitions:

- **Time zero:** for clinical/event studies, the user-supplied product
  administration/key-event timestamp for each cow. If omitted in the **automatic**
  report, farm-local From 00:00 is a visibly labelled **period anchor** for generic
  pivoting only; it must never be described as administration or an alert.
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
  The automatic report converts `rum_index/seconds` to minutes using `/60` to align
  with the example's values; the audit CSV and guided builder keep their source units.
- **Rback:** elapsed days from the first occurrence of Rl in `[T0,T0+5d)` to the
  first later observed rumination reading at or above pre-event Rn. Recovery is
  searched through the available requested period and stays blank if no recovery
  is observed.
- **Rdown:** elapsed days from T0 (the Rn starting point) to the first occurrence
  of Rl in `[T0,T0+5d)`.
- **RA1–RA5:** arithmetic mean of all valid rumination observations in consecutive
  elapsed windows `[T0,T0+24h)`, `[T0+24h,T0+48h)`, through day five. The calculation
  uses every available source interval and divides by its actual observation count.
- **Lact/DIM:** new collections preserve the official animal `lifecycle` and its
  historical `cycles`. Lact is the latest cycle whose calving is at/before T0 and
  whose dry-off is absent/after T0. DIM is the farm-local calendar-date difference
  between T0 and that cycle's calving timestamp. Both remain blank for older
  collections without lifecycle metadata or when T0 is outside a lactating cycle.

The **automatic 0.13.0 companion** preserves the ASPI table's visible groundwork:
the first `Cow analysis` sheet keeps the original 28 columns, including the example's
`To` (T0 temperature) and `R120` spellings, in order. It inserts `Rdown` after Rback
and appends `RA1`–`RA5`, producing A:AH, one cow/case per row and a filterable
blue-banded Excel table and decimal-fraction `%drop` display (`0.13`, not `13%`).
Lact/DIM, Rback, Rdown and RA1–RA5 use the documented rules above when inputs are
available. Talert and R20 remain proxies, explained in header comments; the To
header also explains the period-anchor fallback. The
automatic table has no additional source columns. A separate `Aligned data` worksheet
contains temperature, activity and rumination blocks over the user-selected window
(default -24 to +120 hours) at a six-hour cadence anchored to T0. The user can enter
each boundary in hours or days before download; exact non-six-hour boundaries are also
included. This choice applies only to the aligned sheet and does not widen API From/To.
Cow/case columns are side by side; each row also contains actual n, mean and
normal 95% confidence limits (`mean ± 1.96 * sample SD / sqrt(n)`, blank for n < 2),
with one valid cohort chart per metric. Activity is the mean of the preceding six-hour
window; temperature and rumination are exact-offset readings. Provenance remains in
the separate unchanged collection manifest/CSVs.

The **guided `client-study.xlsx`** still adds adjacent event/farm/date/status columns
and separate aligned/analysis/QC sheets for advanced studies. Its aligned sheet
places cow/case columns side-by-side around time zero, per-offset n,
mean, sample SD and 95% confidence limits; separate absolute/relative n is needed
when some cows lack baselines. Both absolute and baseline-relative views are useful
because the example analyses both. Use `1.96 * sample SD / sqrt(n)` for the normal
95% half-width as in its `CONFIDENCE.NORM` examples; use the actual available n at each
offset, not a fixed herd count. n<2 has no interval, not a zero-width interval.

## Safety and acceptance boundary

- Produce two separate companions from a completed local direct-API collection:
  automatic `client-analysis.xlsx` for each usable cow collection, and the retained
  guided `client-study.xlsx` when the user explicitly requests advanced role/event
  mapping. Both are non-overwriting and derived from the hashed tidy CSV.
- The queue optionally records one strict farm-local T0 per cow/case. A shared value
  can be applied atomically to selected rows or the full queue, while individual cells
  remain editable. It is reviewed with the cow's From/To before data collection. When absent, the automatic workbook
  uses farm-local From 00:00 as a **period anchor** and fills available exact T/AT/RT
  columns. This is not a substitute for a real clinical key event; baseline and
  follow-up columns may be blank if the requested period lacks coverage.
- To cover every current baseline/recovery field, request From at least 14 days
  before T0 and To at least five days after T0. Workbench warns about this in the
  queue but does not silently widen the reviewed API date range.
- In the automatic report, map exact source pairs present in the representative
  collection. `temp_normal_index/degree_celsius` is provisionally the normal role,
  with disclosed `temp/degree_celsius` fallback if missing; neither is used for T.
  `temp_without_drink_cycles/degree_celsius` supplies T. Unrecognized pairs stay in
  the
  original CSV/workbook, not used for client formulas.
- The guided workbook's Analysis summary follows the example's T/A/R absolute and
  normal-relative time-point blocks with actual n, mean, sample SD, lower/upper
  95% limits and charts. The automatic companion now adds the bounded aligned cohort
  view while leaving the client cow table unchanged. Drug-specific subgroup
  blocks need reviewed product assignments before implementation.
  Never change authentication, API requests, raw responses, either CSV or the
  existing descriptive workbook. The manifest only gains optional T0 and derived-
  companion filename/hash/warning metadata; its original lineage fields remain.
- Never read/write client files inside the repository. A derived-output error leaves
  the successful original collection intact and visible with a warning.
- Mapped metric roles must be chosen from the exact discovered `(code, source unit)` pairs.
  Do not infer meaning from a string fragment or merge units. The normal-temperature
  role is separate from temperature without drinking cycles. A role not present in
  the collection may remain unmapped; every dependent column/chart stays blank and
  the guided Definitions states this. At least one role must be mapped. The R20 differential
  requires Celsius source units for both temperature roles and is blank without Tn.
- Derive numeric/time values only when the source is unambiguous. Preserve raw input.
  For duplicate same-timestamp/metric/unit measurements, collapse *identical* values
  in the derived view; conflicting values remain blank. The guided workbook has
  explicit QC counts; the automatic table relies on the unchanged audit collection
  for detailed traceability. The audit CSV/raw responses are never deduplicated.
- Use exact elapsed time in UTC for T/RT points and aligned rows, while displaying
  each cow's farm-local time zero. Reject ambiguous/nonexistent local time zero.
  Missing intervals, uncertain metric roles, truncated coverage, daily resolution,
  invalid values and per-target failures are not silently estimated. The guided QC
  shows them explicitly; the automatic table leaves unavailable fields blank and
  requires the collection manifest/CSV for detailed audit.
- The client must review real source metric codes/units, baseline adequacy, formula
  interpretations, the Rback approximation, thresholds, horizon, and aligned graph appearance before
  claiming clinical acceptance.
