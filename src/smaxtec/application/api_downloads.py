"""Direct API collection with raw lineage, CSV output and an optional Excel workbook."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any, Protocol
from uuid import uuid4

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


def _rows(
    target: ApiTarget,
    series: dict[str, Any],
    chunk_index: int,
    chunk_start: datetime,
    chunk_end: datetime,
) -> Iterator[tuple[str, ...]]:
    metric = _scalar(series.get("metric"))
    unit = _scalar(series.get("unit"))
    for point in _series_points(series.get("data")):
        timestamp, value, raw = _point_parts(point)
        yield (
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
        )


class _ExcelWriter:
    def __init__(self, path: Path) -> None:
        import xlsxwriter

        self.path = path
        self.workbook = xlsxwriter.Workbook(str(path), {"constant_memory": True})
        self.header = self.workbook.add_format(
            {"bold": True, "font_color": "#FFFFFF", "bg_color": "#245D43"}
        )
        self.wrap = self.workbook.add_format({"text_wrap": True, "valign": "top"})
        self._sheet_index = 0
        self._sheet = None
        self._row = EXCEL_MAX_DATA_ROWS + 1
        self._summary = self.workbook.add_worksheet("Collection summary")
        self._summary.set_column(0, 0, 25)
        self._summary.set_column(1, 1, 80)
        self._summary_row = 0
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
        if self._row > EXCEL_MAX_DATA_ROWS:
            self._sheet_index += 1
            self._sheet = self.workbook.add_worksheet(f"Measurements {self._sheet_index:03d}")
            self._sheet.freeze_panes(1, 0)
            self._sheet.autofilter(0, 0, 0, len(MEASUREMENT_HEADERS) - 1)
            self._sheet.set_column(0, 13, 18)
            self._sheet.set_column(14, 15, 24)
            self._sheet.set_column(16, 16, 45)
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

    def close(self) -> None:
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
        excel_partial = folder / f".{request.name}.partial.xlsx"
        excel_path = folder / f"{request.name}.xlsx"
        excel = _ExcelWriter(excel_partial) if request.excel else None
        results: list[ApiFileResult] = []
        warnings: list[str] = []
        manifest_targets: list[dict[str, Any]] = []
        total_rows = 0
        cancelled = False
        extras: dict[str, Any] = {}
        with csv_partial.open("x", encoding="utf-8-sig", newline="") as csv_handle:
            writer = csv.writer(csv_handle)
            writer.writerow(MEASUREMENT_HEADERS)
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
                        target, request.aggregation, raw_folder, writer, excel, stop
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
                if excel:
                    excel.close()
        csv_partial.replace(csv_path)
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
            "format_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "collection_name": request.name,
            "aggregation": request.aggregation,
            "measurement_csv": csv_path.name,
            "measurement_csv_sha256": self._hash(csv_path),
            "excel": excel_path.name if request.excel else None,
            "excel_sha256": self._hash(excel_path) if request.excel else None,
            "cancelled": cancelled,
            "total_measurement_rows": total_rows,
            "targets": manifest_targets,
            "extras": extras,
            "warnings": warnings,
        }
        _write_json(folder / "collection.json", manifest)
        progress(
            ApiProgress(
                "Direct API collection ready.",
                len(request.targets),
                len(request.targets),
            )
        )
        return ApiDownloadResult(
            folder, tuple(results), total_rows, cancelled=cancelled, warnings=tuple(warnings)
        )

    def _target(
        self,
        target: ApiTarget,
        aggregation: str,
        raw_folder: Path,
        writer: csv.writer,
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
                for item in series:
                    if not isinstance(item, dict):
                        raise ApiError("api_response", "smaXtec returned invalid measurement data.")
                    for row in _rows(target, item, chunk_index, start, end):
                        writer.writerow(row)
                        if excel:
                            excel.measurement_row(row)
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
