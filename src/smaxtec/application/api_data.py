"""Immutable inputs for direct smaXtec data collection, independent of Qt/HTTP."""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ApiError(Exception):
    """Curated errors only; HTTP payloads and credentials must never reach the UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ApiCancelled(Exception):
    pass


@dataclass(frozen=True)
class ApiFarm:
    id: str
    name: str
    timezone: str


@dataclass(frozen=True)
class ApiEntity:
    id: str
    kind: str
    farm: ApiFarm
    number: str
    name: str
    official_id: str = ""
    group: str = ""
    archived: bool = False

    @property
    def label(self) -> str:
        if self.number and self.name and self.number != self.name:
            return f"{self.number} · {self.name}"
        return self.number or self.name or self.id


@dataclass(frozen=True)
class ApiMetric:
    code: str
    units: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApiCatalog:
    farm: ApiFarm
    animals: tuple[ApiEntity, ...]
    groups: tuple[ApiEntity, ...]
    devices: tuple[ApiEntity, ...]
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ApiTarget:
    entity: ApiEntity
    start_date: date
    end_date: date
    metrics: tuple[str, ...] = ()  # Empty means all metrics discovered for this entity.

    def __post_init__(self) -> None:
        if self.entity.kind not in {"animals", "groups", "devices"}:
            raise ValueError("Choose an animal, animal group or device.")
        if not self.entity.id or not self.entity.farm.id:
            raise ValueError("Choose a target from the connected farm.")
        if not date(2000, 1, 1) <= self.start_date <= self.end_date:
            raise ValueError("Use a valid From/To period from 2000 onwards.")
        if self.end_date > datetime.now(ZoneInfo(self.entity.farm.timezone)).date():
            raise ValueError("The To date cannot be in the future for this farm.")
        if len(self.metrics) != len(set(self.metrics)):
            raise ValueError("Each metric may be selected only once.")

    def utc_bounds(self) -> tuple[datetime, datetime]:
        """Whole farm-local days; exact half-open UTC range, including DST changes."""
        zone = ZoneInfo(self.entity.farm.timezone)
        start = datetime.combine(self.start_date, time.min, zone).astimezone(UTC)
        end = datetime.combine(self.end_date + timedelta(days=1), time.min, zone).astimezone(UTC)
        return start, end


@dataclass(frozen=True)
class ApiDownloadRequest:
    targets: tuple[ApiTarget, ...]
    destination: Path
    name: str = "Herd data"
    aggregation: str = "native"
    excel: bool = True
    include_health_index: bool = False

    def __post_init__(self) -> None:
        if not self.targets or len(self.targets) > 5000:
            raise ValueError("Add between 1 and 5,000 targets to the download queue.")
        if not self.destination.is_absolute():
            raise ValueError("Choose a folder for the downloaded collection.")
        if self.aggregation not in {"native", "10minutes", "hourly", "daily"}:
            raise ValueError("Choose a supported measurement resolution.")
        if (
            not self.name.strip()
            or self.name != self.name.strip()
            or len(self.name) > 80
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', self.name)
            or self.name.endswith((".", " "))
            or self.name.split(".")[0].upper() in WINDOWS_RESERVED_NAMES
        ):
            raise ValueError("Use a short file name without Windows reserved characters.")


@dataclass(frozen=True)
class ApiProgress:
    message: str
    current: int = 0
    total: int = 0


@dataclass(frozen=True)
class ApiFileResult:
    target: ApiTarget
    status: str
    rows: int = 0
    detail: str = ""


@dataclass(frozen=True)
class ApiDownloadResult:
    folder: Path
    files: tuple[ApiFileResult, ...]
    rows: int
    cancelled: bool = False
    warnings: tuple[str, ...] = ()
    analysis_csv: Path | None = None
    workbook: Path | None = None
