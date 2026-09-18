"""Client-defined, opt-in study view of an existing direct-API collection.

This module never changes the collection's source files or manifest. Metric roles and
time zero are explicit user choices; exact points are never replaced by nearest ones.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from bisect import bisect_left
from collections import Counter, defaultdict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, stdev
from threading import Event
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import xlsxwriter

from smaxtec.application.api_data import ApiCancelled, ApiError, ApiLactation, ApiProgress

CORE_HEADERS = (
    "No",
    "Cow",
    "Lact",
    "DIM",
    "Tn",
    "Talert proxy",
    "T0",
    "T6",
    "T12",
    "T18",
    "T24",
    "R20 proxy",
    "AN",
    "AT0",
    "AT6",
    "AT12",
    "AT18",
    "AT24",
    "Rn",
    "Rl",
    "%drop",
    "Rback",
    "RT0",
    "RT24",
    "RT48",
    "RT72",
    "RT96",
    "RT120",
)
AUTOMATIC_HEADERS = (
    "No",
    "Cow",
    "Lact",
    "DIM",
    "Tn",
    "Talert",
    "To",
    "T6",
    "T12",
    "T18",
    "T24",
    "R20",
    "AN",
    "AT0",
    "AT6",
    "AT12",
    "AT18",
    "AT24",
    "Rn",
    "Rl",
    "%drop",
    "Rback",
    "Rdown",
    "RT0",
    "RT24",
    "RT48",
    "RT72",
    "RT96",
    "R120",
    "RA1",
    "RA2",
    "RA3",
    "RA4",
    "RA5",
)
REQUIRED_CSV = {
    "target_type",
    "target_id",
    "farm_id",
    "requested_from",
    "requested_to",
    "metric",
    "unit",
    "timestamp_utc",
    "value",
}
MAX_ANALYSIS_ROWS = 3_000_000
MAX_CASES = 500
MAX_OFFSETS = 241


@dataclass(frozen=True)
class StudyCase:
    index: int
    farm: str
    farm_id: str
    target_id: str
    cow: str
    from_date: str
    to_date: str
    timezone: str
    status: str
    event_utc: datetime | None = None
    lactations: tuple[ApiLactation, ...] = ()

    @property
    def key(self) -> tuple[str, str, str, str]:
        return self.farm_id, self.target_id, self.from_date, self.to_date


@dataclass(frozen=True)
class StudySource:
    folder: Path
    csv_path: Path
    csv_sha256: str
    cases: tuple[StudyCase, ...]
    pairs: tuple[tuple[str, str], ...]
    resolution: str

    @classmethod
    def load(cls, folder: Path, stop: Event | None = None) -> StudySource:
        stop = stop or Event()
        folder = folder.resolve()
        manifest_path = folder / "collection.json"
        csv_path = folder / "analysis_ready.csv"
        if not manifest_path.is_file() or not csv_path.is_file():
            raise ApiError("study_source", "Choose a completed direct-API collection folder.")
        try:
            if manifest_path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("manifest too large")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected = manifest["analysis_csv_sha256"]
            if manifest.get("analysis_csv") != csv_path.name or manifest.get("format_version") != 2:
                raise ValueError("incompatible collection")
            cases = []
            for index, entry in enumerate(manifest["targets"], 1):
                if entry.get("target_type") != "animals":
                    continue
                cases.append(
                    StudyCase(
                        index,
                        str(entry["farm"]),
                        str(entry["farm_id"]),
                        str(entry["target_id"]),
                        str(entry["animal_number"]),
                        str(entry["from"]),
                        str(entry["to"]),
                        str(entry["farm_timezone"]),
                        str(entry["status"]),
                        (
                            _manifest_event(entry["study_event_utc"])
                            if entry.get("study_event_utc")
                            else None
                        ),
                        _manifest_lactations(entry.get("lactations", [])),
                    )
                )
            if not cases or len(cases) > MAX_CASES:
                raise ValueError("no supported cow rows or too many cow rows")
            digest = hashlib.sha256()
            with csv_path.open("rb") as handle:
                while block := handle.read(1024 * 1024):
                    if stop.is_set():
                        raise ApiCancelled
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError("analysis CSV hash changed")
            pairs: set[tuple[str, str]] = set()
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not REQUIRED_CSV.issubset(reader.fieldnames or ()):
                    raise ValueError("analysis CSV schema changed")
                for index, row in enumerate(reader, 1):
                    if stop.is_set():
                        raise ApiCancelled
                    if index > MAX_ANALYSIS_ROWS:
                        raise ValueError("too many measurement rows")
                    if row["target_type"] == "animals" and row["metric"]:
                        pairs.add((row["metric"], row["unit"]))
            if not pairs:
                raise ValueError("no cow measurements")
        except ApiCancelled:
            raise
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise ApiError(
                "study_source",
                "This collection is incomplete, changed or too large for a study workbook. "
                "Use an intact direct-API collection with cow measurements.",
            ) from None
        return cls(
            folder,
            csv_path,
            expected,
            tuple(cases),
            tuple(sorted(pairs)),
            str(manifest.get("aggregation", "")),
        )


def parse_event_time(text: str, timezone: str) -> datetime:
    """Strict farm-local DD/MM/YYYY HH:MM, rejecting DST gaps and ambiguous folds."""
    try:
        naive = datetime.strptime(text.strip(), "%d/%m/%Y %H:%M")
        if naive.strftime("%d/%m/%Y %H:%M") != text.strip():
            raise ValueError
        zone = ZoneInfo(timezone)
        candidates = []
        for fold in (0, 1):
            local = naive.replace(tzinfo=zone, fold=fold)
            utc = local.astimezone(UTC)
            if utc.astimezone(zone).replace(tzinfo=None) == naive:
                candidates.append(utc)
        if len(set(candidates)) != 1:
            raise ValueError
        return candidates[0]
    except (ValueError, KeyError):
        raise ValueError(
            "Enter an unambiguous farm-local time as DD/MM/YYYY HH:MM; "
            "the selected time may fall in a daylight-saving change."
        ) from None


def _manifest_event(text: str) -> datetime:
    """Never interpret a timezone-free stored event in the computer's local zone."""
    event = datetime.fromisoformat(text)
    if event.tzinfo is None or event.utcoffset() is None:
        raise ValueError("event timezone missing")
    return event.astimezone(UTC)


def _manifest_lactations(value: Any) -> tuple[ApiLactation, ...]:
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError("invalid lactation history")
    result = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("invalid lactation history")
        number = entry.get("number")
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError("invalid lactation number")
        calving = _manifest_event(entry.get("calving_utc", ""))
        dry_off = _manifest_event(entry["dry_off_utc"]) if entry.get("dry_off_utc") else None
        result.append(ApiLactation(number, calving, dry_off))
    return tuple(sorted(result, key=lambda item: item.calving_utc))


