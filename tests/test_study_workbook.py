"""Synthetic client-study regressions; no live data, credentials or sample workbook."""

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from threading import Event
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from xlsxwriter.utility import xl_col_to_name

from smaxtec.application.api_data import ApiError
from smaxtec.application.api_downloads import ANALYSIS_HEADERS
from smaxtec.application.study_workbook import (
    AutomaticStudyWorkbookService,
    StudySettings,
    StudySource,
    StudyWorkbookService,
    parse_event_time,
)


def _collection(
    tmp_path,
    *,
    two_cows=True,
    second_without_normal=False,
    cow_count=None,
    auto_pairs=False,
    auto_event=False,
):
    event = datetime(2026, 9, 15, 8, 10, tzinfo=UTC)
    cows = (
        tuple(f"{index:03d}" for index in range(1, cow_count + 1))
        if cow_count is not None
        else ("57", "657")
        if two_cows
        else ("57",)
    )
    targets = []
    rows = []
    for cow in cows:
        target_id = "synthetic-" + cow
        targets.append(
            {
                "farm": "Synthetic Farm",
                "farm_id": "synthetic-farm",
                "target_type": "animals",
                "target_id": target_id,
                "animal_number": cow,
                "from": "2026-09-01",
                "to": "2026-10-05",
                "farm_timezone": "Europe/London",
                "status": "saved",
                "study_event_utc": event.isoformat() if auto_event else None,
            }
        )

        def add(
            metric,
            unit,
            offset_hours,
            value,
            *,
            target_id=target_id,
            cow=cow,
            timestamp=None,
        ):
            if auto_pairs:
                metric, unit = {
                    "normal_temp": ("temp_normal_index", "degree_celsius"),
                    "temp_no_drink": ("temp_without_drink_cycles", "degree_celsius"),
                    "activity": ("act", "act"),
                    "rumination": ("rum_index", "seconds"),
                }.get(metric, (metric, unit))
                if metric == "rum_index":
                    value *= 60
            stamp = (
                (timestamp or event + timedelta(hours=offset_hours))
                .isoformat()
                .replace("+00:00", "Z")
            )
            row = dict.fromkeys(ANALYSIS_HEADERS, "")
            row.update(
                {
                    "target_type": "animals",
                    "target_id": target_id,
                    "target_number": cow,
                    "farm_id": "synthetic-farm",
                    "requested_from": "2026-09-01",
                    "requested_to": "2026-10-05",
                    "farm_timezone": "Europe/London",
                    "metric": metric,
                    "unit": unit,
                    "timestamp_utc": stamp,
                    "value": str(value),
                }
            )
            rows.append(row)

        for offset in (-14 * 24 + 1, -7 * 24 + 1, -5 * 24 + 1, -6, 0, 6, 24, 48, 72, 96, 120):
            add("temp_no_drink", "celsius", offset, 39 if offset < 0 else 40 + offset / 100)
            if not (second_without_normal and cow == "657"):
                add("normal_temp", "celsius", offset, 39.5)
            add("activity", "index", offset, 6 if offset < 0 else 8)
            add("rumination", "minutes", offset, 500 if offset < 0 else 400 + offset)
        add("activity", "index", 3, 10)
        add("rumination", "minutes", 12, 300)
        add("temp_no_drink", "celsius", 6, 40.06)  # identical boundary duplicate
        if auto_pairs:
            start = datetime(2026, 8, 31, 23, tzinfo=UTC)
            for offset, temperature, rumination in (
                (0, 40.0, 400),
                (6, 40.1, 420),
                (24, 40.2, 440),
            ):
                stamp = start + timedelta(hours=offset)
                add("temp_no_drink", "celsius", 0, temperature, timestamp=stamp)
                add("normal_temp", "celsius", 0, 39.5, timestamp=stamp)
                add("activity", "index", 0, 6, timestamp=stamp)
                add("rumination", "minutes", 0, rumination, timestamp=stamp)
    csv_path = tmp_path / "analysis_ready.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ANALYSIS_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "format_version": 2,
        "aggregation": "10minutes",
        "analysis_csv": csv_path.name,
        "analysis_csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "targets": targets,
    }
    (tmp_path / "collection.json").write_text(json.dumps(manifest), encoding="utf-8")
    return event


