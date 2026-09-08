"""UI-independent farm selection and export request types."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
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


def parse_user_date(raw: str, field_name: str) -> date:
    """Parse exactly the date format displayed to the user and sent to smaXtec."""
    value = raw.strip()
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        raise ValueError(f"Enter the {field_name} as DD/MM/YYYY.")
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        raise ValueError(f"Enter a real calendar date for the {field_name}.") from None


def validate_date_range(start_date: date, end_date: date) -> None:
    if start_date < date(2000, 1, 1):
        raise ValueError("The start date cannot be before 01/01/2000.")
    if start_date > end_date:
        raise ValueError("The start date must be on or before the end date.")
    if end_date > date.today():
        raise ValueError("The end date cannot be in the future.")


@dataclass(frozen=True)
class CowExport:
    """One indivisible export target; its dates always travel with its cow number."""

    cow_number: str
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        cleaned = self.cow_number.strip()
        if not cleaned:
            raise ValueError("Enter a cow number.")
        if len(cleaned) > 64 or re.search(r"[,;\s]", cleaned):
            raise ValueError("Enter one cow number per row (up to 64 characters).")
        validate_date_range(self.start_date, self.end_date)
        object.__setattr__(self, "cow_number", cleaned)

    @property
    def site_start_date(self) -> str:
        return self.start_date.strftime("%d/%m/%Y")

    @property
    def site_end_date(self) -> str:
        return self.end_date.strftime("%d/%m/%Y")

    @property
    def description(self) -> str:
        return f"Cow {self.cow_number} · {self.site_start_date} to {self.site_end_date}"


@dataclass(frozen=True)
class ExportRequest:
    farm: Farm
    entries: tuple[CowExport, ...]

    def __post_init__(self) -> None:
        # Copy mutable caller collections and deduplicate only identical targets.
        entries = tuple(dict.fromkeys(self.entries))
        if not entries:
            raise ValueError("Enter at least one cow and date range.")
        object.__setattr__(self, "entries", entries)

    @classmethod
    def for_cows(
        cls, farm: Farm, cow_numbers: tuple[str, ...], start_date: date, end_date: date
    ) -> "ExportRequest":
        """Convenience for callers deliberately applying one period to several cows."""
        return cls(farm, tuple(CowExport(cow, start_date, end_date) for cow in cow_numbers))


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
    requested: tuple[CowExport, ...]
    skipped_as_already_attempted: tuple[CowExport, ...] = ()


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
        completed: tuple[CowExport, ...] = (),
        attempted: tuple[CowExport, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.completed = completed
        self.attempted = attempted


ExportProgressCallback = Callable[[ExportProgress], None]
