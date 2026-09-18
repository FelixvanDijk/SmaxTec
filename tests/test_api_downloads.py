"""Offline direct-data collection tests; no credentials or live API calls."""

import csv
import json
from datetime import UTC, date, datetime
from threading import Event
from zipfile import ZipFile

import pytest

from smaxtec.application import api_downloads
from smaxtec.application.api_data import (
    ApiDownloadRequest,
    ApiEntity,
    ApiError,
    ApiFarm,
    ApiLactation,
    ApiMetric,
    ApiTarget,
)
from smaxtec.application.api_downloads import ApiDownloadService


class FakeClient:
    def __init__(self):
        self.data_calls = []

    def metrics(self, entity, stop):
        return (ApiMetric("temp", ("celsius",)), ApiMetric("act", ("index",)))

    def data(self, entity, metrics, start, end, aggregation, stop):
        self.data_calls.append((entity.number, metrics, start, end, aggregation))
        return [
            {
                "_id": entity.id,
                "metric": "temp",
                "unit": "celsius",
                "data": [
                    [start.isoformat(), 38.4],
                    {"timestamp": end.isoformat(), "value": 38.6, "quality": "synthetic"},
                ],
            }
        ]

    def health_index(self, farm, start, end, stop):
        return [{"selector": farm.id, "data": [[start.isoformat(), 71, 60, 80]]}]


def target(
    number="57",
    *,
    start=date(2026, 9, 1),
    end=date(2026, 9, 2),
    metrics=(),
    lactations=(),
):
    farm = ApiFarm("farm-synthetic-001", "Synthetic Farm", "Europe/London")
    entity = ApiEntity(
        "animal-synthetic-" + number,
        "animals",
        farm,
        number,
        number,
        "UK000000000" + number,
        lactations=lactations,
    )
    return ApiTarget(entity, start, end, metrics)


def test_collection_preserves_raw_chunks_and_builds_csv_excel_and_hashed_manifest(tmp_path):
    client = FakeClient()
    request = ApiDownloadRequest(
        (
            target(
                "57",
                lactations=(ApiLactation(3, datetime(2026, 8, 31, 23, tzinfo=UTC)),),
            ),
            target("657", metrics=("temp",)),
        ),
        tmp_path,
        "September herd data",
        aggregation="hourly",
        excel=True,
        include_health_index=True,
    )
    progress = []
    result = ApiDownloadService(client).download(request, Event(), progress.append)
    assert result.rows == 4
    assert [entry.status for entry in result.files] == ["saved", "saved"]
    assert result.folder.parent == tmp_path
    assert result.folder.name.startswith("September-herd-data-")
    assert result.client_workbook is not None
    assert result.client_workbook.is_file()

    manifest = json.loads((result.folder / "collection.json").read_text("utf-8"))
    assert manifest["format_version"] == 2
    assert manifest["total_measurement_rows"] == 4
    assert manifest["cancelled"] is False
    assert manifest["client_analysis"] == {
        "aligned_before_hours": 24,
        "aligned_after_hours": 120,
    }
    assert len(manifest["targets"]) == 2
    assert manifest["targets"][0]["lactations"] == [
        {
            "number": 3,
            "calving_utc": "2026-08-31T23:00:00+00:00",
            "dry_off_utc": None,
        }
    ]
    for entry in manifest["targets"]:
        assert entry["status"] == "saved"
        assert entry["raw_files"]
        for raw in entry["raw_files"]:
            assert (result.folder / raw["file"]).is_file()
            assert len(raw["sha256"]) == 64
    assert manifest["extras"]["farm-synthetic-001"]["health_index"]["records"] == 1
    assert manifest["analysis_csv"] == "analysis_ready.csv"
    assert len(manifest["analysis_csv_sha256"]) == 64
    assert manifest["client_workbook"] == result.client_workbook.name
    assert len(manifest["client_workbook_sha256"]) == 64

    with (result.folder / "measurements.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == [
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
    ]
    assert [row["animal_number"] for row in rows] == ["57", "57", "657", "657"]
    assert json.loads(rows[1]["raw_point"])["quality"] == "synthetic"
    assert rows[0]["requested_from"] == "2026-09-01"
    assert rows[0]["farm_timezone"] == "Europe/London"

    with (result.folder / "analysis_ready.csv").open(encoding="utf-8-sig", newline="") as handle:
        analysis_reader = csv.DictReader(handle)
        analysis_rows = list(analysis_reader)
    assert analysis_reader.fieldnames[:12] == [
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
    ]
    assert [row["target_number"] for row in analysis_rows] == ["57", "57", "657", "657"]
    assert analysis_rows[0]["metric"] == "temp"
    assert analysis_rows[0]["unit"] == "celsius"
    assert analysis_rows[0]["value"] == "38.4"
    assert analysis_rows[0]["resolution"] == "hourly"
    assert analysis_rows[0]["timestamp_utc"] == "2026-08-31T23:00:00Z"
    assert analysis_rows[0]["timestamp_local"] == "2026-09-01T00:00:00+01:00"
    assert analysis_rows[0]["local_date"] == "2026-09-01"
    assert analysis_rows[0]["local_time"] == "00:00:00"
    assert analysis_rows[0]["source_timestamp"] == "2026-08-31T23:00:00+00:00"
    assert analysis_rows[0]["farm_id"] == "farm-synthetic-001"
    assert analysis_rows[0]["series_index"] == "1"
    assert analysis_rows[0]["point_index"] == "1"

    workbook = result.folder / "September herd data.xlsx"
    with ZipFile(workbook) as archive:
        assert "xl/workbook.xml" in archive.namelist()
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        assert 'name="Collection summary"' in workbook_xml
        assert 'name="Measurements 001"' in workbook_xml
        assert 'name="Measurement index"' in workbook_xml
        assert 'name="Data guide"' in workbook_xml
        assert "xl/charts/chart1.xml" in archive.namelist()
        measurement_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        assert 'hidden="1"' in measurement_xml
    assert result.analysis_csv == result.folder / "analysis_ready.csv"
    assert result.workbook == workbook
    serialized = "\n".join(path.read_text("utf-8") for path in result.folder.rglob("*.json"))
    assert "password" not in serialized.casefold()
    assert "api-token" not in serialized.casefold()
    assert progress[-1].message == "Direct API collection ready."