@dataclass(frozen=True)
class StudySettings:
    events: tuple[tuple[tuple[str, str, str, str], datetime], ...]
    normal_temp: tuple[str, str] | None
    temperature: tuple[str, str] | None
    activity: tuple[str, str] | None
    rumination: tuple[str, str] | None
    threshold_c: float = 0.8
    followup_days: int = 20
    temp_step_hours: int = 6
    temp_horizon_hours: int = 24
    rum_step_hours: int = 24
    rum_horizon_hours: int = 120
    aligned_before_hours: int = 24
    aligned_after_hours: int = 120
    aligned_step_hours: int = 6
    unanchored_cases: tuple[tuple[str, str, str, str], ...] = ()
    provisional_cases: tuple[tuple[str, str, str, str], ...] = ()
    rumination_minutes: bool = False
    automatic: bool = False

    def validate(self, source: StudySource) -> None:
        cases = {case.key for case in source.cases}
        events = dict(self.events)
        if len(events) != len(self.events) or set(events) != cases:
            raise ValueError("Enter one time zero for every cow/case in the collection.")
        roles = (self.normal_temp, self.temperature, self.activity, self.rumination)
        selected = tuple(pair for pair in roles if pair is not None)
        if (not selected and not self.automatic) or any(
            pair not in source.pairs for pair in selected
        ):
            raise ValueError(
                "Choose at least one source code/unit pair from this collection. "
                "Unmapped fields will remain blank."
            )
        if self.normal_temp is not None and self.normal_temp == self.temperature:
            raise ValueError(
                "Normal temperature and temperature without drinking cycles must differ."
            )
        if len(set(selected)) != len(selected):
            raise ValueError("Choose a distinct source measurement for each study role.")
        if not set(self.unanchored_cases).issubset(cases):
            raise ValueError("An automatic study case is not part of this collection.")
        if not set(self.provisional_cases).issubset(cases):
            raise ValueError("A provisional study case is not part of this collection.")
        if self.rumination_minutes and self.rumination != ("rum_index", "seconds"):
            raise ValueError("Only rum_index/seconds may be converted to minutes here.")
        celsius_units = {"c", "celsius", "°c", "℃", "degc", "degrees celsius", "degree_celsius"}
        if any(
            pair[1].strip().casefold() not in celsius_units
            for pair in (
                self.normal_temp,
                self.temperature,
            )
            if pair is not None
        ):
            raise ValueError(
                "The two temperature source units must be Celsius for the requested "
                "degree-above-normal calculation. No unit conversion is applied."
            )
        if not (0 <= self.threshold_c <= 5 and 1 <= self.followup_days <= 60):
            raise ValueError("Temperature differential must be 0–5 °C and follow-up 1–60 days.")
        for step, horizon in (
            (self.temp_step_hours, self.temp_horizon_hours),
            (self.rum_step_hours, self.rum_horizon_hours),
            (self.aligned_step_hours, self.aligned_before_hours + self.aligned_after_hours),
        ):
            if step < 1 or horizon < 1 or horizon > 1440 or horizon // step > MAX_OFFSETS:
                raise ValueError("Choose positive time steps and a horizon of at most 60 days.")
        if self.aligned_before_hours < 0 or self.aligned_after_hours < 1:
            raise ValueError("Aligned time must include at least one post-event hour.")
        for case in source.cases:
            event = events[case.key]
            if event.tzinfo is None or event.utcoffset() is None:
                raise ValueError("Each time zero must include a valid farm timezone.")
            local = event.astimezone(ZoneInfo(case.timezone))
            if not (case.from_date <= local.date().isoformat() <= case.to_date):
                raise ValueError(
                    f"Cow {case.cow}: time zero is outside its reviewed From/To dates."
                )


@dataclass(frozen=True)
class _Point:
    time: datetime
    value: float


def _number(text: str) -> float | None:
    try:
        value = float(text)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _sample_stats(
    values: list[float],
) -> tuple[int, float | None, float | None, float | None, float | None]:
    if not values:
        return 0, None, None, None, None
    average = mean(values)
    if len(values) < 2:
        return 1, average, None, None, None
    sample_sd = stdev(values)
    margin = 1.96 * sample_sd / math.sqrt(len(values))
    return len(values), average, sample_sd, average - margin, average + margin


