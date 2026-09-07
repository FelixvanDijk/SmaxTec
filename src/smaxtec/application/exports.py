"""UI-independent farm selection and export request types."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


@dataclass(frozen=True, order=True)
class Farm:
    name: str

    def __post_init__(self) -> None:
        cleaned = " ".join(self.name.split())
        if not cleaned:
            raise ValueError("No farm was selected.")
        object.__setattr__(self, "name", cleaned)


def parse_cow_numbers(raw: str) -> tuple[str, ...]:
    """Parse comma, semicolon, whitespace, or line-separated identifiers."""
    values = [part.strip() for part in re.split(r"[,;\s]+", raw) if part.strip()]
    if not values:
        raise ValueError("Enter at least one cow number.")
    if any(len(value) > 64 for value in values):
        raise ValueError("Cow numbers must be 64 characters or fewer.")
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True)
class ExportRequest:
    farm: Farm
    cow_numbers: tuple[str, ...]
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        cleaned = tuple(dict.fromkeys(value.strip() for value in self.cow_numbers if value.strip()))
        if not cleaned:
            raise ValueError("Enter at least one cow number.")
        if self.start_date > self.end_date:
            raise ValueError("The start date must be on or before the end date.")
        object.__setattr__(self, "cow_numbers", cleaned)

    @property
    def site_start_date(self) -> str:
        return self.start_date.strftime("%d/%m/%Y")

    @property
    def site_end_date(self) -> str:
        return self.end_date.strftime("%d/%m/%Y")


class ExportStage(StrEnum):
    DISCOVERING_FARMS = "discovering_farms"
    FARMS_READY = "farms_ready"
    RECONNECTING = "reconnecting"
    OPENING_FARM = "opening_farm"
    FINDING_COW = "finding_cow"
    REQUESTING_EXPORT = "requesting_export"
    COW_COMPLETE = "cow_complete"


@dataclass(frozen=True)
class ExportProgress:
    stage: ExportStage
    message: str
    current: int = 0
    total: int = 0


@dataclass(frozen=True)
class ExportBatchResult:
    requested: tuple[str, ...]
    skipped_as_already_attempted: tuple[str, ...] = ()


class ExportFailureCode(StrEnum):
    SESSION_EXPIRED = "session_expired"
    PAGE_CHANGED = "page_changed"
    FARM_NOT_FOUND = "farm_not_found"
    COW_NOT_FOUND = "cow_not_found"
    COW_AMBIGUOUS = "cow_ambiguous"
    EXPORT_REJECTED = "export_rejected"
    EXPORT_UNCONFIRMED = "export_unconfirmed"
    SITE_UNAVAILABLE = "site_unavailable"


class ExportError(Exception):
    """Curated failure with completion and no-retry attempt information."""

    def __init__(
        self,
        code: ExportFailureCode,
        message: str,
        completed: tuple[str, ...] = (),
        attempted: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.completed = completed
        self.attempted = attempted


ExportProgressCallback = Callable[[ExportProgress], None]