def test_client_companion_failure_keeps_existing_collection_outputs(tmp_path, monkeypatch):
    def fail_client_workbook(_self, _folder, _stop, _progress):
        raise RuntimeError("synthetic companion failure")

    monkeypatch.setattr(
        "smaxtec.application.study_workbook.AutomaticStudyWorkbookService.create",
        fail_client_workbook,
    )
    request = ApiDownloadRequest((target("57"),), tmp_path, "Synthetic data")
    result = ApiDownloadService(FakeClient()).download(request, Event(), lambda _: None)
    assert result.client_workbook is None
    assert result.workbook.is_file()
    assert result.analysis_csv.is_file()
    assert (result.folder / "measurements.csv").is_file()
    assert (result.folder / "collection.json").is_file()
    assert "client analysis" in result.warnings[0].lower()
    manifest = json.loads((result.folder / "collection.json").read_text("utf-8"))
    assert manifest["client_workbook"] is None
    assert manifest["warnings"] == list(result.warnings)


def test_companion_manifest_refresh_failure_preserves_first_manifest(tmp_path, monkeypatch):
    original_write = api_downloads._write_json
    manifest_writes = 0

    def fail_second_manifest(path, value):
        nonlocal manifest_writes
        if path.name == "collection.json":
            manifest_writes += 1
            if manifest_writes == 2:
                raise OSError("synthetic manifest refresh failure")
        return original_write(path, value)

    monkeypatch.setattr(api_downloads, "_write_json", fail_second_manifest)
    result = ApiDownloadService(FakeClient()).download(
        ApiDownloadRequest((target("57"),), tmp_path, "Manifest fallback"),
        Event(),
        lambda _: None,
    )
    assert manifest_writes == 2
    assert result.client_workbook.is_file()
    assert result.analysis_csv.is_file()
    assert "companion metadata" in result.warnings[-1].lower()
    manifest = json.loads((result.folder / "collection.json").read_text("utf-8"))
    assert manifest["format_version"] == 2
    assert manifest["analysis_csv_sha256"]


def test_reviewed_study_T0_is_metadata_not_a_different_api_range(tmp_path):
    ordinary = target("57")
    event = datetime(2026, 9, 1, 8, 10, tzinfo=UTC)
    studied = ApiTarget(
        ordinary.entity,
        ordinary.start_date,
        ordinary.end_date,
        study_event_utc=event,
    )
    client = FakeClient()
    request = ApiDownloadRequest((studied,), tmp_path, "Study event test")
    result = ApiDownloadService(client).download(request, Event(), lambda _: None)
    manifest = json.loads((result.folder / "collection.json").read_text("utf-8"))
    assert manifest["targets"][0]["study_event_utc"] == event.isoformat()
    assert result.client_workbook.is_file()
    assert client.data_calls[0][2] == ordinary.utc_bounds()[0]
    assert client.data_calls[0][3] == ordinary.utc_bounds()[1]