def _settings(source):
    events = tuple(
        (case.key, parse_event_time("15/09/2026 09:10", case.timezone)) for case in source.cases
    )
    return StudySettings(
        events,
        ("normal_temp", "celsius"),
        ("temp_no_drink", "celsius"),
        ("activity", "index"),
        ("rumination", "minutes"),
    )


def _numeric_cell(xml: bytes, address: str) -> float | None:
    root = ElementTree.fromstring(xml)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    node = root.find(f".//m:c[@r='{address}']/m:v", ns)
    return float(node.text) if node is not None else None


def test_client_workbook_has_one_case_row_exact_hours_aligned_cows_and_qc(tmp_path):
    _collection(tmp_path)
    source = StudySource.load(tmp_path)
    assert [case.cow for case in source.cases] == ["57", "657"]
    progress = []
    output = StudyWorkbookService().create(source, _settings(source), Event(), progress.append)
    assert output.name == "client-study.xlsx"
    assert progress[-1].message == "Client study workbook ready."
    with ZipFile(output) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        for name in (
            "Client parameters",
            "Normal values",
            "Temperature timepoints",
            "Rumination timepoints",
            "Temperature aligned",
            "Activity aligned",
            "Rumination aligned",
            "Analysis",
            "Study graphs",
            "Definitions",
            "QC and missing data",
        ):
            assert f'name="{name}"' in workbook_xml
        assert (
            len([name for name in archive.namelist() if name.startswith("xl/charts/chart")]) == 15
        )
        raw_sheet = archive.read("xl/worksheets/sheet1.xml")
        sheet = raw_sheet.decode("utf-8")
        assert '<c r="B4"' in sheet and '<c r="B5"' in sheet
        assert '<c r="H4"' in sheet  # T6 at exactly +6h
        assert '<c r="I4"' not in sheet  # T12 is missing, not nearest +24h
        assert '<c r="U4"' in sheet  # percentage drop
        assert _numeric_cell(raw_sheet, "E4") == pytest.approx(39.5)  # Tn
        assert _numeric_cell(raw_sheet, "H4") == pytest.approx(40.06)  # T6
        assert _numeric_cell(raw_sheet, "L4") == pytest.approx(4)  # R20 proxy
        assert _numeric_cell(raw_sheet, "N4") == pytest.approx(6)  # AT0 previous 6h
        assert _numeric_cell(raw_sheet, "O4") == pytest.approx(9)  # AT6 0..6h
        assert _numeric_cell(raw_sheet, "S4") == pytest.approx(500)  # Rn
        assert _numeric_cell(raw_sheet, "T4") == pytest.approx(300)  # Rl
        assert _numeric_cell(raw_sheet, "U4") == pytest.approx(0.4)  # 40% formatted
        assert b'formatCode="0.0%"' in archive.read("xl/styles.xml")
        aligned = archive.read("xl/worksheets/sheet5.xml")
        assert b"Sample SD" in aligned
        assert _numeric_cell(aligned, "D8") == pytest.approx(2)  # available cows at T0
        assert _numeric_cell(aligned, "E8") == pytest.approx(40)  # absolute mean
        assert _numeric_cell(aligned, "F8") == pytest.approx(0)  # sample SD
        assert _numeric_cell(aligned, "I8") == pytest.approx(2)  # relative available cows
        assert _numeric_cell(aligned, "J8") == pytest.approx(0.5)  # mean vs baseline
        summary = archive.read("xl/worksheets/sheet8.xml")
        assert _numeric_cell(summary, "F5") == pytest.approx(40)  # Cohort T0 mean.
        assert _numeric_cell(summary, "M5") == pytest.approx(6)  # Cohort AT0 mean.
        assert _numeric_cell(summary, "V5") == pytest.approx(400)  # Cohort RT0 mean.
        qc = archive.read("xl/worksheets/sheet11.xml").decode("utf-8")
        assert "identical_duplicate_collapsed" in qc
        assert "Availability by cow/case" in qc
        assert all(
            b"#REF!" not in archive.read(name)
            for name in archive.namelist()
            if name.startswith("xl/charts/chart")
        )
    assert (tmp_path / "analysis_ready.csv").is_file()
    another = StudyWorkbookService().create(source, _settings(source), Event(), lambda _: None)
    assert another.name == ("client-study-1.xlsx")


