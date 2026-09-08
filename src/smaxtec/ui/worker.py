"""Serialized worker boundary for a single browser-owning thread."""

from collections.abc import Callable
from contextlib import suppress
from queue import Empty, Queue
from threading import Event

from PySide6.QtCore import QThread, Signal

from smaxtec.application.exports import (
    CowExport,
    ExportBatchResult,
    ExportError,
    ExportFailureCode,
    ExportProgress,
    ExportRequest,
    ExportStage,
)
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
        self._attempted_exports: set[tuple[str, CowExport]] = set()

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
            session = self._connect_session(reconnecting=False)
            while not self._stop.is_set():
                try:
                    request = self._commands.get(timeout=0.2)
                except Empty:
                    continue
                if request is None:
                    break
                pending_request, previously_attempted = self._without_attempted_exports(request)
                if pending_request is None:
                    self.export_completed.emit(ExportBatchResult((), previously_attempted))
                    continue
                request = pending_request
                if session is None or not session.is_open():
                    self._close_session(session)
                    session = None
                    try:
                        session = self._connect_session(reconnecting=True)
                    except LoginCancelled:
                        break
                    except (LoginError, ExportError) as error:
                        if not self._stop.is_set():
                            self.export_failed.emit(
                                ExportError(
                                    ExportFailureCode.SITE_UNAVAILABLE,
                                    "The automatic reconnection could not finish. "
                                    f"No export was requested. {error}",
                                )
                            )
                        continue
                try:
                    result = session.request_exports(request, self.export_progress.emit, self._stop)
                except LoginCancelled:
                    break
                except ExportError as error:
                    self._remember_attempts(request, error.attempted)
                    if not self._stop.is_set():
                        self.export_failed.emit(error)
                else:
                    self._remember_attempts(request, result.requested)
                    skipped = tuple(
                        dict.fromkeys((*previously_attempted, *result.skipped_as_already_attempted))
                    )
                    self.export_completed.emit(ExportBatchResult(result.requested, skipped))
                finally:
                    # A fresh authenticated browser for each later batch avoids stale
                    # smaXtec SPA state. It is recreated only after another reviewed request.
                    self._close_session(session)
                    session = None
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
            self._attempted_exports.clear()
            self._close_session(session)

    def _connect_session(self, *, reconnecting: bool) -> LoginSession:
        assert self._credentials is not None
        if reconnecting:
            self.export_progress.emit(
                ExportProgress(
                    ExportStage.RECONNECTING,
                    "Opening a fresh secure smaXtec session for this request…",
                )
            )
        session = self._factory()
        try:
            session.connect(self._credentials, self.login_progress.emit, self._stop)
            farms = session.discover_farms(self.export_progress.emit, self._stop)
        except Exception:
            self._close_session(session)
            raise
        self.farms_discovered.emit(farms)
        return session

    def _without_attempted_exports(
        self, request: ExportRequest
    ) -> tuple[ExportRequest | None, tuple[CowExport, ...]]:
        pending: list[CowExport] = []
        skipped: list[CowExport] = []
        for entry in request.entries:
            target = (request.farm.name, entry)
            (skipped if target in self._attempted_exports else pending).append(entry)
        filtered = ExportRequest(request.farm, tuple(pending)) if pending else None
        return filtered, tuple(skipped)

    def _remember_attempts(self, request: ExportRequest, entries: tuple[CowExport, ...]) -> None:
        self._attempted_exports.update((request.farm.name, entry) for entry in entries)

    @staticmethod
    def _close_session(session: LoginSession | None) -> None:
        if session is not None:
            # Raw browser errors may contain private URLs or page data.
            with suppress(Exception):
                session.close()


# Compatibility for the first milestone's public import.
LoginWorker = SessionWorker
