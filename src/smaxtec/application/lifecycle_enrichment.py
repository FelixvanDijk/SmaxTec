"""Read-only website Lact/DIM enrichment for a completed API collection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from smaxtec.application.api_data import ApiCancelled, ApiError, ApiProgress
from smaxtec.application.lifecycle import LifecycleReader, LifecycleReading, LifecycleTarget
from smaxtec.application.study_workbook import AutomaticStudyWorkbookService, StudySource


@dataclass(frozen=True)
class LifecycleEnrichmentResult:
    workbook: Path
    readings: tuple[LifecycleReading, ...]

    @property
    def added(self) -> int:
        return sum(reading.available for reading in self.readings)

    @property
    def skipped(self) -> int:
        return len(self.readings) - self.added


class LifecycleEnrichmentService:
    """Validate website readings and regenerate a non-overwriting analysis workbook."""

    def enrich(
        self,
        folder: Path,
        reader: LifecycleReader,
        stop: Event,
        progress: Callable[[ApiProgress], None],
    ) -> LifecycleEnrichmentResult:
        source = StudySource.load(folder, stop)
        targets = tuple(
            dict.fromkeys(LifecycleTarget(case.farm, case.cow) for case in source.cases)
        )
        if stop.is_set():
            raise ApiCancelled
        progress(ApiProgress("Opening the website to read Lact and DIM…", 0, len(targets)))
        readings = tuple(reader.read_lact_dim(targets, progress, stop))
        if len(readings) != len(targets) or {item.target for item in readings} != set(targets):
            raise ApiError(
                "lifecycle_results",
                "The website results did not match the reviewed collection. "
                "The existing analysis workbook was not changed.",
            )
        values = {
            (item.target.farm, item.target.cow): (item.lactation, item.dim)
            for item in readings
            if item.available
        }
        if not values:
            raise ApiError(
                "lifecycle_unavailable",
                "No cow diagram supplied both Lact and DIM. The existing analysis remains "
                "available; disabled diagrams and unavailable cows were left blank.",
            )
        progress(ApiProgress("Building an enriched client analysis workbook…", 0, 3))
        workbook = AutomaticStudyWorkbookService().create(
            folder,
            stop,
            progress,
            lifecycle_values=values,
        )
        return LifecycleEnrichmentResult(workbook, readings)
