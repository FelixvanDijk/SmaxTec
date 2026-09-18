"""Lifecycle-enrichment orchestration tests without live website access."""

from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from smaxtec.application.api_data import ApiError
from smaxtec.application.lifecycle import LifecycleReading, LifecycleTarget
from smaxtec.application.lifecycle_enrichment import LifecycleEnrichmentService


class Reader:
    def __init__(self, readings):
        self.readings = readings
        self.targets = ()

    def read_lact_dim(self, targets, progress, stop):
        self.targets = targets
        return self.readings


def source():
    return SimpleNamespace(
        cases=(
            SimpleNamespace(farm="Farm A", cow="57"),
            SimpleNamespace(farm="Farm A", cow="57"),  # Two periods; one website lookup.
            SimpleNamespace(farm="Farm A", cow="257"),
        )
    )


def test_enrichment_deduplicates_lookups_and_rebuilds_with_available_values(tmp_path, monkeypatch):
    readings = (
        LifecycleReading(LifecycleTarget("Farm A", "57"), 7, 216),
        LifecycleReading(LifecycleTarget("Farm A", "257"), detail="Show diagram is unavailable."),
    )
    reader = Reader(readings)
    expected = tmp_path / "client-analysis-1.xlsx"
    captured = {}
    monkeypatch.setattr(
        "smaxtec.application.lifecycle_enrichment.StudySource.load",
        lambda _folder, _stop: source(),
    )

    def create(_self, folder, stop, progress, *, lifecycle_values=None):
        captured.update(lifecycle_values)
        return expected

    monkeypatch.setattr(
        "smaxtec.application.lifecycle_enrichment.AutomaticStudyWorkbookService.create",
        create,
    )

    result = LifecycleEnrichmentService().enrich(
        Path(tmp_path), reader, Event(), lambda _event: None
    )

    assert reader.targets == (
        LifecycleTarget("Farm A", "57"),
        LifecycleTarget("Farm A", "257"),
    )
    assert captured == {("Farm A", "57"): (7, 216)}
    assert result.workbook == expected
    assert (result.added, result.skipped) == (1, 1)


def test_enrichment_keeps_existing_workbook_when_every_diagram_is_unavailable(
    tmp_path, monkeypatch
):
    readings = (
        LifecycleReading(LifecycleTarget("Farm A", "57"), detail="Unavailable"),
        LifecycleReading(LifecycleTarget("Farm A", "257"), detail="Unavailable"),
    )
    monkeypatch.setattr(
        "smaxtec.application.lifecycle_enrichment.StudySource.load",
        lambda _folder, _stop: source(),
    )

    with pytest.raises(ApiError, match="No cow diagram"):
        LifecycleEnrichmentService().enrich(
            tmp_path, Reader(readings), Event(), lambda _event: None
        )
