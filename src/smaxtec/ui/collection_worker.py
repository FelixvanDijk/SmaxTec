"""Short-lived, cancellable collection jobs; no provider objects reach the GUI."""

from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QThread, Signal

from smaxtec.application.collection import (
    CollectionCancelled,
    CollectionError,
    CollectionProgress,
    CollectionResult,
)

CollectionJob = Callable[[Event, Callable[[CollectionProgress], None]], object]


class CollectionWorker(QThread):
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(self, job: CollectionJob) -> None:
        super().__init__()
        self._job: CollectionJob | None = job
        self._stop = Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            if self._stop.is_set():
                raise CollectionCancelled
            assert self._job is not None
            result = self._job(self._stop, self.progress.emit)
            # Download results retain successfully saved files even after cancellation.
            if self._stop.is_set() and not isinstance(result, CollectionResult):
                raise CollectionCancelled
            self.succeeded.emit(result)
        except CollectionCancelled:
            self.cancelled.emit()
        except CollectionError as error:
            # Do not retain adapter stack frames or exception contexts in GUI objects.
            self.failed.emit(CollectionError(error.code, str(error)))
        except Exception:
            self.failed.emit(
                CollectionError(
                    "unexpected",
                    "This collection step could not finish. Completed files are kept. "
                    "Try again, or reconnect Outlook if the problem continues.",
                )
            )
        finally:
            self._job = None