def test_automatic_companion_defaults_to_labelled_From_anchor_and_pivots_exact_points(tmp_path):
    _collection(tmp_path, two_cows=False, auto_pairs=True)
    source_hash = hashlib.sha256((tmp_path / "analysis_ready.csv").read_bytes()).hexdigest()
    output = AutomaticStudyWorkbookService().create(tmp_path, Event(), lambda _: None)
    assert output.name == "client-analysis.xlsx"
    with ZipFile(output) as archive:
        parameters = archive.read("xl/worksheets/sheet1.xml")
        assert b"57" in parameters
        assert _numeric_cell(parameters, "E4") is None  # No prior-week coverage.
        assert _numeric_cell(parameters, "N4") is None  # No preceding 6h coverage.
        assert _numeric_cell(parameters, "G4") == pytest.approx(40.0)
        assert _numeric_cell(parameters, "H4") == pytest.approx(40.1)
        assert _numeric_cell(parameters, "K4") == pytest.approx(40.2)
        assert _numeric_cell(parameters, "O4") == pytest.approx(6)
        assert _numeric_cell(parameters, "W4") == pytest.approx(400)  # Seconds -> minutes.
        assert _numeric_cell(parameters, "X4") == pytest.approx(440)
        assert b"period anchor" in parameters
        definitions = archive.read("xl/worksheets/sheet10.xml")
        assert b"temp_normal_index [degree_celsius]" in definitions
        assert b"temp_without_drink_cycles [degree_celsius]" in definitions
        assert b"act [act]" in definitions
        assert b"rum_index [seconds]" in definitions
        assert b"divided by 60 into minutes" in definitions
    assert hashlib.sha256((tmp_path / "analysis_ready.csv").read_bytes()).hexdigest() == source_hash


def test_automatic_companion_fills_supported_fields_when_T0_is_supplied(tmp_path):
    _collection(tmp_path, two_cows=False, auto_pairs=True, auto_event=True)
    output = AutomaticStudyWorkbookService().create(tmp_path, Event(), lambda _: None)
    assert output.name == "client-analysis.xlsx"
    with ZipFile(output) as archive:
        parameters = archive.read("xl/worksheets/sheet1.xml")
        assert _numeric_cell(parameters, "E4") == pytest.approx(39.5)
        assert _numeric_cell(parameters, "N4") == pytest.approx(6)
        assert _numeric_cell(parameters, "O4") == pytest.approx(9)
        assert _numeric_cell(parameters, "S4") == pytest.approx(500)
        assert _numeric_cell(parameters, "T4") == pytest.approx(300)
        assert _numeric_cell(parameters, "U4") == pytest.approx(0.4)
        assert _numeric_cell(parameters, "W4") == pytest.approx(400)
        assert _numeric_cell(parameters, "G4") == pytest.approx(40)
        assert _numeric_cell(parameters, "H4") == pytest.approx(40.06)


