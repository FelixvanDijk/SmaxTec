"""The sign-in boundary shared by the desktop UI and website adapter."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event
from typing import Protocol


@dataclass(frozen=True)
class Credentials:
    username: str = field(repr=False)
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.username.strip() or not self.password.strip():
            raise ValueError("Enter your email address and password.")
        object.__setattr__(self, "username", self.username.strip())


class LoginStage(StrEnum):
    OPENING = "opening"
    LOGIN_FORM = "login_form"
    CREDENTIALS_ENTERED = "credentials_entered"
    VERIFYING = "verifying"
    ACTION_REQUIRED = "action_required"
    CONNECTED = "connected"


@dataclass(frozen=True)
class LoginProgress:
    stage: LoginStage
    message: str


class FailureCode(StrEnum):
    BROWSER_UNAVAILABLE = "browser_unavailable"
    SITE_UNAVAILABLE = "site_unavailable"
    PAGE_CHANGED = "page_changed"
    UNTRUSTED_PAGE = "untrusted_page"
    LOGIN_REJECTED = "login_rejected"
    LOGIN_TIMEOUT = "login_timeout"
    BROWSER_CLOSED = "browser_closed"
    UNEXPECTED = "unexpected"


class LoginError(Exception):
    """Only a curated message crosses into UI; never raw browser exceptions."""

    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class LoginCancelled(Exception):
    """Normal cooperative stop; not an error shown to the user."""


ProgressCallback = Callable[[LoginProgress], None]


class LoginSession(Protocol):
    """All methods must be called on the same owning worker thread."""

    def connect(
        self, credentials: Credentials, progress: ProgressCallback, stop: Event
    ) -> None: ...

    def keep_open(self, stop: Event) -> None: ...

    def close(self) -> None: ...
