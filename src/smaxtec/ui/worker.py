"""Serialized worker boundary for a single browser-owning thread."""

from collections.abc import Callable
from contextlib import suppress
from queue import Empty, Queue
from threading import Event

from PySide6.QtCore import QThread, Signal

from smaxtec.application.exports import ExportError, ExportRequest
from smaxtec.application.login import (
    Credentials,
    FailureCode,
    LoginCancelled,
    LoginError,
    LoginSession,
)


class SessionWorker(QThread):
    login_progress = Signal(object)
    farms_discovered = Signal(object)
    export_progress = Signal(object)
    export_completed = Signal(object)
    connection_failed = Signal(object)
    export_failed = Signal(object)

    def __init__(self, factory: Callable[[], LoginSession], credentials: Credentials) -> None:
        super().__init__()
        self._factory = factory
        self._credentials: Credentials | None = credentials
        self._stop = Event()
        self._commands: Queue[ExportRequest | None] = Queue()

    def submit_exports(self, request: ExportRequest) -> None:
        self._commands.put(request)

    def request_stop(self) -> None:
        # Queued Qt slots do not run while this thread is inside Playwright.
        self._stop.set()
        self._commands.put(None)

    def run(self) -> None:
        session: LoginSession | None = None
        try:
            if self._stop.is_set():
                return
            session = self._factory()
            assert self._credentials is not None
            session.connect(self._credentials, self.login_progress.emit, self._stop)
            self._credentials = None
            farms = session.discover_farms(self.export_progress.emit, self._stop)
            self.farms_discovered.emit(farms)
            while not self._stop.is_set() and session.is_open():
                try:
                    request = self._commands.get(timeout=0.2)
                except Empty:
                    continue
                if request is None:
                    break
                try:
                    result = session.request_exports(request, self.export_progress.emit, self._stop)
                except LoginCancelled:
                    break
                except ExportError as error:
                    if not self._stop.is_set():
                        self.export_failed.emit(error)
                else:
                    self.export_completed.emit(result)
        except LoginCancelled:
            pass
        except (LoginError, ExportError) as error:
            if not self._stop.is_set():
                self.connection_failed.emit(error)
        except Exception:
            if not self._stop.is_set():
                self.connection_failed.emit(
                    LoginError(
                        FailureCode.UNEXPECTED,
                        "The connection could not finish. Close it and try again. "
                        "If this continues, contact support.",
                    )
                )
        finally:
            self._credentials = None
            if session is not None:
                # Raw browser errors may contain private URLs or page data.
                with suppress(Exception):
                    session.close()


# Compatibility for the first milestone's public import.
LoginWorker = SessionWorker