def test_local_day_bounds_are_dst_safe_and_long_native_ranges_are_chunked(tmp_path):
    client = FakeClient()
    request = ApiDownloadRequest(
        (target(start=date(2026, 3, 1), end=date(2026, 4, 2), metrics=("temp",)),),
        tmp_path,
        "DST check",
        aggregation="native",
        excel=False,
    )
    result = ApiDownloadService(client).download(request, Event(), lambda _progress: None)
    assert len(client.data_calls) == 2
    assert client.data_calls[0][2].isoformat() == "2026-03-01T00:00:00+00:00"
    assert client.data_calls[-1][3].isoformat() == "2026-04-02T23:00:00+00:00"
    raw_parts = list((result.folder / "raw").glob("*-part-*.json"))
    assert len(raw_parts) == 2


def test_invalid_metric_is_a_per_target_failure_and_other_targets_continue(tmp_path):
    request = ApiDownloadRequest(
        (target("57", metrics=("unknown",)), target("657", metrics=("temp",))),
        tmp_path,
        "Partial result",
        excel=False,
    )
    result = ApiDownloadService(FakeClient()).download(request, Event(), lambda _progress: None)
    assert [entry.status for entry in result.files] == ["failed", "saved"]
    assert result.files[0].rows == 0
    assert result.files[1].rows == 2
    manifest = json.loads((result.folder / "collection.json").read_text("utf-8"))
    assert manifest["targets"][0]["requested_metrics"] == ["unknown"]


def test_analysis_view_preserves_duplicates_and_does_not_guess_ambiguous_times(tmp_path):
    class AmbiguousClient(FakeClient):
        def data(self, entity, metrics, start, end, aggregation, stop):
            return [
                {
                    "metric": "temp",
                    "unit": "celsius",
                    "data": [["1725148800", 38.4], ["1725148800", 38.4]],
                },
                {
                    "metric": "activity",
                    "unit": "index",
                    "data": [{"timestamp": "2026-09-01 12:00:00", "value": 9}],
                },
            ]

    request = ApiDownloadRequest(
        (target(metrics=("temp",)),),
        tmp_path,
        "Ambiguous timestamps",
        aggregation="native",
        excel=False,
    )
    result = ApiDownloadService(AmbiguousClient()).download(
        request, Event(), lambda _progress: None
    )
    with (result.folder / "analysis_ready.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 3
    assert [row["source_timestamp"] for row in rows[:2]] == ["1725148800", "1725148800"]
    assert [row["point_index"] for row in rows[:2]] == ["1", "2"]
    assert all(row["timestamp_utc"] == "" for row in rows)
    assert all(row["timestamp_local"] == "" for row in rows)


def test_cancellation_keeps_completed_chunk_with_explicit_partial_status(tmp_path):
    stop = Event()

    class CancellingClient(FakeClient):
        def data(self, entity, metrics, start, end, aggregation, stop_event):
            result = super().data(entity, metrics, start, end, aggregation, stop_event)
            stop.set()
            return result

    request = ApiDownloadRequest(
        (
            target(start=date(2026, 1, 1), end=date(2026, 2, 15), metrics=("temp",)),
            target("657", metrics=("temp",)),
        ),
        tmp_path,
        "Cancelled result",
        excel=False,
    )
    result = ApiDownloadService(CancellingClient()).download(request, stop, lambda _progress: None)
    assert result.cancelled
    assert [entry.status for entry in result.files] == ["partial", "cancelled"]
    assert result.files[0].rows == 2
    manifest = json.loads((result.folder / "collection.json").read_text("utf-8"))
    assert manifest["targets"][0]["raw_files"]
    assert manifest["targets"][0]["status"] == "partial"


def test_invalid_output_name_is_rejected_before_any_files_are_created(tmp_path):
    try:
        ApiDownloadRequest((target(),), tmp_path, " CON")
    except ValueError as error:
        assert "file name" in str(error)
    else:
        raise AssertionError("Reserved output name was accepted")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("before", "after"),
    ((-1, 120), (24, 0), (False, 120), (24, True), (721, 720)),
)
def test_invalid_aligned_window_is_rejected(before, after, tmp_path):
    with pytest.raises(ValueError, match="aligned-data window"):
        ApiDownloadRequest(
            (target(),),
            tmp_path,
            aligned_before_hours=before,
            aligned_after_hours=after,
        )


def test_unwritable_destination_is_a_curated_output_error(tmp_path, monkeypatch):
    def denied(*_args, **_kwargs):
        raise PermissionError("private operating-system detail")

    monkeypatch.setattr("pathlib.Path.mkdir", denied)
    request = ApiDownloadRequest((target(),), tmp_path / "blocked", "Output error")
    try:
        ApiDownloadService(FakeClient()).download(request, Event(), lambda _progress: None)
    except ApiError as error:
        assert error.code == "api_output"
        assert "private" not in str(error)
        assert "another location" in str(error)
    else:
        raise AssertionError("Output error was not reported")
