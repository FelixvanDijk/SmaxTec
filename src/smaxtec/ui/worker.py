"""The GUI's worker boundary; no website selectors or Playwright objects here."""

from collections.abc import Callable
from contextlib import suppress
from threading import Event

from PySide6.QtCore import QThread, Signal

from smaxtec.application.login import (
    Credentials,
    FailureCode,
    LoginCancelled,
    LoginError,
    LoginSession,
)


class LoginWorker(QThread):
    progress = Signal(object)
    failed = Signal(object)

    def __init__(self, factory: Callable[[], LoginSession], credentials: Credentials) -> None:
        super().__init__()
        self._factory = factory
        self._credentials: Credentials | None = credentials
        self._stop = Event()

    def request_stop(self) -> None:
        # A queued Qt slot would not run while this worker is inside Playwright.
        self._stop.set()

    def run(self) -> None:
        session: LoginSession | None = None
        try:
            if self._stop.is_set():
                return
            session = self._factory()
            assert self._credentials is not None
            session.connect(self._credentials, self.progress.emit, self._stop)
            self._credentials = None
            session.keep_open(self._stop)
        except LoginCancelled:
            pass
        except LoginError as error:
            if not self._stop.is_set():
                self.failed.emit(error)
        except Exception:
            if not self._stop.is_set():
                self.failed.emit(
                    LoginError(
                        FailureCode.UNEXPECTED,
                        "The connection could not finish. Close it and try again. "
                        "If this continues, contact support.",
                    )
                )
        finally:
            self._credentials = None
            if session is not None:
                # No raw error output: browser errors may contain secrets.
                with suppress(Exception):
                    session.close()
