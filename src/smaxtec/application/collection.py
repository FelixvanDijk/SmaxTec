"""Immutable, provider-independent email collection contracts (no credentials)."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


class CollectionError(Exception):
    """Only curated messages cross into the GUI; never wrap raw network/COM errors."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CollectionCancelled(Exception):
    pass


@dataclass(frozen=True)
class MailFolder:
    key: str
    label: str


@dataclass(frozen=True)
class MailMessage:
    key: str
    subject: str
    sender: str
    received_at: datetime
    html_body: str = field(default="", repr=False)
    text_body: str = field(default="", repr=False)


@dataclass(frozen=True)
class MailCandidate:
    key: str
    subject: str
    sender: str
    received_at: datetime
    kind: str
    download_url: str = field(default="", repr=False)
    link_fingerprint: str = ""
    issue: str = ""


@dataclass(frozen=True)
class MailScan:
    candidates: tuple[MailCandidate, ...]
    scanned: int
    warning: str = ""


@dataclass(frozen=True)
class CollectionProgress:
    message: str
    current: int = 0
    total: int = 0


@dataclass(frozen=True)
class CollectedFile:
    key: str
    status: str
    filename: str = ""
    cow_number: str = ""
    detail: str = ""


@dataclass(frozen=True)
class CollectionResult:
    folder: Path
    files: tuple[CollectedFile, ...]
    cancelled: bool = False
