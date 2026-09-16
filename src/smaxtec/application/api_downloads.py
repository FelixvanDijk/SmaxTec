"""Direct API collection with raw lineage, CSV output and an optional Excel workbook."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from smaxtec.application.api_data import (
    ApiCancelled,
    ApiDownloadRequest,
    ApiDownloadResult,
    ApiError,
    ApiFileResult,
    ApiMetric,
    ApiProgress,
    ApiTarget,
)

MEASUREMENT_HEADERS = (
    "farm",
    "farm_timezone",
    "target_type",
    "target_id",
    "animal_number",
    "animal_name",
    "official_id",
    "requested_from",
    "requested_to",
    "api_chunk",
    "chunk_from_utc",
    "chunk_to_utc",
    "metric",
    "unit",
    "timestamp",
    "value",
    "raw_point",
)
ANALYSIS_HEADERS = (
    "farm_name",
    "target_type",
    "target_number",
    "target_name",
    "official_id",
    "target_group",
    "metric",
    "unit",
    "timestamp_local",
    "local_date",
    "local_time",
    "timestamp_utc",
    "value",
    "resolution",
    "requested_from",
    "requested_to",
    "farm_timezone",
    "farm_id",
    "target_id",
    "api_chunk",
    "series_index",
    "point_index",
    "source_timestamp",
)
EXCEL_MAX_DATA_ROWS = 1_000_000
RAW_RESPONSE_LIMIT = 128 * 1024 * 1024
_SAFE_PART = re.compile(r"[^A-Za-z0-9._-]+")


class ApiClient(Protocol):
    def metrics(self, entity, stop: Event) -> tuple[ApiMetric, ...]: ...

    def data(
        self,
        entity,
        metrics: tuple[str, ...],
        start: datetime,
        end: datetime,
        aggregation: str,
        stop: Event,
    ) -> list[dict[str, Any]]: ...

    def health_index(self, farm, start: date, end: date, stop: Event) -> Any: ...


def _check_stop(stop: Event) -> None:
    if stop.is_set():
        raise ApiCancelled


def _safe_part(value: str, fallback: str) -> str:
    result = _SAFE_PART.sub("-", value.strip()).strip(" .-")[:80]
    return result or fallback


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _write_json(path: Path, value: Any) -> str:
    raw = (_json(value) + "\n").encode("utf-8")
    if len(raw) > RAW_RESPONSE_LIMIT:
        raise ApiError(
            "api_size",
            "A raw smaXtec response is too large to save safely. Select a shorter period.",
        )
    temporary = path.with_name("." + path.name + ".partial")
    with temporary.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    return hashlib.sha256(raw).hexdigest()


def _chunks(target: ApiTarget, aggregation: str) -> Iterator[tuple[datetime, datetime]]:
    start, end = target.utc_bounds()
    days = {"native": 31, "10minutes": 31, "hourly": 180, "daily": 730}[aggregation]
    cursor = start
    while cursor < end:
        next_cursor = min(end, cursor + timedelta(days=days))
        yield cursor, next_cursor
        cursor = next_cursor


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return _json(value)


def _point_parts(point: Any) -> tuple[str, str, str]:
    """Extract common timestamp/value shapes while retaining the complete point."""
    raw = _json(point)
    if isinstance(point, dict):
        timestamp = next(
            (
                point[key]
                for key in ("timestamp", "ts", "datetime", "date", "time", "x")
                if key in point
            ),
            "",
        )
        value = next(
            (point[key] for key in ("value", "val", "v", "y") if key in point),
            "",
        )
        return _scalar(timestamp), _scalar(value), raw
    if isinstance(point, (list, tuple)):
        timestamp = point[0] if point else ""
        value = point[1] if len(point) > 1 else ""
        return _scalar(timestamp), _scalar(value), raw
    return "", _scalar(point), raw


def _series_points(data: Any) -> Iterable[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return ({"timestamp": key, "value": value} for key, value in data.items())
    if data is None:
        return ()
    return (data,)


def _analysis_times(timestamp: str, timezone: str) -> tuple[str, str, str, str]:
    """Derive explicit times only from an unambiguous timezone-aware ISO value."""
    candidate = timestamp.strip()
    if not candidate:
        return "", "", "", ""
    if candidate[-1:] in {"Z", "z"}:
        candidate = candidate[:-1] + "+00:00"
    try:
        source = datetime.fromisoformat(candidate)
        if source.tzinfo is None or source.utcoffset() is None:
            return "", "", "", ""
        utc_value = source.astimezone(UTC)
        local_value = utc_value.astimezone(ZoneInfo(timezone))
    except (ValueError, TypeError):
        return "", "", "", ""
    return (
        utc_value.isoformat().replace("+00:00", "Z"),
        local_value.isoformat(),
        local_value.date().isoformat(),
        local_value.timetz().isoformat(),
    )


@dataclass(frozen=True)
class _MeasurementRecord:
    staging: tuple[str, ...]
    analysis: tuple[str, ...]


def _rows(
    target: ApiTarget,
    series: dict[str, Any],
    chunk_index: int,
    series_index: int,
    chunk_start: datetime,
    chunk_end: datetime,
    aggregation: str,
) -> Iterator[_MeasurementRecord]:
    metric = _scalar(series.get("metric"))
    unit = _scalar(series.get("unit"))
    for point_index, point in enumerate(_series_points(series.get("data")), 1):
        timestamp, value, raw = _point_parts(point)
        timestamp_utc, timestamp_local, local_date, local_time = _analysis_times(
            timestamp, target.entity.farm.timezone
        )
        yield _MeasurementRecord(
            staging=(
                target.entity.farm.name,
                target.entity.farm.timezone,
                target.entity.kind,
                target.entity.id,
                target.entity.number,
                target.entity.name,
                target.entity.official_id,
                target.start_date.isoformat(),
                target.end_date.isoformat(),
                str(chunk_index),
                chunk_start.isoformat(),
                chunk_end.isoformat(),
                metric,
                unit,
                timestamp,
                value,
                raw,
            ),
            analysis=(
                target.entity.farm.name,
                target.entity.kind,
                target.entity.number,
                target.entity.name,
                target.entity.official_id,
                target.entity.group,
                metric,
                unit,
                timestamp_local,
                local_date,
                local_time,
                timestamp_utc,
                value,
                aggregation,
                target.start_date.isoformat(),
                target.end_date.isoformat(),
                target.entity.farm.timezone,
                target.entity.farm.id,
                target.entity.id,
                str(chunk_index),
                str(series_index),
                str(point_index),
                timestamp,
            ),
        )


class _ExcelWriter:
    def __init__(self, path: Path) -> None:
        import xlsxwriter

        self.path = path
        self.workbook = xlsxwriter.Workbook(str(path), {"constant_memory": True})
        self.workbook.set_properties(
            {
                "title": "SmaxTec Workbench direct data collection",
                "subject": "Auditable smaXtec measurement collection",
                "author": "SmaxTec Workbench",
                "comments": "Source values preserved; see Data guide for provenance.",
            }
        )
        self.header = self.workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#245D43",
                "border": 0,
                "valign": "vcenter",
            }
        )
        self.title = self.workbook.add_format(
            {"bold": True, "font_color": "#193E34", "font_size": 24}
        )
        self.subtitle = self.workbook.add_format(
            {"bold": True, "font_color": "#4C8854", "font_size": 11}
        )
        self.wrap = self.workbook.add_format(
            {"text_wrap": True, "valign": "top", "font_color": "#35523E"}
        )
        self.note = self.workbook.add_format(
            {
                "text_wrap": True,
                "valign": "top",
                "font_color": "#63776E",
                "bg_color": "#F1F6ED",
            }
        )
        self.count = self.workbook.add_format(
            {"num_format": "#,##0", "font_color": "#244D40", "align": "right"}
        )
        self._metric_counts: Counter[tuple[str, str]] = Counter()
        self._sheet_index = 0
        self._sheet = None
        self._row = EXCEL_MAX_DATA_ROWS + 1
        self._summary = self.workbook.add_worksheet("Collection summary")
        self._summary.hide_gridlines(2)
        self._summary.set_tab_color("#4C8854")
        self._summary.set_zoom(95)
        self._summary.set_column(0, 0, 28)
        self._summary.set_column(1, 1, 62)
        self._summary.set_column(2, 8, 13)
        self._summary.set_row(0, 36)
        self._summary.write_string(0, 0, "SmaxTec Workbench", self.title)
        self._summary.write_string(1, 0, "DIRECT API COLLECTION", self.subtitle)
        self._summary.write_string(2, 0, "START HERE", self.subtitle)
        self._summary.write_string(
            2,
            1,
            "Start with analysis_ready.csv for filtering and future charts. "
            "The raw JSON and measurements.csv remain the audit source.",
            self.note,
        )
        self._summary.set_row(2, 34)
        self._summary_row = 4
        self.summary_row(("Field", "Value"), header=True)

    @staticmethod
    def _cell(value: Any) -> str:
        text = _scalar(value)
        return text if len(text) <= 32767 else text[:32748] + "… [truncated]"

    def summary_row(self, values: Iterable[Any], *, header: bool = False) -> None:
        for column, value in enumerate(values):
            self._summary.write_string(
                self._summary_row,
                column,
                self._cell(value),
                self.header if header else self.wrap,
            )
        self._summary_row += 1

    def measurement_row(self, values: tuple[str, ...]) -> None:
        self._metric_counts[(values[12], values[13])] += 1
        if self._row > EXCEL_MAX_DATA_ROWS:
            self._sheet_index += 1
            self._sheet = self.workbook.add_worksheet(f"Measurements {self._sheet_index:03d}")
            self._sheet.hide_gridlines(2)
            self._sheet.set_zoom(90)
            self._sheet.freeze_panes(1, 0)
            self._sheet.autofilter(0, 0, 0, len(MEASUREMENT_HEADERS) - 1)
            self._sheet.set_row(0, 26)
            self._sheet.set_column(0, 0, 22)
            self._sheet.set_column(1, 1, 16, None, {"hidden": True})
            self._sheet.set_column(2, 2, 13)
            self._sheet.set_column(3, 3, 18, None, {"hidden": True})
            self._sheet.set_column(4, 4, 14)
            self._sheet.set_column(5, 6, 22)
            self._sheet.set_column(7, 8, 14)
            self._sheet.set_column(9, 11, 22, None, {"hidden": True})
            self._sheet.set_column(12, 12, 22)
            self._sheet.set_column(13, 13, 16)
            self._sheet.set_column(14, 14, 25)
            self._sheet.set_column(15, 15, 16)
            self._sheet.set_column(16, 16, 45, None, {"hidden": True})
            for column, heading in enumerate(MEASUREMENT_HEADERS):
                self._sheet.write_string(0, column, heading, self.header)
            self._row = 1
        assert self._sheet is not None
        for column, value in enumerate(values):
            self._sheet.write_string(self._row, column, self._cell(value))
        self._row += 1

    def json_sheet(self, name: str, records: Iterable[dict[str, Any]]) -> None:
        sheet = self.workbook.add_worksheet(name[:31])
        sheet.freeze_panes(1, 0)
        sheet.set_column(0, 0, 18)
        sheet.set_column(1, 1, 100)
        sheet.write_string(0, 0, "record", self.header)
        sheet.write_string(0, 1, "raw_json", self.header)
        for row, record in enumerate(records, 1):
            if row > EXCEL_MAX_DATA_ROWS:
                break
            sheet.write_number(row, 0, row)
            sheet.write_string(row, 1, self._cell(record), self.wrap)

    def _write_metric_index(self) -> None:
        sheet = self.workbook.add_worksheet("Measurement index")
        sheet.hide_gridlines(2)
        sheet.freeze_panes(4, 0)
        sheet.set_tab_color("#80B25E")
        sheet.set_column(0, 0, 32)
        sheet.set_column(1, 1, 22)
        sheet.set_column(2, 2, 16)
        sheet.write_string(0, 0, "Measurement index", self.title)
        sheet.write_string(
            1,
            0,
            "Descriptive source row counts only — no clinical meaning, unit conversion "
            "or duplicate removal has been applied.",
            self.note,
        )
        headings = ("Measurement", "Source unit", "Observations")
        for column, heading in enumerate(headings):
            sheet.write_string(3, column, heading, self.header)
        ordered = sorted(
            self._metric_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
        )
        for row, ((metric, unit), observations) in enumerate(ordered, 4):
            sheet.write_string(row, 0, self._cell(metric))
            sheet.write_string(row, 1, self._cell(unit))
            sheet.write_number(row, 2, observations, self.count)
        if ordered:
            chart_rows = min(len(ordered), 15)
            chart = self.workbook.add_chart({"type": "column"})
            chart.add_series(
                {
                    "name": "Observations",
                    "categories": ["Measurement index", 4, 0, 3 + chart_rows, 0],
                    "values": ["Measurement index", 4, 2, 3 + chart_rows, 2],
                    "fill": {"color": "#4C8854"},
                    "border": {"none": True},
                }
            )
            chart.set_title({"name": "Observations by measurement"})
            chart.set_y_axis({"name": "Source rows", "major_gridlines": {"visible": False}})
            chart.set_x_axis({"label_position": "low"})
            chart.set_legend({"none": True})
            chart.set_style(10)
            self._summary.insert_chart(4, 3, chart, {"x_scale": 1.25, "y_scale": 1.1})

    def _write_data_guide(self) -> None:
        sheet = self.workbook.add_worksheet("Data guide")
        sheet.hide_gridlines(2)
        sheet.freeze_panes(4, 0)
        sheet.set_column(0, 0, 24)
        sheet.set_column(1, 1, 76)
        sheet.set_column(2, 2, 18)
        sheet.write_string(0, 0, "Data guide", self.title)
        sheet.write_string(
            1,
            0,
            "Nothing in this workbook changes the source measurements. Technical columns "
            "are hidden only for readability and can be unhidden in Excel.",
            self.note,
        )
        rows = (
            (
                "analysis_ready.csv",
                "Recommended tidy table for filtering and future graphs.",
                "Companion file",
            ),
            (
                "measurements.csv",
                "Complete staging rows with raw point and chunk lineage.",
                "Companion file",
            ),
            (
                "raw/",
                "Original bounded API response chunks and target metadata.",
                "Companion folder",
            ),
            (
                "collection.json",
                "File names, statuses, row counts and SHA-256 hashes.",
                "Companion file",
            ),
            ("farm", "Farm display name returned by smaXtec.", "Visible"),
            ("farm_timezone", "IANA timezone used for reviewed local dates.", "Hidden"),
            ("target_type", "animals, groups or devices.", "Visible"),
            ("target_id", "Internal smaXtec target identity.", "Hidden"),
            ("animal_number", "Animal number or target number, preserved as text.", "Visible"),
            ("animal_name", "Target display name returned by smaXtec.", "Visible"),
            ("official_id", "Official animal identifier when supplied.", "Visible"),
            ("requested_from / to", "Reviewed whole farm-local date period.", "Visible"),
            ("api_chunk / bounds", "Exact request part and half-open UTC boundaries.", "Hidden"),
            ("metric", "Source measurement code returned by smaXtec.", "Visible"),
            ("unit", "Source unit returned by smaXtec.", "Visible"),
            ("timestamp", "Source timestamp serialized without interpretation.", "Visible"),
            ("value", "Source value serialized without conversion.", "Visible"),
            ("raw_point", "Complete source point JSON for audit and later validation.", "Hidden"),
        )
        for column, heading in enumerate(("Item", "Purpose", "Default view")):
            sheet.write_string(3, column, heading, self.header)
        for row, values in enumerate(rows, 4):
            for column, value in enumerate(values):
                sheet.write_string(row, column, value, self.wrap)

    def close(self) -> None:
        self._write_metric_index()
        self._write_data_guide()
        self.workbook.close()


class ApiDownloadService:
    """Create one auditable collection folder from a frozen reviewed request."""

    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def download(
        self,
        request: ApiDownloadRequest,
        stop: Event,
        progress: Callable[[ApiProgress], None],
    ) -> ApiDownloadResult:
        try:
            return self._download(request, stop, progress)
        except (ApiCancelled, ApiError):
            raise
        except OSError:
            raise ApiError(
                "api_output",
                "Workbench could not create the collection in that folder. "
                "Choose another location and check that it has free space.",
            ) from None

    def _download(
        self,
        request: ApiDownloadRequest,
        stop: Event,
        progress: Callable[[ApiProgress], None],
    ) -> ApiDownloadResult:
        _check_stop(stop)
        folder = self._folder(request.destination, request.name)
        raw_folder = folder / "raw"
        raw_folder.mkdir(parents=True)
        csv_partial = folder / ".measurements.csv.partial"
        csv_path = folder / "measurements.csv"
        analysis_partial = folder / ".analysis_ready.csv.partial"
        analysis_path = folder / "analysis_ready.csv"
        excel_partial = folder / f".{request.name}.partial.xlsx"
        excel_path = folder / f"{request.name}.xlsx"
        excel = _ExcelWriter(excel_partial) if request.excel else None
        results: list[ApiFileResult] = []
        warnings: list[str] = []
        manifest_targets: list[dict[str, Any]] = []
        total_rows = 0
        cancelled = False
        extras: dict[str, Any] = {}
        with (
            csv_partial.open("x", encoding="utf-8-sig", newline="") as csv_handle,
            analysis_partial.open("x", encoding="utf-8-sig", newline="") as analysis_handle,
        ):
            writer = csv.writer(csv_handle)
            analysis_writer = csv.writer(analysis_handle)
            writer.writerow(MEASUREMENT_HEADERS)
            analysis_writer.writerow(ANALYSIS_HEADERS)
            try:
                if excel:
                    excel.summary_row(("Collection", request.name))
                    excel.summary_row(("Created UTC", datetime.now(UTC).isoformat()))
                    excel.summary_row(("Resolution", request.aggregation))
                    excel.summary_row(("Targets", len(request.targets)))
                for index, target in enumerate(request.targets, 1):
                    _check_stop(stop)
                    progress(
                        ApiProgress(
                            f"Downloading {target.entity.label} from {target.entity.farm.name}…",
                            index - 1,
                            len(request.targets),
                        )
                    )
                    result, record, rows = self._target(
                        target,
                        request.aggregation,
                        raw_folder,
                        writer,
                        analysis_writer,
                        excel,
                        stop,
                    )
                    results.append(result)
                    manifest_targets.append(record)
                    total_rows += rows
                    _check_stop(stop)
                    progress(ApiProgress("Target saved.", index, len(request.targets)))
                extras = self._extras(request, raw_folder, excel, stop, progress)
            except ApiCancelled:
                cancelled = True
                warnings.append("The collection was cancelled; completed target files were kept.")
            finally:
                csv_handle.flush()
                os.fsync(csv_handle.fileno())
                analysis_handle.flush()
                os.fsync(analysis_handle.fileno())
                if excel:
                    excel.close()
        csv_partial.replace(csv_path)
        analysis_partial.replace(analysis_path)
        if excel:
            excel_partial.replace(excel_path)
        if cancelled:
            completed = {entry.target for entry in results}
            results.extend(
                ApiFileResult(target, "cancelled", detail="Not requested before cancellation.")
                for target in request.targets
                if target not in completed
            )
        manifest = {
            "format_version": 2,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "collection_name": request.name,
            "aggregation": request.aggregation,
            "measurement_csv": csv_path.name,
            "measurement_csv_sha256": self._hash(csv_path),
            "analysis_csv": analysis_path.name,
            "analysis_csv_sha256": self._hash(analysis_path),
            "excel": excel_path.name if request.excel else None,
            "excel_sha256": self._hash(excel_path) if request.excel else None,
            "cancelled": cancelled,
            "total_measurement_rows": total_rows,
            "targets": manifest_targets,
            "extras": extras,
            "warnings": warnings,
        }
        _write_json(folder / "collection.json", manifest)
        client_workbook = None
        if (
            not cancelled
            and total_rows
            and any(target.entity.kind == "animals" for target in request.targets)
        ):
            try:
                from smaxtec.application.study_workbook import AutomaticStudyWorkbookService

                client_workbook = AutomaticStudyWorkbookService().create(folder, stop, progress)
            except Exception:
                warnings.append(
                    "The client analysis workbook could not be built from this collection. "
                    "The original data is safe; use Create study workbook to review it."
                )
        try:
            manifest["client_workbook"] = client_workbook.name if client_workbook else None
            manifest["client_workbook_sha256"] = (
                self._hash(client_workbook) if client_workbook else None
            )
            manifest["warnings"] = warnings
            _write_json(folder / "collection.json", manifest)
        except (OSError, ApiError):
            warnings.append(
                "The original collection is complete, but companion metadata could not "
                "be added to its manifest. Keep the collection folder together."
            )
            with suppress(OSError):
                (folder / ".collection.json.partial").unlink(missing_ok=True)
        progress(
            ApiProgress(
                "Direct API collection ready.",
                len(request.targets),
                len(request.targets),
            )
        )
        return ApiDownloadResult(
            folder,
            tuple(results),
            total_rows,
            cancelled=cancelled,
            warnings=tuple(warnings),
            analysis_csv=analysis_path,
            workbook=excel_path if request.excel else None,
            client_workbook=client_workbook,
        )

    def _target(
        self,
        target: ApiTarget,
        aggregation: str,
        raw_folder: Path,
        writer: csv.writer,
        analysis_writer: csv.writer,
        excel: _ExcelWriter | None,
        stop: Event,
    ) -> tuple[ApiFileResult, dict[str, Any], int]:
        stem = self._target_stem(target, raw_folder)
        record: dict[str, Any] = {
            "farm": target.entity.farm.name,
            "farm_id": target.entity.farm.id,
            "farm_timezone": target.entity.farm.timezone,
            "target_type": target.entity.kind,
            "target_id": target.entity.id,
            "animal_number": target.entity.number,
            "animal_name": target.entity.name,
            "official_id": target.entity.official_id,
            "from": target.start_date.isoformat(),
            "to": target.end_date.isoformat(),
            "requested_metrics": list(target.metrics),
            "study_event_utc": (
                target.study_event_utc.astimezone(UTC).isoformat()
                if target.study_event_utc is not None
                else None
            ),
        }
        raw_files: list[dict[str, Any]] = []
        row_count = 0
        try:
            available = self.client.metrics(target.entity, stop)
            available_codes = tuple(metric.code for metric in available)
            selected = target.metrics or available_codes
            missing = sorted(set(selected) - set(available_codes))
            if missing:
                raise ApiError(
                    "api_metrics",
                    "This target does not provide: " + ", ".join(missing[:10]),
                )
            if not selected:
                raise ApiError("api_metrics", "This target has no available measurements.")
            for chunk_index, (start, end) in enumerate(_chunks(target, aggregation), 1):
                _check_stop(stop)
                series = self.client.data(target.entity, selected, start, end, aggregation, stop)
                for series_index, item in enumerate(series, 1):
                    if not isinstance(item, dict):
                        raise ApiError("api_response", "smaXtec returned invalid measurement data.")
                    for row in _rows(
                        target,
                        item,
                        chunk_index,
                        series_index,
                        start,
                        end,
                        aggregation,
                    ):
                        writer.writerow(row.staging)
                        analysis_writer.writerow(row.analysis)
                        if excel:
                            excel.measurement_row(row.staging)
                        row_count += 1
                chunk_name = f"{stem}-part-{chunk_index:04d}.json"
                sha256 = _write_json(
                    raw_folder / chunk_name,
                    {
                        "from_utc": start.isoformat(),
                        "to_utc": end.isoformat(),
                        "series": series,
                    },
                )
                raw_files.append(
                    {
                        "file": "raw/" + chunk_name,
                        "sha256": sha256,
                        "from_utc": start.isoformat(),
                        "to_utc": end.isoformat(),
                    }
                )
            metadata_name = f"{stem}-metadata.json"
            metadata = {
                "request": record,
                "available_metrics": [
                    {"metric": metric.code, "available_units": list(metric.units)}
                    for metric in available
                ],
                "selected_metrics": list(selected),
                "raw_files": raw_files,
            }
            sha256 = _write_json(raw_folder / metadata_name, metadata)
            record.update(
                {
                    "status": "saved",
                    "metadata_file": "raw/" + metadata_name,
                    "metadata_sha256": sha256,
                    "raw_files": raw_files,
                    "rows": row_count,
                }
            )
            if excel:
                excel.summary_row(
                    (
                        f"{target.entity.farm.name} / {target.entity.label}",
                        f"{target.start_date:%d/%m/%Y} to {target.end_date:%d/%m/%Y}; "
                        f"{row_count:,} rows; {len(selected)} metrics",
                    )
                )
            return ApiFileResult(target, "saved", row_count, metadata_name), record, row_count
        except ApiCancelled:
            status = "partial" if raw_files or row_count else "cancelled"
            record.update(
                {
                    "status": status,
                    "detail": "Stopped by the user.",
                    "raw_files": raw_files,
                    "rows": row_count,
                }
            )
            return (
                ApiFileResult(target, status, row_count, detail="Stopped by the user."),
                record,
                row_count,
            )
        except ApiError as error:
            status = "partial" if raw_files or row_count else "failed"
            record.update(
                {
                    "status": status,
                    "detail": str(error),
                    "raw_files": raw_files,
                    "rows": row_count,
                }
            )
            return (
                ApiFileResult(target, status, row_count, detail=str(error)),
                record,
                row_count,
            )

    def _extras(
        self,
        request: ApiDownloadRequest,
        raw_folder: Path,
        excel: _ExcelWriter | None,
        stop: Event,
        progress: Callable[[ApiProgress], None],
    ) -> dict[str, Any]:
        if not request.include_health_index:
            return {}
        by_farm: dict[Any, list[ApiTarget]] = defaultdict(list)
        for target in request.targets:
            by_farm[target.entity.farm].append(target)
        extras: dict[str, Any] = {}
        for farm_index, (farm, targets) in enumerate(by_farm.items(), 1):
            _check_stop(stop)
            first = min(target.start_date for target in targets)
            last = max(target.end_date for target in targets)
            farm_record: dict[str, Any] = {"from": first.isoformat(), "to": last.isoformat()}
            if request.include_health_index:
                progress(ApiProgress(f"Downloading farm health index for {farm.name}…"))
                try:
                    health = self.client.health_index(farm, first, last, stop)
                    name = _safe_part(farm.name, f"farm-{farm_index}") + "-health-index.json"
                    sha = _write_json(raw_folder / name, health)
                    farm_record["health_index"] = {
                        "file": "raw/" + name,
                        "sha256": sha,
                        "records": len(health) if isinstance(health, list) else 1,
                    }
                    if excel:
                        records = health if isinstance(health, list) else [{"value": health}]
                        excel.json_sheet(f"Health index {farm_index:02d}", records)
                except ApiError as error:
                    farm_record["health_index"] = {"status": "failed", "detail": str(error)}
            extras[farm.id] = farm_record
        return extras

    @staticmethod
    def _folder(root: Path, name: str) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = root / f"{_safe_part(name, 'Herd-data')}-{stamp}-{uuid4().hex[:8]}"
        folder.mkdir()
        return folder

    @staticmethod
    def _target_stem(target: ApiTarget, root: Path) -> str:
        prefix = {"animals": "cow", "groups": "group", "devices": "device"}[target.entity.kind]
        identity = target.entity.number or target.entity.name or target.entity.id
        stem = (
            f"{prefix}-{_safe_part(identity, target.entity.id[:12])}-"
            f"{target.start_date:%Y%m%d}-{target.end_date:%Y%m%d}"
        )
        candidate = stem
        suffix = 2
        while (root / f"{candidate}-metadata.json").exists():
            candidate = f"{stem}-{suffix:02d}"
            suffix += 1
        return candidate

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
