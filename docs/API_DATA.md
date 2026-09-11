# Direct smaXtec API data

Status: implemented in source preview **0.5.0** on 2026-09-11. Authentication,
farm discovery and metric discovery were live-verified read-only against an authorized
account. Direct measurement download still needs client acceptance with representative
periods before this preview can be called production-ready.

This document is the research record and implementation contract for the project's
API pivot. The current [Public API v2 documentation](https://api.smaxtec.com/api/v2/)
and its [Swagger contract](https://api.smaxtec.com/api/v2/swagger.json) are the primary
sources. The vendor's [beta Python SDK](https://github.com/smaxtec/sxapi) is a useful
route catalogue and example, but it is not installed by Workbench.

## Decision

Use the Public API as the primary data-collection path. Keep the website/export/email
implementation in a clearly labelled legacy tab until the direct path has completed
client acceptance; do not delete a working fallback during the transition.

The API removes the project's most fragile chain: browser selectors, delayed email,
forwarding, Safe Links, short-lived download links, B3-only identity and sensitivity-
label ambiguity. It also exposes stable internal farm/animal/group/device identities,
available metric codes and units before collection. That is a materially better basis
for the future canonical dataset, workbook and graph layers.

Workbench implements a small hardened client rather than depending directly on the
beta SDK because:

- Swagger declares measurement filters as query parameters, while the SDK's
  [data implementation](https://github.com/smaxtec/sxapi/blob/main/src/sxapi/publicV2/data.py)
  sends JSON bodies with GET requests. Intermediaries do not reliably preserve GET
  bodies.
- The SDK's [base HTTP implementation](https://github.com/smaxtec/sxapi/blob/main/src/sxapi/base.py)
  has no explicit request timeout or response-size/cancellation boundary and assumes
  JSON for every decorated response.
- The SDK exposes mutation and emailed-report methods that this read-only desktop
  collection slice does not need.
- A narrow adapter lets UI tests use synthetic clients and keeps HTTP details outside
  application/domain code.

Revisit that choice if smaXtec publishes a stable SDK release whose requests match
the current contract and which provides bounded, cancellable operations.

## Verified route map

| Purpose | Route | Workbench use |
| --- | --- | --- |
| Sign in | `POST /users/credentials` | Yes; JSON body live-verified, token held in memory |
| User/farm membership | `GET /users/{user_id}` | Yes |
| Farm, group and device catalogue | `GET /organisations/{id}` | Yes |
| Cow catalogue | `GET /organisations/{id}/animals?archived=...` | Yes |
| Available codes/units | `GET /data/{animals\|groups\|devices}/{id}/metrics` | Yes, per target |
| Measurement series | `GET /data/{animals\|groups\|devices}/{id}.json` | Yes |
| Weekly farm health index | `GET /kpis/organisations/{id}/health_index` | Optional |
| Events | `GET /events` | Withheld: integer date unit is undocumented |
| Server-side bulk jobs | `GET /data/download_*_data` | Withheld in this slice |
| Generated Excel reports | `POST /data/downloads/generate_*` | No; these return to email workflow |

Swagger describes credential values as query parameters. An authorized read-only
probe on 2026-09-10 confirmed that the same endpoint accepts a JSON body and returns
the documented token/user result. Workbench uses that verified form so credentials
do not enter URLs, proxy history or HTTP request-line diagnostics. This behavior is
covered by synthetic regression tests but should be rechecked if smaXtec changes auth.

The same live probe confirmed authorized farm discovery, organization catalogues and
metric discovery for an active animal. That animal exposed 18 metric codes at the
time of inspection. An animal without current sensor availability returned a 400 for
metric discovery; Workbench presents that as a target-specific unavailable-data result,
not as an account-wide authentication failure. No live mutation, emailed export or
write endpoint was called.

## Desktop workflow

The **Direct data API** workspace is the default tab:

1. Enter smaXtec email/password in masked controls and choose **Connect**.
2. Choose any farm returned by the account. Its current catalogue is loaded dynamically.
3. Browse cows, groups or devices; filter the visible catalogue or enter exact cow
   numbers. Exact `57` never selects `657`.
4. Choose From/To, optionally inspect the selected target's available metric codes,
   then add one or many selected targets to the queue.
5. Edit From/To independently in any queue row. The same target with a different
   period remains a separate request. **Apply Browse dates to all** is explicit.
6. Choose native, 10-minute, hourly or daily resolution; optionally include the
   documented weekly farm health index; choose destination, collection name and Excel.
7. Review every farm/target/date/timezone/measurement association, then download.
8. Inspect per-target success/partial/failure status and open the unique result folder.

The queue may combine farms and target types. Changing a display filter never changes
queued immutable identities. Up to 5,000 target-period rows are allowed, but practical
volume depends on period, metric count, API retention and the user's computer. Large
jobs should be broken into reviewable collections.

## Dates, timezones and measurement requests

GUI dates are strict `DD/MM/YYYY` real calendar dates. Every target carries its own
dates and farm timezone. Workbench interprets the full local days as:

```text
[farm-local From 00:00, day after farm-local To 00:00)
                         -> explicit UTC instants
```

This conversion uses the IANA farm timezone and therefore handles daylight-saving
changes. Requests ask the API for ISO timestamps in UTC using `timestamp_format=iso`,
`tz_mode=utc` and `timezone=UTC`. Both human dates and exact UTC chunk bounds are
stored with every output row.

Swagger does not state whether its `to_date` comparison is inclusive. Workbench does
not silently deduplicate boundary values: every CSV row carries its API chunk number
and bounds, and every response remains in raw JSON. The later normalization milestone
must decide duplicate/interval rules using representative accepted data.

Native and 10-minute requests are split into at most 31-day calls, hourly into 180-day
calls and daily into 730-day calls. This keeps response sizes and failure recovery
bounded without changing the user's reviewed period. There is no automatic HTTP retry.

## Output contract

Each confirmed run creates a new non-overwriting folder beneath the chosen destination:

```text
<collection>-YYYYMMDD-HHMMSS-<random>/
  collection.json
  measurements.csv
  analysis_ready.csv
  <collection>.xlsx                 # when selected
  raw/
    cow-57-YYYYMMDD-YYYYMMDD-metadata.json
    cow-57-YYYYMMDD-YYYYMMDD-part-0001.json
    ...
    <farm>-health-index.json         # when selected
```

- Raw chunk files preserve the API series without guessing undocumented point shapes.
- Metadata files record available/selected metric codes and map chunks to the target.
- `measurements.csv` is an analysis-friendly **staging** table. It preserves farm,
  timezone, target type/internal identity, Animal number/name/ear tag, requested dates,
  chunk bounds, metric, unit, timestamp, value and complete raw point JSON.
- `analysis_ready.csv` is the recommended human/graphing view of those same rows. Its
  readable columns begin with farm and target identity, then metric/unit, farm-local and
  UTC timestamps, value and request details; technical lineage follows at the end. It is
  a tidy long table: one source observation per row, suitable for filtering, grouping
  and charting without first unpacking raw JSON.
- `analysis_ready.csv` never deduplicates, pivots, converts units, interprets metrics or
  coerces values. Timezone-aware ISO source timestamps receive canonical UTC plus the
  farm-local timestamp/date/time. Numeric epochs, timezone-free strings and other
  ambiguous timestamps remain in `source_timestamp`, with derived time fields blank.
  `api_chunk`, `series_index` and `point_index` retain order and distinguish duplicates.
- The optional XLSX contains a readable collection summary and the same staging rows;
  additional measurement sheets are created before Excel's row limit.
- `collection.json` format 2 records target statuses, file paths, row counts and SHA-256
  hashes for both CSV views. It never stores credentials or bearer tokens. The original
  `measurements.csv` columns are unchanged from format 1 for compatibility.

Raw/CSV files are written through exclusive partial files and atomically published.
Cancellation keeps completed chunks and marks the interrupted target `partial`; targets
not started are `cancelled`. A target-specific unavailable metric/data error does not
discard successful targets. The current direct collections do not yet have cross-restart
resume; rerun creates a new collection and does not overwrite the earlier one.

## Security and operational boundaries

- The API origin is fixed to `https://api.smaxtec.com/api/v2`; users cannot enter a
  server URL. Redirects are rejected.
- Sign-in credentials and bearer token stay in process memory, are excluded from repr,
  and are released on Disconnect/close. Python cannot guarantee zeroing immutable strings.
- HTTP calls use a 45-second socket timeout, a 90-second overall response deadline,
  JSON/content-encoding checks and a 32 MiB response cap. Raw output files are capped.
- Remote IDs/names/types are validated and catalogued under the signed-in farm before
  they can be requested. Unexpected HTTP/payload details do not reach the GUI.
- The adapter only reads catalogues, metrics, data and the optional health KPI after
  explicit review. It never calls animal/event mutations or the emailed Excel endpoints.
- Output contains real farm/sensor data. Users must choose an approved storage location
  and follow their organization's retention/classification rules. Workbench does not
  assign an Office sensitivity label.

## Known limits and next work

- Measurement point shape is intentionally treated as semi-structured because Swagger's
  `DataSchema.data` is undocumented. Raw preservation comes before normalization.
- Metric codes and units are displayed exactly as the account exposes them. Clinical
  meanings, preferred-unit conversions and `transformations` are not invented.
- Events remain disabled until smaXtec confirms the unit/semantics of integer From/To
  values. Background bulk jobs remain disabled until polling, pending-job spacing,
  expiry and partial-recovery behavior are specified and tested.
- API availability, retention, rate limits and maximum synchronous period are not fully
  documented. The conservative chunks are a local safety choice, not a vendor limit.
- Direct download, dates and output must be client-tested with representative cows,
  groups, devices and longer periods. Corporate proxy behavior also remains a release gate.
- `analysis_ready.csv` is a safer bridge into graphing, not yet the canonical validated
  dataset. Representative data still must determine timestamp/value shapes, duplicate
  policy, unit handling and missing-interval rules before calculations or graphs.
- The next product milestone defines a canonical normalized schema and then builds
  calculations, a master workbook and graphs from that one dataset. No clinical formula,
  anomaly threshold or visual interpretation is implied by preview 0.7.0.