def test_source_hash_role_and_daylight_saving_guardrails(tmp_path):
    _collection(tmp_path, two_cows=False)
    source = StudySource.load(tmp_path)
    with pytest.raises(ValueError, match="differ"):
        settings = _settings(source)
        StudySettings(
            settings.events,
            settings.temperature,
            settings.temperature,
            settings.activity,
            settings.rumination,
        ).validate(source)
    with pytest.raises(ValueError, match="daylight-saving"):
        parse_event_time("25/10/2026 01:30", "Europe/London")
    with pytest.raises(ValueError, match="daylight-saving"):
        parse_event_time("29/03/2026 01:30", "Europe/London")
    with (tmp_path / "analysis_ready.csv").open("a", encoding="utf-8") as handle:
        handle.write("changed")
    with pytest.raises(ApiError, match="changed since it was loaded"):
        StudyWorkbookService().create(source, _settings(source), Event(), lambda _: None)
    with pytest.raises(ApiError, match="incomplete, changed"):
        StudySource.load(tmp_path)


def test_unavailable_metric_roles_remain_blank_without_guessing(tmp_path):
    _collection(tmp_path, two_cows=False)
    source = StudySource.load(tmp_path)
    full = _settings(source)
    partial = StudySettings(
        full.events,
        None,
        full.temperature,
        None,
        None,
    )
    output = StudyWorkbookService().create(source, partial, Event(), lambda _: None)
    with ZipFile(output) as archive:
        main = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert '<c r="E4"' not in main  # No guessed normal temperature.
        assert '<c r="L4"' not in main  # R20 needs Tn.
        assert '<c r="H4"' in main  # Available exact temperature still works.
        definitions = archive.read("xl/worksheets/sheet10.xml").decode("utf-8")
        assert "Not mapped" in definitions


def test_relative_confidence_uses_its_own_available_cow_count(tmp_path):
    _collection(tmp_path, second_without_normal=True)
    source = StudySource.load(tmp_path)
    output = StudyWorkbookService().create(source, _settings(source), Event(), lambda _: None)
    with ZipFile(output) as archive:
        main = archive.read("xl/worksheets/sheet1.xml")
        assert _numeric_cell(main, "E5") is None  # Cow 657 has no normal baseline.
        assert _numeric_cell(main, "L5") is None  # No invented R20 without Tn.
        aligned = archive.read("xl/worksheets/sheet5.xml")
        assert _numeric_cell(aligned, "D8") == 2  # Both cows have T0.
        assert _numeric_cell(aligned, "I8") == 1  # Only one baseline-adjusted cow.
        assert _numeric_cell(aligned, "J8") == pytest.approx(0.5)
        assert _numeric_cell(aligned, "L8") is None  # n<2 has no confidence limits.


def test_three_hundred_cow_study_keeps_every_row_and_cohort_count(tmp_path):
    _collection(tmp_path, cow_count=300)
    source = StudySource.load(tmp_path)
    assert len(source.cases) == 300
    output = StudyWorkbookService().create(source, _settings(source), Event(), lambda _: None)
    with ZipFile(output) as archive:
        main = archive.read("xl/worksheets/sheet1.xml")
        assert b'<c r="B303"' in main  # Row 303 is the 300th cow.
        aligned = archive.read("xl/worksheets/sheet5.xml")
        n_col = xl_col_to_name(len(source.cases) + 1)
        assert _numeric_cell(aligned, f"{n_col}8") == 300


def test_unexpected_study_write_error_cleans_partial_without_touching_source(tmp_path, monkeypatch):
    _collection(tmp_path, two_cows=False)
    source = StudySource.load(tmp_path)
    service = StudyWorkbookService()

    def fails_after_partial(path, *_args):
        path.write_bytes(b"synthetic partial")
        raise RuntimeError("synthetic internal failure")

    monkeypatch.setattr(service, "_write", fails_after_partial)
    with pytest.raises(ApiError, match="Original source files are unchanged"):
        service.create(source, _settings(source), Event(), lambda _: None)
    assert not list(tmp_path.glob(".client-study-*.partial.xlsx"))
    assert not list(tmp_path.glob("client-study*.xlsx"))
    assert StudySource.load(tmp_path).csv_sha256 == source.csv_sha256