class StudyWorkbookService:
    """Produce a separate, non-overwriting XLSX and explicit QC from hashed CSV."""

    def create(
        self,
        source: StudySource,
        settings: StudySettings,
        stop: Event,
        progress: Callable[[ApiProgress], None],
        *,
        file_stem: str = "client-study",
    ) -> Path:
        if file_stem not in {"client-study", "client-analysis"}:
            raise ValueError("Unsupported study workbook name.")
        settings.validate(source)
        if stop.is_set():
            raise ApiCancelled
        with source.csv_path.open("rb") as handle:
            digest = hashlib.sha256()
            while chunk := handle.read(1024 * 1024):
                if stop.is_set():
                    raise ApiCancelled
                digest.update(chunk)
        if digest.hexdigest() != source.csv_sha256:
            raise ApiError(
                "study_source_changed",
                "The selected collection changed since it was loaded. Choose it again.",
            )
        progress(ApiProgress("Reading validated cow measurements…", 0, 3))
        chosen = {
            settings.normal_temp,
            settings.temperature,
            settings.activity,
            settings.rumination,
        } - {None}
        case_keys = {case.key for case in source.cases}
        raw: dict[tuple[tuple[str, str, str, str], tuple[str, str]], dict[datetime, set[float]]] = (
            defaultdict(lambda: defaultdict(set))
        )
        quality: Counter[str] = Counter()
        with source.csv_path.open(encoding="utf-8-sig", newline="") as handle:
            for index, row in enumerate(csv.DictReader(handle), 1):
                if index % 4096 == 0 and stop.is_set():
                    raise ApiCancelled
                if index > MAX_ANALYSIS_ROWS:
                    raise ApiError(
                        "study_size", "This collection is too large for a study workbook."
                    )
                key = (
                    row["farm_id"],
                    row["target_id"],
                    row["requested_from"],
                    row["requested_to"],
                )
                pair = row["metric"], row["unit"]
                if key not in case_keys or pair not in chosen:
                    continue
                if not row["timestamp_utc"]:
                    quality["ambiguous_source_time"] += 1
                    continue
                try:
                    stamp = datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00"))
                    stamp = stamp.astimezone(UTC)
                except ValueError:
                    quality["ambiguous_source_time"] += 1
                    continue
                value = _number(row["value"])
                if value is None:
                    quality["non_numeric_value"] += 1
                    continue
                if settings.rumination_minutes and pair == settings.rumination:
                    value /= 60
                bucket = raw[(key, pair)][stamp]
                if value in bucket:
                    quality["identical_duplicate_collapsed"] += 1
                bucket.add(value)
        series: dict[tuple[tuple[str, str, str, str], tuple[str, str]], tuple[_Point, ...]] = {}
        conflicts: dict[tuple[tuple[str, str, str, str], tuple[str, str]], set[datetime]] = {}
        for key_pair, by_time in raw.items():
            conflicts[key_pair] = {stamp for stamp, values in by_time.items() if len(values) > 1}
            quality["conflicting_same_timestamp_excluded"] += len(conflicts[key_pair])
            series[key_pair] = tuple(
                _Point(stamp, next(iter(values)))
                for stamp, values in sorted(by_time.items())
                if len(values) == 1
            )
        progress(ApiProgress("Calculating exact event-relative study values…", 1, 3))
        suffix = 0
        while True:
            name = f"{file_stem}.xlsx" if suffix == 0 else f"{file_stem}-{suffix}.xlsx"
            output = source.folder / name
            if not output.exists():
                break
            suffix += 1
        temporary = source.folder / f".{file_stem}-{uuid4().hex}.partial.xlsx"
        try:
            self._write(temporary, source, settings, series, conflicts, quality, stop)
            if stop.is_set():
                raise ApiCancelled
            temporary.replace(output)
        except (ApiCancelled, ApiError):
            raise
        except (OSError, xlsxwriter.exceptions.XlsxWriterException):
            raise ApiError(
                "study_output",
                "Could not save the study workbook. Check free space and that the collection "
                "folder is writable.",
            ) from None
        except Exception:
            raise ApiError(
                "study_output",
                "The study workbook could not finish. Original source files are unchanged; "
                "retry with this collection or a smaller one.",
            ) from None
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        progress(ApiProgress("Client study workbook ready.", 3, 3))
        return output

    def _analysis_summary(
        self,
        workbook,
        cases,
        events,
        settings,
        series,
        baselines,
        title,
        header,
        number,
        muted,
        stop,
    ) -> None:
        """Client-example-style absolute and normal-relative cohort blocks."""
        groups = (
            ("Temperature", "temperature", settings.temperature, (0, 6, 12, 18, 24), 5),
            ("Activity", "activity", settings.activity, (0, 6, 12, 18, 24), 12),
            ("Rumination", "rumination", settings.rumination, (0, 24, 48, 72, 96, 120), 21),
        )
        stats: dict[
            tuple[str, str, int], tuple[int, float | None, float | None, float | None, float | None]
        ] = {}
        for _name, role, pair, offsets, _first_column in groups:
            for offset in offsets:
                absolute = []
                relative = []
                for case in cases:
                    if stop.is_set():
                        raise ApiCancelled
                    if case.key in settings.unanchored_cases:
                        continue
                    stamp = events[case.key] + timedelta(hours=offset)
                    if role == "activity":
                        values = self._values(series, case, pair, stamp - timedelta(hours=6), stamp)
                        value = mean(values) if values else None
                    else:
                        value = self._exact(series, case, pair, stamp)
                    if value is None:
                        continue
                    absolute.append(value)
                    baseline = baselines[case.key][role]
                    if baseline is not None:
                        relative.append(value - baseline)
                stats[role, "absolute", offset] = _sample_stats(absolute)
                stats[role, "relative", offset] = _sample_stats(relative)
        sheet = workbook.add_worksheet("Analysis")
        sheet.hide_gridlines(2)
        sheet.set_column(0, 0, 23)
        sheet.set_column(1, 27, 13)
        sheet.write_string(0, 0, "All requested cows · cohort analysis", title)
        sheet.write_string(
            1,
            0,
            "Named hours are exact elapsed hours from each supplied T0. Activity is a "
            "preceding 6-hour mean. Missing T0/source readings never enter the cohort.",
            muted,
        )
        labels = ("n", "Mean", "Sample SD", "Lower 95%", "Upper 95%")
        for start_row, variant in ((2, "absolute"), (10, "relative")):
            for name, _role, _pair, offsets, first_column in groups:
                sheet.write_string(
                    start_row,
                    first_column - 1,
                    name + (" absolute" if variant == "absolute" else " vs normal"),
                    header,
                )
                for column, offset in enumerate(offsets, first_column):
                    sheet.write_number(start_row, column, offset, header)
            for shift, text in enumerate(labels):
                row = start_row + 1 + shift
                for _name, role, _pair, offsets, first_column in groups:
                    sheet.write_string(row, first_column - 1, text)
                    for column, offset in enumerate(offsets, first_column):
                        value = stats[role, variant, offset][shift]
                        if value is not None:
                            sheet.write_number(row, column, value, number)
        for name, _role, pair, offsets, first_column in groups:
            for start_row, label in ((3, "Absolute"), (11, "Relative")):
                if pair is None or all(case.key in settings.unanchored_cases for case in cases):
                    continue
                chart = workbook.add_chart({"type": "line"})
                for row, series_name, color in (
                    (start_row + 1, "Mean", "#245D43"),
                    (start_row + 3, "Lower 95%", "#80B25E"),
                    (start_row + 4, "Upper 95%", "#80B25E"),
                ):
                    chart.add_series(
                        {
                            "name": series_name,
                            "categories": [
                                "Analysis",
                                2 if start_row == 3 else 10,
                                first_column,
                                2 if start_row == 3 else 10,
                                first_column + len(offsets) - 1,
                            ],
                            "values": [
                                "Analysis",
                                row,
                                first_column,
                                row,
                                first_column + len(offsets) - 1,
                            ],
                            "line": {"color": color},
                        }
                    )
                chart.set_title({"name": f"{name} · {label.lower()} mean and 95% limits"})
                chart.set_x_axis({"name": "Elapsed hours from T0"})
                chart.set_y_axis(
                    {
                        "name": "Study units: minutes"
                        if role == "rumination" and settings.rumination_minutes
                        else f"Source units: {pair[1]}"
                    }
                )
                chart.set_legend({"position": "bottom"})
                sheet.insert_chart(
                    20 if start_row == 3 else 40,
                    first_column - 1,
                    chart,
                    {"x_scale": 1.2, "y_scale": 1.1},
                )

    @staticmethod
    def _graphs(workbook, cases, settings, title, muted) -> None:
        """One intact chart pair per metric, referenced from aligned summaries."""
        sheet = workbook.add_worksheet("Study graphs")
        sheet.hide_gridlines(2)
        sheet.set_column(0, 23, 11)
        sheet.write_string(0, 0, "Cohort study graphs", title)
        sheet.write_string(
            1,
            0,
            "Available-cow mean and 95% limits; relative plots subtract each cow's normal.",
            muted,
        )
        if all(case.key in settings.unanchored_cases for case in cases):
            sheet.write_string(
                3,
                0,
                "No supplied study T0 yet. Enter the cow's treatment/key-event time "
                "to calculate aligned cohort graphs.",
                muted,
            )
            return
        stats_start = len(cases) + 1
        offsets = list(
            range(
                -settings.aligned_before_hours,
                settings.aligned_after_hours + 1,
                settings.aligned_step_hours,
            )
        )
        if 0 not in offsets:
            offsets.append(0)
        last_row = 2 + len(offsets)
        for metric_index, (name, unit) in enumerate(
            (
                (
                    "Temperature aligned",
                    settings.temperature[1] if settings.temperature else "unmapped",
                ),
                ("Activity aligned", settings.activity[1] if settings.activity else "unmapped"),
                (
                    "Rumination aligned",
                    (
                        "minutes"
                        if settings.rumination_minutes
                        else settings.rumination[1]
                        if settings.rumination
                        else "unmapped"
                    ),
                ),
            )
        ):
            for relative in (False, True):
                chart = workbook.add_chart({"type": "line"})
                start_col = stats_start + (6 if relative else 1)
                for column, label, color in (
                    (start_col, "Mean", "#245D43"),
                    (start_col + 2, "Lower 95%", "#80B25E"),
                    (start_col + 3, "Upper 95%", "#80B25E"),
                ):
                    chart.add_series(
                        {
                            "name": label,
                            "categories": [name, 3, 0, last_row, 0],
                            "values": [name, 3, column, last_row, column],
                            "line": {"color": color, "width": 2 if label == "Mean" else 1},
                        }
                    )
                metric = name.split()[0]
                chart.set_title(
                    {"name": f"{metric}: {'change vs normal' if relative else 'absolute mean'}"}
                )
                chart.set_x_axis({"name": "Hours from time zero"})
                chart.set_y_axis({"name": f"{'Change in ' if relative else ''}{unit}"})
                chart.set_legend({"position": "bottom"})
                sheet.insert_chart(
                    4 + metric_index * 21,
                    12 if relative else 0,
                    chart,
                    {"x_scale": 1.55, "y_scale": 1.35},
                )

    @staticmethod
    def _values(
        series: dict,
        case: StudyCase,
        pair: tuple[str, str] | None,
        start: datetime,
        end: datetime,
    ) -> list[float]:
        points = series.get((case.key, pair), ())
        first = bisect_left(points, start, key=lambda point: point.time)
        last = bisect_left(points, end, key=lambda point: point.time)
        return [point.value for point in points[first:last]]

    @staticmethod
    def _exact(
        series: dict,
        case: StudyCase,
        pair: tuple[str, str] | None,
        at: datetime,
    ) -> float | None:
        points = series.get((case.key, pair), ())
        index = bisect_left(points, at, key=lambda point: point.time)
        return points[index].value if index < len(points) and points[index].time == at else None

    @staticmethod
    def _lactation_at(case: StudyCase, at: datetime) -> ApiLactation | None:
        """Return the latest documented lactation cycle containing ``at``."""
        eligible = (
            lactation
            for lactation in case.lactations
            if lactation.calving_utc <= at
            and (lactation.dry_off_utc is None or at < lactation.dry_off_utc)
        )
        return max(eligible, key=lambda item: item.calving_utc, default=None)

    @staticmethod
    def _rumination_timing_days(
        series: dict,
        case: StudyCase,
        pair: tuple[str, str] | None,
        start: datetime,
        low_window_end: datetime,
        recovery_end: datetime,
        normal: float | None,
    ) -> tuple[float | None, float | None]:
        """Return (Rback, Rdown) in elapsed days around the first Rl minimum.

        Rdown is T0 to the first observed five-day minimum. Rback is that minimum
        to the first later observation at or above the pre-event Rn baseline.
        """
        if pair is None or normal is None or normal <= 0:
            return None, None
        points = series.get((case.key, pair), ())
        first = bisect_left(points, start, key=lambda point: point.time)
        last = bisect_left(points, low_window_end, key=lambda point: point.time)
        window = points[first:last]
        if not window:
            return None, None
        low = min(point.value for point in window)
        low_index = next(index for index, point in enumerate(window) if point.value == low)
        low_time = window[low_index].time
        rdown = (low_time - start).total_seconds() / timedelta(days=1).total_seconds()
        recovery_last = bisect_left(points, recovery_end, key=lambda point: point.time)
        for point in points[first + low_index + 1 : recovery_last]:
            if point.value >= normal:
                rback = (point.time - low_time).total_seconds() / timedelta(days=1).total_seconds()
                return rback, rdown
        return None, rdown

    def _automatic_aligned_sheet(
        self,
        workbook,
        source: StudySource,
        settings: StudySettings,
        series: dict,
        events: dict,
        title,
        header,
        number,
        integer,
        muted,
        stop: Event,
    ) -> None:
        """Put T/A/R cow traces and cohort confidence limits on one extra sheet."""
        sheet = workbook.add_worksheet("Aligned data")
        sheet.hide_gridlines(2)
        sheet.set_tab_color("#4C8854")
        sheet.set_column(0, 0, 15)
        sheet.set_column(1, 1, 8)
        sheet.set_column(2, 4, 14)
        if source.cases:
            sheet.set_column(5, 4 + len(source.cases), 18)
        offsets = list(range(-24, 121, 6))
        block_height = len(offsets) + 25
        metrics = (
            (
                "Temperature aligned",
                settings.temperature,
                "Exact temperature without drinking cycles at each six-hour offset.",
                "temperature",
            ),
            (
                "Activity aligned",
                settings.activity,
                "Mean activity in the six hours ending at each offset.",
                "activity",
            ),
            (
                "Rumination aligned",
                settings.rumination,
                "Exact rumination at each six-hour offset; seconds are displayed as minutes.",
                "rumination",
            ),
        )
        event_by_case = events
        for block_index, (name, pair, description, role) in enumerate(metrics):
            start_row = block_index * block_height
            header_row = start_row + 2
            event_row = start_row + 3
            data_row = start_row + 4
            sheet.write_string(start_row, 0, name, title)
            sheet.write_string(
                start_row + 1,
                0,
                description + " Hour 0 is each cow's own Study T0; labelled period anchors "
                "remain non-clinical.",
                muted,
            )
            headings = ("Hours from T0", "n", "Mean", "Lower 95%", "Upper 95%") + tuple(
                f"Cow {case.cow} · case {case.index}" for case in source.cases
            )
            for column, text in enumerate(headings):
                sheet.write_string(header_row, column, text, header)
            sheet.write_string(event_row, 0, "Farm-local T0", header)
            for column, case in enumerate(source.cases, 5):
                event = event_by_case[case.key]
                text = event.astimezone(ZoneInfo(case.timezone)).strftime("%d/%m/%Y %H:%M %Z")
                if case.key in settings.provisional_cases:
                    text += " · period anchor"
                sheet.write_string(event_row, column, text, muted)
            for offset_index, offset in enumerate(offsets):
                if stop.is_set():
                    raise ApiCancelled
                row = data_row + offset_index
                sheet.write_number(row, 0, offset, integer)
                observed = []
                for column, case in enumerate(source.cases, 5):
                    event = event_by_case[case.key]
                    stamp = event + timedelta(hours=offset)
                    if role == "activity":
                        values = self._values(series, case, pair, stamp - timedelta(hours=6), stamp)
                        value = mean(values) if values else None
                    else:
                        value = self._exact(series, case, pair, stamp)
                    if value is not None:
                        sheet.write_number(row, column, value, number)
                        observed.append(value)
                n, average, _sd, low, high = _sample_stats(observed)
                sheet.write_number(row, 1, n, integer)
                for column, value in enumerate((average, low, high), 2):
                    if value is not None:
                        sheet.write_number(row, column, value, number)
            chart = workbook.add_chart({"type": "line"})
            for column, label, color, width in (
                (2, "Mean", "#245D43", 2.25),
                (3, "Lower 95%", "#80B25E", 1),
                (4, "Upper 95%", "#80B25E", 1),
            ):
                chart.add_series(
                    {
                        "name": label,
                        "categories": ["Aligned data", data_row, 0, data_row + len(offsets) - 1, 0],
                        "values": [
                            "Aligned data",
                            data_row,
                            column,
                            data_row + len(offsets) - 1,
                            column,
                        ],
                        "line": {"color": color, "width": width},
                    }
                )
            chart.set_title({"name": f"{name} · mean and 95% confidence limits"})
            chart.set_x_axis({"name": "Hours from T0"})
            chart.set_y_axis(
                {
                    "name": (
                        "Minutes"
                        if role == "rumination" and settings.rumination_minutes
                        else pair[1]
                        if pair
                        else "Unmapped"
                    )
                }
            )
            chart.set_legend({"position": "bottom"})
            sheet.insert_chart(
                data_row + len(offsets) + 2,
                0,
                chart,
                {"x_scale": 1.55, "y_scale": 1.15},
            )

    def _write(
        self,
        path: Path,
        source: StudySource,
        settings: StudySettings,
        series: dict,
        conflicts: dict,
        quality: Counter[str],
        stop: Event,
    ) -> None:
        # Excel tables are unavailable in XlsxWriter's constant-memory mode.
        # The automatic view is bounded to 500 cow rows; keep streaming for the
        # larger guided workbook with its many aligned/time-point sheets.
        workbook = xlsxwriter.Workbook(str(path), {"constant_memory": not settings.automatic})
        workbook.set_properties({"title": "Client study workbook", "author": "SmaxTec Workbench"})
        title = workbook.add_format({"bold": True, "font_size": 22, "font_color": "#193E34"})
        header = workbook.add_format(
            {"bold": True, "font_color": "#FFFFFF", "bg_color": "#245D43", "text_wrap": True}
        )
        number = workbook.add_format({"num_format": "0.00"})
        integer = workbook.add_format({"num_format": "0"})
        percent = workbook.add_format({"num_format": "0.0%"})
        muted = workbook.add_format({"font_color": "#63776E", "text_wrap": True})
        cases_sheet = workbook.add_worksheet(
            "Cow analysis" if settings.automatic else "Client parameters"
        )
        cases_sheet.hide_gridlines(2)
        cases_sheet.freeze_panes(2 if settings.automatic else 3, 2)
        cases_sheet.set_tab_color("#176384" if settings.automatic else "#4C8854")
        cases_sheet.set_column(0, 0, 6 if settings.automatic else 7)
        cases_sheet.set_column(1, 1, 9 if settings.automatic else 15)
        cases_sheet.set_column(2, 3, 7 if settings.automatic else 10)
        cases_sheet.set_column(
            4, 33 if settings.automatic else 27, 8.5 if settings.automatic else 13
        )
        if settings.automatic:
            cases_sheet.set_column(11, 11, 7)
            cases_sheet.set_column(20, 20, 8)
            cases_sheet.set_row(1, 25)
            cases_sheet.add_table(
                1,
                0,
                1 + len(source.cases),
                len(AUTOMATIC_HEADERS) - 1,
                {
                    "name": "CowAnalysis",
                    "style": "Table Style Medium 2",
                    "columns": [{"header": name} for name in AUTOMATIC_HEADERS],
                },
            )
            cases_sheet.write_comment(
                1,
                6,
                "To is the client's label for T0 temperature, not the collection end "
                "date. Without a supplied Study T0, exact time points use the cow's "
                "farm-local From date at 00:00 as a period anchor, NOT treatment time.",
            )
            cases_sheet.write_comment(
                1,
                5,
                "Proxy: maximum temperature without drinking cycles in the five "
                "days before time zero; not an observed alert event.",
            )
            cases_sheet.write_comment(
                1,
                2,
                "Lactation number returned by the smaXtec animal lifecycle for the "
                "cycle containing time zero. Older collections may not contain it.",
            )
            cases_sheet.write_comment(
                1,
                3,
                "Days in milk at time zero: farm-local calendar days since that "
                "lactation's calving date. Blank if lifecycle data is unavailable "
                "or the cow was already dry.",
            )
            cases_sheet.write_comment(
                1,
                4,
                "Mean normal-temperature metric over the seven days before time zero. "
                "The downloaded period must include that history.",
            )
            cases_sheet.write_comment(
                1,
                11,
                f"Proxy: distinct temperature measurements above Tn + "
                f"{settings.threshold_c:g} Celsius in the first "
                f"{settings.followup_days} days. The saved Public API collection "
                "does not contain a reliably typed temperature-alert event stream.",
            )
            cases_sheet.write_comment(
                1,
                20,
                "Stored as 1 - Rl/Rn; displayed as a decimal fraction (0.13 means "
                "13%) to match the supplied ASPI sheet.",
            )
            cases_sheet.write_comment(
                1,
                12,
                "Mean activity over the fourteen days before time zero. The "
                "downloaded period must include that history.",
            )
            cases_sheet.write_comment(
                1,
                18,
                "Mean rumination over the seven days before time zero. The calculation "
                "divides by 60 to display source rumination seconds as minutes; the "
                "source CSV remains unchanged.",
            )
            cases_sheet.write_comment(
                1,
                21,
                "Elapsed days from the first Rl minimum in the five days after T0 "
                "until the first later observed rumination reading at or above Rn. "
                "Recovery is searched through the available requested period.",
            )
            cases_sheet.write_comment(
                1,
                22,
                "Rdown: elapsed days from T0 (the Rn starting point) to the first "
                "occurrence of Rl in the five days after T0.",
            )
            for column, day_number in enumerate(range(1, 6), 29):
                cases_sheet.write_comment(
                    1,
                    column,
                    f"RA{day_number}: arithmetic mean of every valid rumination "
                    f"measurement in elapsed day {day_number} after T0. Source "
                    "rumination seconds are displayed as minutes.",
                )
        else:
            cases_sheet.set_column(28, 28, 24)
            cases_sheet.set_column(29, 32, 20)
            cases_sheet.write_string(0, 0, "Cow-by-cow study parameters", title)
            cases_sheet.write_string(
                1,
                0,
                "One row per cow/case. T6 means exactly six elapsed hours. See Definitions and QC.",
                muted,
            )
        extra_headers = (
            "Farm-local time zero",
            "Farm",
            "Requested From",
            "Requested To",
            "Source case status",
        )
        if not settings.automatic:
            for column, name in enumerate(CORE_HEADERS + extra_headers):
                cases_sheet.write_string(2, column, name, header)
            cases_sheet.set_row(2, 34)
            cases_sheet.autofilter(2, 0, 2 + len(source.cases), 32)
        events = dict(settings.events)
        case_baselines: dict[tuple, dict[str, float | None]] = {}
        missing: Counter[str] = Counter()
        first_data_row = 2 if settings.automatic else 3
        for row, case in enumerate(source.cases, first_data_row):
            if stop.is_set():
                raise ApiCancelled
            event = events[case.key]
            anchored = case.key not in settings.unanchored_cases
            day = timedelta(days=1)
            hour = timedelta(hours=1)
            tn = (
                self._values(series, case, settings.normal_temp, event - 7 * day, event)
                if anchored
                else []
            )
            an = (
                self._values(series, case, settings.activity, event - 14 * day, event)
                if anchored
                else []
            )
            rn = (
                self._values(series, case, settings.rumination, event - 7 * day, event)
                if anchored
                else []
            )
            tn_value, an_value, rn_value = (
                mean(values) if values else None for values in (tn, an, rn)
            )
            case_baselines[case.key] = {
                "temperature": tn_value,
                "activity": an_value,
                "rumination": rn_value,
            }
            temps_pre = self._values(series, case, settings.temperature, event - 5 * day, event)
            temps_post = self._values(
                series, case, settings.temperature, event, event + settings.followup_days * day
            )
            rum_post = self._values(series, case, settings.rumination, event, event + 5 * day)
            low = min(rum_post) if rum_post else None
            r20 = (
                sum(value > tn_value + settings.threshold_c for value in temps_post)
                if tn_value is not None
                else None
            )
            drop = 1 - low / rn_value if low is not None and rn_value and rn_value > 0 else None
            lactation = self._lactation_at(case, event)
            dim = (
                event.astimezone(ZoneInfo(case.timezone)).date()
                - lactation.calving_utc.astimezone(ZoneInfo(case.timezone)).date()
                if lactation is not None
                else None
            )
            rback, rdown = self._rumination_timing_days(
                series,
                case,
                settings.rumination,
                event,
                event + 5 * day,
                self._collection_end(case),
                rn_value,
            )
            temps = [
                self._exact(series, case, settings.temperature, event + n * hour)
                for n in (0, 6, 12, 18, 24)
            ]
            activities = [
                mean(values) if values else None
                for values in (
                    self._values(series, case, settings.activity, event - 6 * hour, event),
                    *(
                        self._values(
                            series,
                            case,
                            settings.activity,
                            event + (n - 6) * hour,
                            event + n * hour,
                        )
                        for n in (6, 12, 18, 24)
                    ),
                )
            ]
            rumination = [
                self._exact(series, case, settings.rumination, event + n * hour)
                for n in (0, 24, 48, 72, 96, 120)
            ]
            rumination_daily_averages = []
            for day_number in range(1, 6):
                daily_values = self._values(
                    series,
                    case,
                    settings.rumination,
                    event + (day_number - 1) * day,
                    event + day_number * day,
                )
                rumination_daily_averages.append(mean(daily_values) if daily_values else None)
            values: tuple[Any, ...] = (
                row - first_data_row + 1,
                case.cow,
                lactation.number if lactation is not None else None,
                dim.days if dim is not None else None,
                tn_value,
                max(temps_pre) if temps_pre else None,
                *temps,
                r20,
                an_value,
                *activities,
                rn_value,
                low,
                drop,
                rback,
                *rumination,
                (
                    event.astimezone(ZoneInfo(case.timezone)).strftime("%d/%m/%Y %H:%M %Z")
                    + (" · period anchor" if case.key in settings.provisional_cases else "")
                    if anchored
                    else "T0 not supplied"
                ),
                case.farm,
                case.from_date,
                case.to_date,
                case.status,
            )
            assert len(values) == 33
            if not anchored:
                values = values[:2] + (None,) * 26 + values[28:]
            if settings.automatic:
                values = values[:22] + (rdown,) + values[22:28] + tuple(rumination_daily_averages)
            for column, value in enumerate(values):
                if value is None:
                    ignored_missing = (2, 3, 21, 22) if settings.automatic else (2, 3, 21)
                    if column not in ignored_missing:
                        visible_headers = (
                            AUTOMATIC_HEADERS
                            if settings.automatic
                            else CORE_HEADERS + extra_headers
                        )
                        missing[visible_headers[column]] += 1
                    continue
                if isinstance(value, int | float):
                    if settings.automatic:
                        integer_columns = (0, 2, 3, 11, 18, 19, 23, 24, 25, 26, 27, 28)
                        fmt = integer if column in integer_columns else number
                    else:
                        fmt = percent if column == 20 else integer if column in (0, 11) else number
                    cases_sheet.write_number(row, column, value, fmt)
                else:
                    cases_sheet.write_string(row, column, str(value))
        if settings.automatic:
            self._automatic_aligned_sheet(
                workbook,
                source,
                settings,
                series,
                events,
                title,
                header,
                number,
                integer,
                muted,
                stop,
            )
            workbook.close()
            return
        normal_sheet = workbook.add_worksheet("Normal values")
        normal_sheet.hide_gridlines(2)
        normal_sheet.freeze_panes(2, 2)
        normal_sheet.set_column(0, 0, 15)
        normal_sheet.set_column(1, 1, 16)
        normal_sheet.set_column(2, 4, 15)
        normal_sheet.write_string(0, 0, "Baseline normal values", title)
        for column, name in enumerate(("Cow", "Time zero", "Tn", "AN", "Rn")):
            normal_sheet.write_string(1, column, name, header)
        for row, case in enumerate(source.cases, 2):
            base = case_baselines[case.key]
            normal_sheet.write_string(row, 0, case.cow)
            normal_sheet.write_string(
                row,
                1,
                (
                    events[case.key].astimezone(ZoneInfo(case.timezone)).strftime("%d/%m/%Y %H:%M")
                    + (" · period anchor" if case.key in settings.provisional_cases else "")
                    if case.key not in settings.unanchored_cases
                    else "T0 not supplied"
                ),
            )
            for column, role in enumerate(("temperature", "activity", "rumination"), 2):
                if base[role] is not None:
                    normal_sheet.write_number(row, column, base[role], number)
        self._timepoint_sheet(
            workbook,
            "Temperature timepoints",
            source.cases,
            events,
            settings.temperature,
            settings.temp_step_hours,
            settings.temp_horizon_hours,
            "T",
            series,
            title,
            header,
            number,
            muted,
            stop,
            settings.unanchored_cases,
            False,
            settings.provisional_cases,
        )
        self._timepoint_sheet(
            workbook,
            "Rumination timepoints",
            source.cases,
            events,
            settings.rumination,
            settings.rum_step_hours,
            settings.rum_horizon_hours,
            "RT",
            series,
            title,
            header,
            number,
            muted,
            stop,
            settings.unanchored_cases,
            settings.rumination_minutes,
            settings.provisional_cases,
        )
        for title_text, pair, role in (
            ("Temperature aligned", settings.temperature, "temperature"),
            ("Activity aligned", settings.activity, "activity"),
            ("Rumination aligned", settings.rumination, "rumination"),
        ):
            self._aligned(
                workbook,
                title_text,
                source.cases,
                events,
                pair,
                role,
                series,
                case_baselines,
                settings,
                title,
                header,
                number,
                muted,
                stop,
            )
        self._analysis_summary(
            workbook,
            source.cases,
            events,
            settings,
            series,
            case_baselines,
            title,
            header,
            number,
            muted,
            stop,
        )
        self._graphs(workbook, source.cases, settings, title, muted)
        definitions = workbook.add_worksheet("Definitions")
        definitions.hide_gridlines(2)
        definitions.set_column(0, 0, 27)
        definitions.set_column(1, 1, 90)
        definitions.write_string(0, 0, "What each column means", title)
        notes = (
            ("Source", "Original analysis_ready.csv SHA-256: " + source.csv_sha256),
            (
                "Resolution",
                source.resolution
                + "; exact elapsed hours are never renamed as download intervals.",
            ),
            (
                "Time zero",
                (
                    "Each cow's optional queue T0 is the treatment/key-event time. "
                    "Without it, From 00:00 is used as a labelled period anchor only; "
                    "the resulting offsets are not treatment-relative. Elapsed offsets use UTC."
                    if settings.automatic
                    else (
                        "Explicit farm-local treatment/key-event time per cow; "
                        "elapsed offsets use UTC."
                    )
                ),
            ),
            (
                "Normal temperature",
                (
                    f"{settings.normal_temp[0]} [{settings.normal_temp[1]}], previous 7 days."
                    if settings.normal_temp
                    else "Not mapped; Tn and R20 proxy remain blank."
                ),
            ),
            (
                "Temperature",
                (
                    f"{settings.temperature[0]} [{settings.temperature[1]}], "
                    "without drinking cycles; exact T points."
                    if settings.temperature
                    else "Not mapped; T points and Talert proxy blank."
                ),
            ),
            (
                "Activity",
                (
                    f"{settings.activity[0]} [{settings.activity[1]}], "
                    "previous 14 days baseline; AT in 6-hour windows."
                    if settings.activity
                    else "Not mapped; AN and AT points remain blank."
                ),
            ),
            (
                "Rumination",
                (
                    f"{settings.rumination[0]} [{settings.rumination[1]}], "
                    + (
                        "divided by 60 into minutes in this derived workbook; "
                        if settings.rumination_minutes
                        else ""
                    )
                    + "previous 7 days baseline; Rl next 5 days."
                    if settings.rumination
                    else "Not mapped; R and RT points remain blank."
                ),
            ),
            (
                "Talert proxy",
                "Maximum temperature without drinking cycles in the 5 days "
                "before time zero; not an alert flag.",
            ),
            (
                "R20 proxy",
                f"Count of distinct measurements > Tn + {settings.threshold_c:g} °C "
                f"in first {settings.followup_days} days; not alert events.",
            ),
            (
                "%drop",
                "Stored as 1 - Rl/Rn and formatted as a percentage, like the client's "
                "Excel example; blank when Rn is zero or unavailable.",
            ),
            (
                "Rback",
                "Elapsed days from the first Rl minimum in the five days after time "
                "zero until the first later observed rumination reading at or above "
                "the pre-event Rn baseline. The automatic workbook searches through "
                "the available requested period.",
            ),
            (
                "Lact / DIM",
                "Lact is the documented smaXtec lifecycle cycle containing time zero. "
                "DIM is the farm-local calendar-day difference between time zero and "
                "that cycle's calving date. Blank when lifecycle data is unavailable "
                "or time zero falls outside a lactating cycle.",
            ),
            (
                "Aligned activity",
                "At each labelled offset, mean of the preceding 6-hour "
                "window; point metrics are exact.",
            ),
            ("95% limits", "Mean ± 1.96 × sample SD / sqrt(actual n); n<2 leaves limits blank."),
            (
                "Duplicate policy",
                "Identical same-timestamp values collapse only here; conflicting "
                "values are excluded and flagged. Source unchanged.",
            ),
        )
        for row, (name, text) in enumerate(notes, 2):
            definitions.write_string(row, 0, name, header)
            definitions.write_string(row, 1, text, muted)
        qc = workbook.add_worksheet("QC and missing data")
        qc.hide_gridlines(2)
        qc.set_column(0, 0, 36)
        qc.set_column(1, 1, 20)
        qc.set_column(2, 7, 17)
        qc.write_string(0, 0, "Quality and availability", title)
        qc.write_string(
            1,
            0,
            "All counts describe this derived view; original source files are unchanged.",
            muted,
        )
        qc.write_string(2, 0, "Item", header)
        qc.write_string(2, 1, "Count", header)
        all_quality = quality + Counter(
            {"missing_" + name: count for name, count in missing.items()}
        )
        all_quality["cow_cases"] = len(source.cases)
        all_quality["cow_cases_without_T0"] = len(settings.unanchored_cases)
        all_quality["cow_cases_using_period_anchor"] = len(settings.provisional_cases)
        all_quality["non_saved_cow_cases"] = sum(case.status != "saved" for case in source.cases)
        required_windows = (
            ("short_14d_activity_baseline", timedelta(days=14), timedelta()),
            ("short_7d_normal_baseline", timedelta(days=7), timedelta()),
            ("short_5d_temperature_proxy", timedelta(days=5), timedelta()),
            ("short_5d_rumination_low", timedelta(), timedelta(days=5)),
            (
                "short_R20_followup",
                timedelta(),
                timedelta(days=settings.followup_days),
            ),
            (
                "short_aligned_window",
                timedelta(hours=settings.aligned_before_hours),
                timedelta(hours=settings.aligned_after_hours),
            ),
        )
        for name, before, after in required_windows:
            all_quality[name] = sum(
                case.key not in settings.unanchored_cases
                and (
                    events[case.key] - before < self._collection_start(case)
                    or events[case.key] + after > self._collection_end(case)
                )
                for case in source.cases
            )
        for row, (name, count) in enumerate(sorted(all_quality.items()), 3):
            qc.write_string(row, 0, name)
            qc.write_number(row, 1, count, integer)
        case_row = len(all_quality) + 6
        qc.write_string(case_row, 0, "Availability by cow/case", title)
        qc.write_string(
            case_row + 1,
            0,
            "Baseline sample counts are not adequacy guarantees; inspect dates and resolution.",
            muted,
        )
        for column, label in enumerate(
            (
                "Farm",
                "Cow",
                "API status",
                "Normal temp 7d n",
                "Activity 14d n",
                "Rumination 7d n",
                "T0 exact?",
                "Conflicting points",
            )
        ):
            qc.write_string(case_row + 2, column, label, header)
        for row, case in enumerate(source.cases, case_row + 3):
            event = events[case.key]
            qc.write_string(row, 0, case.farm)
            qc.write_string(row, 1, case.cow)
            qc.write_string(row, 2, case.status)
            for column, pair, days in (
                (3, settings.normal_temp, 7),
                (4, settings.activity, 14),
                (5, settings.rumination, 7),
            ):
                qc.write_number(
                    row,
                    column,
                    len(self._values(series, case, pair, event - timedelta(days=days), event)),
                    integer,
                )
            qc.write_string(
                row,
                6,
                "Yes"
                if case.key not in settings.unanchored_cases
                and self._exact(series, case, settings.temperature, event) is not None
                else "No",
            )
            qc.write_number(
                row,
                7,
                sum(
                    len(conflicts.get((case.key, pair), ()))
                    for pair in (
                        settings.normal_temp,
                        settings.temperature,
                        settings.activity,
                        settings.rumination,
                    )
                ),
                integer,
            )
        workbook.close()

    @staticmethod
    def _collection_start(case: StudyCase) -> datetime:
        local = datetime.fromisoformat(case.from_date).replace(tzinfo=ZoneInfo(case.timezone))
        return local.astimezone(UTC)

    @staticmethod
    def _collection_end(case: StudyCase) -> datetime:
        local = (datetime.fromisoformat(case.to_date) + timedelta(days=1)).replace(
            tzinfo=ZoneInfo(case.timezone)
        )
        return local.astimezone(UTC)

    def _aligned(
        self,
        workbook,
        name,
        cases,
        events,
        pair,
        role,
        series,
        baselines,
        settings,
        title,
        header,
        number,
        muted,
        stop,
    ) -> None:
        sheet = workbook.add_worksheet(name)
        sheet.hide_gridlines(2)
        sheet.freeze_panes(3, 1)
        sheet.set_column(0, 0, 16)
        sheet.set_column(1, len(cases), 15)
        stats_start = len(cases) + 1
        sheet.set_column(stats_start, stats_start + 9, 16)
        sheet.write_string(0, 0, name, title)
        sheet.write_string(
            1,
            0,
            "Cow values are aligned by elapsed hours from each cow's own time zero. "
            "Mean and 95% limits use available cows at each offset.",
            muted,
        )
        headings = ("Hours from T0",) + tuple(
            f"{case.farm} · cow {case.cow} · case {case.index}" for case in cases
        )
        headings += (
            "n",
            "Mean",
            "Sample SD",
            "Lower 95%",
            "Upper 95%",
            "Relative n",
            "Mean vs normal",
            "Relative sample SD",
            "Relative lower 95%",
            "Relative upper 95%",
        )
        for column, text in enumerate(headings):
            sheet.write_string(2, column, text, header)
        sheet.set_row(2, 44)
        start = -settings.aligned_before_hours
        end = settings.aligned_after_hours
        offsets = list(range(start, end + 1, settings.aligned_step_hours))
        if 0 not in offsets:
            offsets.append(0)
            offsets.sort()
        if len(offsets) > MAX_OFFSETS:
            raise ApiError("study_size", "Reduce the aligned time range or increase its step.")
        for row, offset in enumerate(offsets, 3):
            if stop.is_set():
                raise ApiCancelled
            sheet.write_number(row, 0, offset)
            absolute = []
            relative = []
            for column, case in enumerate(cases, 1):
                if case.key in settings.unanchored_cases:
                    continue
                stamp = events[case.key] + timedelta(hours=offset)
                if role == "activity":
                    values = self._values(series, case, pair, stamp - timedelta(hours=6), stamp)
                    value = mean(values) if values else None
                else:
                    value = self._exact(series, case, pair, stamp)
                if value is not None:
                    sheet.write_number(row, column, value, number)
                    absolute.append(value)
                    baseline = baselines[case.key][role]
                    if baseline is not None:
                        relative.append(value - baseline)
            n, avg, sd, low, high = _sample_stats(absolute)
            sheet.write_number(row, stats_start, n)
            for column, value in enumerate((avg, sd, low, high), stats_start + 1):
                if value is not None:
                    sheet.write_number(row, column, value, number)
            rel_n, rel_avg, rel_sd, rel_low, rel_high = _sample_stats(relative)
            sheet.write_number(row, stats_start + 5, rel_n)
            for column, value in enumerate((rel_avg, rel_sd, rel_low, rel_high), stats_start + 6):
                if value is not None:
                    sheet.write_number(row, column, value, number)
        if (
            offsets
            and pair is not None
            and any(case.key not in settings.unanchored_cases for case in cases)
        ):
            chart = workbook.add_chart({"type": "line"})
            for col, label, color in (
                (stats_start + 1, "Mean", "#245D43"),
                (stats_start + 3, "Lower 95%", "#80B25E"),
                (stats_start + 4, "Upper 95%", "#80B25E"),
            ):
                chart.add_series(
                    {
                        "name": label,
                        "categories": [name, 3, 0, 2 + len(offsets), 0],
                        "values": [name, 3, col, 2 + len(offsets), col],
                        "line": {"color": color, "width": 2 if label == "Mean" else 1},
                    }
                )
            chart.set_title({"name": f"{role.capitalize()} · mean and 95% limits"})
            chart.set_x_axis({"name": "Elapsed hours from time zero"})
            chart.set_y_axis(
                {
                    "name": "Study units: minutes"
                    if role == "rumination" and settings.rumination_minutes
                    else f"Source units: {pair[1] if pair else 'unmapped'}"
                }
            )
            chart.set_legend({"position": "bottom"})
            sheet.insert_chart(2, stats_start + 11, chart, {"x_scale": 1.35, "y_scale": 1.25})

    def _timepoint_sheet(
        self,
        workbook,
        name,
        cases,
        events,
        pair,
        step,
        horizon,
        prefix,
        series,
        title,
        header,
        number,
        muted,
        stop,
        unanchored_cases=(),
        settings_rumination_minutes=False,
        provisional_cases=(),
    ) -> None:
        sheet = workbook.add_worksheet(name)
        sheet.hide_gridlines(2)
        sheet.freeze_panes(3, 2)
        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 1, 23)
        sheet.set_column(2, 2 + horizon // step, 15)
        sheet.write_string(0, 0, name, title)
        unit_label = pair[1] if pair else "unmapped"
        if prefix == "RT" and pair == ("rum_index", "seconds") and settings_rumination_minutes:
            unit_label = "minutes derived from seconds"
        sheet.write_string(
            1,
            0,
            f"Exact source {pair[0] if pair else 'unmapped'} "
            f"[{unit_label}] points at the configured elapsed-hour "
            "steps; missing points remain blank.",
            muted,
        )
        offsets = list(range(0, horizon + 1, step))
        for column, heading in enumerate(
            ("Cow", "Farm-local time zero") + tuple(f"{prefix}{offset}" for offset in offsets)
        ):
            sheet.write_string(2, column, heading, header)
        for row, case in enumerate(cases, 3):
            if stop.is_set():
                raise ApiCancelled
            event = events[case.key]
            sheet.write_string(row, 0, case.cow)
            sheet.write_string(
                row,
                1,
                (
                    event.astimezone(ZoneInfo(case.timezone)).strftime("%d/%m/%Y %H:%M")
                    + (" · period anchor" if case.key in provisional_cases else "")
                    if case.key not in unanchored_cases
                    else "T0 not supplied"
                ),
            )
            if case.key in unanchored_cases:
                continue
            for column, offset in enumerate(offsets, 2):
                value = self._exact(series, case, pair, event + timedelta(hours=offset))
                if value is not None:
                    sheet.write_number(row, column, value, number)


class AutomaticStudyWorkbookService:
    """Add the client's cow-by-cow layout from observed metric pairs.

    A missing treatment T0 uses From 00:00 solely as a labelled period anchor.
    The collection's raw/tidy measurements remain unchanged.
    """

    SOURCE_PAIRS = {
        "normal_temp": ("temp_normal_index", "degree_celsius"),
        "normal_temp_fallback": ("temp", "degree_celsius"),
        "temperature": ("temp_without_drink_cycles", "degree_celsius"),
        "activity": ("act", "act"),
        "rumination": ("rum_index", "seconds"),
    }

    def create(
        self,
        folder: Path,
        stop: Event,
        progress: Callable[[ApiProgress], None],
    ) -> Path:
        source = StudySource.load(folder, stop)
        present = set(source.pairs)
        events = []
        provisional = []
        for case in source.cases:
            if case.event_utc is None:
                provisional.append(case.key)
                events.append((case.key, StudyWorkbookService._collection_start(case)))
            else:
                events.append((case.key, case.event_utc))
        normal_pair = self.SOURCE_PAIRS["normal_temp"]
        if normal_pair not in present:
            normal_pair = self.SOURCE_PAIRS["normal_temp_fallback"]
        settings = StudySettings(
            events=tuple(events),
            normal_temp=normal_pair if normal_pair in present else None,
            temperature=(
                self.SOURCE_PAIRS["temperature"]
                if self.SOURCE_PAIRS["temperature"] in present
                else None
            ),
            activity=self.SOURCE_PAIRS["activity"]
            if self.SOURCE_PAIRS["activity"] in present
            else None,
            rumination=self.SOURCE_PAIRS["rumination"]
            if self.SOURCE_PAIRS["rumination"] in present
            else None,
            provisional_cases=tuple(provisional),
            rumination_minutes=self.SOURCE_PAIRS["rumination"] in present,
            automatic=True,
        )
        return StudyWorkbookService().create(
            source, settings, stop, progress, file_stem="client-analysis"
        )
