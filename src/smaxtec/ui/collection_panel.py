"""Independent email collection workspace with an explicit, frozen review step."""

import re
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Protocol

from PySide6.QtCore import QStandardPaths, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smaxtec.application.collection import (
    CollectionError,
    CollectionProgress,
    CollectionResult,
    MailCandidate,
    MailFolder,
    MailScan,
)
from smaxtec.ui.collection_worker import CollectionJob, CollectionWorker
from smaxtec.ui.widgets import label


class Mailbox(Protocol):
    def list_inboxes(self, stop: Event) -> tuple[MailFolder, ...]: ...

    def scan(
        self,
        folder: MailFolder,
        limit: int,
        lookback_days: int,
        stop: Event,
        progress: Callable[[CollectionProgress], None],
    ) -> MailScan: ...


class Downloader(Protocol):
    def download(
        self,
        candidates: tuple[MailCandidate, ...],
        destination: Path,
        stop: Event,
        progress: Callable[[CollectionProgress], None],
        resume_folder: Path | None = None,
    ) -> CollectionResult: ...


Importer = Callable[[tuple[Path, ...], Event], MailScan]
EMPTY_REVIEW_NOTE = (
    "Only matching export messages are counted. New arrivals cannot change a reviewed "
    "selection. Forwarded receive dates do not renew the original link's lifetime."
)


def _display(value: str) -> str:
    """Email metadata stays inert plain text; bearer links never become UI text."""
    text = re.sub(r"(?i)\b(?:https?://|www\.)\S+", "[link hidden]", str(value))
    return " ".join(text.split())[:300]


class CollectionPanel(QFrame):
    idle = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        mailbox: Mailbox | None = None,
        microsoft_mailbox: Mailbox | None = None,
        outlook_mailbox: Mailbox | None = None,
        service: Downloader | None = None,
        importer: Importer | None = None,
    ) -> None:
        super().__init__(parent)
        self._injected_mailbox = mailbox
        self._microsoft_mailbox = microsoft_mailbox
        self._outlook_mailbox = outlook_mailbox
        self._mailbox: Mailbox | None = None
        self._active_source = ""
        self._service = service
        self._importer = importer
        self._worker: CollectionWorker | None = None
        self._operation = ""
        self._candidates: tuple[MailCandidate, ...] = ()
        self._result: CollectionResult | None = None
        self._last_folder: Path | None = None
        self._download_started = False
        self._cancelling = False
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(11)
        layout.addWidget(label("3. Collect your emailed exports", "cardTitle"))
        layout.addWidget(
            label(
                "Once your emails have arrived, find and review the ones to download. "
                "This is separate from your smaXtec connection.",
                "muted",
            )
        )

        self.source_controls = QWidget()
        source = QVBoxLayout(self.source_controls)
        source.setContentsMargins(0, 0, 0, 0)
        source.setSpacing(9)
        account_row = QHBoxLayout()
        self.connect_button = self._button(
            "Sign in with Microsoft 365", self._connect_microsoft, primary=True
        )
        self.classic_connect_button = self._button("Connect classic Outlook", self._connect_outlook)
        self.disconnect_button = self._button("Disconnect", self._disconnect)
        self.import_button = self._button("Import saved emails…", self._choose_emails)
        account_row.addWidget(self.connect_button, 1)
        account_row.addWidget(self.classic_connect_button, 1)
        source.addLayout(account_row)
        fallback_row = QHBoxLayout()
        fallback_row.addWidget(self.disconnect_button)
        fallback_row.addStretch()
        fallback_row.addWidget(self.import_button)
        source.addLayout(fallback_row)
        source.addWidget(
            label(
                "Microsoft 365 sign-in works with mailboxes used in new Outlook, Outlook on "
                "the web and classic Outlook, using your browser and normal MFA. The classic "
                "connector remains available as a fallback. Workbench never asks for your "
                "email password.",
                "privacy",
            )
        )
        source.addWidget(label("Inbox", "fieldLabel"))
        self.inbox = QComboBox()
        self.inbox.setAccessibleName("Collection mailbox Inbox")
        self.inbox.addItem("Connect a mailbox to choose an Inbox")
        self.inbox.currentIndexChanged.connect(self._invalidate_review)
        source.addWidget(self.inbox)
        filters = QHBoxLayout()
        filters.addWidget(label("Latest", "fieldLabel", wrap=False))
        self.latest = QSpinBox()
        self.latest.setRange(1, 1000)
        self.latest.setValue(10)
        self.latest.setAccessibleName("Latest matching email count")
        filters.addWidget(self.latest)
        filters.addWidget(label("matching emails received in the last", "muted", wrap=False))
        self.lookback = QSpinBox()
        self.lookback.setRange(1, 30)
        self.lookback.setValue(1)
        self.lookback.setAccessibleName("Email lookback days")
        filters.addWidget(self.lookback)
        filters.addWidget(label("day(s)", "muted", wrap=False))
        filters.addStretch()
        source.addLayout(filters)
        self.latest.valueChanged.connect(self._invalidate_review)
        self.lookback.valueChanged.connect(self._invalidate_review)
        self.scan_button = self._button("Find export emails", self._scan)
        source.addWidget(self.scan_button)

        source.addWidget(label("Save collections to", "fieldLabel"))
        destination_row = QHBoxLayout()
        self.destination = QLineEdit()
        self.destination.setReadOnly(True)
        self.destination.setAccessibleName("Collection output folder")
        self.destination.setPlaceholderText("Choose a collection folder with Browse…")
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        if documents and Path(documents).is_absolute():
            self.destination.setText(str(Path(documents) / "SmaxTec Workbench" / "Collections"))
        destination_row.addWidget(self.destination, 1)
        self.browse_button = self._button("Browse…", self._browse)
        destination_row.addWidget(self.browse_button)
        source.addLayout(destination_row)
        layout.addWidget(self.source_controls)

        self.review_title = label("No emails selected yet", "statusTitle")
        layout.addWidget(self.review_title)
        self.table = QTableWidget(0, 5)
        self.table.setAccessibleName("Reviewed export emails and collection results")
        self.table.setHorizontalHeaderLabels(
            ["Received (local)", "Sender", "Subject", "Source", "Status"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setMinimumSectionSize(65)
        for index, width in enumerate((128, 110, 150, 84, 160)):
            self.table.setColumnWidth(index, width)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setFixedHeight(240)
        self.table.hide()
        layout.addWidget(self.table)
        self.review_note = label(EMPTY_REVIEW_NOTE, "muted")
        layout.addWidget(self.review_note)
        self.resume_controls = QWidget()
        resume_row = QHBoxLayout(self.resume_controls)
        resume_row.setContentsMargins(0, 0, 0, 0)
        self.resume_button = self._button("Resume existing collection…", self._resume_existing)
        resume_row.addWidget(self.resume_button)
        resume_row.addWidget(
            label(
                "Returning after a restart? Re-select the same emails, then choose "
                "their collection folder.",
                "privacy",
            ),
            1,
        )
        layout.addWidget(self.resume_controls)
        actions = QHBoxLayout()
        self.download_button = self._button(
            "Download reviewed emails", self._download, primary=True
        )
        self.cancel_button = self._button("Cancel", self.cancel)
        actions.addWidget(self.download_button, 1)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)
        result_actions = QHBoxLayout()
        self.retry_button = self._button("Retry incomplete downloads", self._retry)
        self.open_button = self._button("Open collection folder", self._open_folder)
        result_actions.addWidget(self.retry_button)
        result_actions.addWidget(self.open_button)
        result_actions.addStretch()
        layout.addLayout(result_actions)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = label("Ready when your emails are.", "muted")
        layout.addWidget(self.status)
        layout.addWidget(
            label(
                "Each workbook is named using its own B3 cow number; notes such as “(new girl)” "
                "are ignored. Existing files are never overwritten. Excel is not opened and "
                "existing sensitivity labels are unchanged. Email selection does not verify "
                "the farm, requested cow number or date period.",
                "privacy",
            )
        )
        self._update_controls()

    @staticmethod
    def _button(text: str, action: Callable, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("primary" if primary else "secondary")
        button.clicked.connect(action)
        return button

    @property
    def is_busy(self) -> bool:
        return self._worker is not None

    def _provider(self) -> Mailbox:
        if self._mailbox is None:
            raise CollectionError(
                "mailbox_disconnected", "Connect a mailbox before searching its Inbox."
            )
        return self._mailbox

    def _choose_provider(self, source: str) -> Mailbox:
        if self._injected_mailbox is not None:
            provider = self._injected_mailbox
        elif source == "microsoft":
            if self._microsoft_mailbox is None:
                from smaxtec.adapters.mail.graph import GraphMailbox

                self._microsoft_mailbox = GraphMailbox()
            provider = self._microsoft_mailbox
        else:
            if self._outlook_mailbox is None:
                from smaxtec.adapters.mail.outlook import OutlookMailbox

                self._outlook_mailbox = OutlookMailbox()
            provider = self._outlook_mailbox
        self._mailbox = provider
        self._active_source = source
        return provider

    def _downloader(self) -> Downloader:
        if self._service is None:
            from smaxtec.application.collection_service import CollectionService

            local_data = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            )
            if not local_data or not Path(local_data).is_absolute():
                raise CollectionError(
                    "local_data_unavailable",
                    "Windows could not locate your application data folder. "
                    "Restart Workbench before downloading.",
                )
            self._service = CollectionService(Path(local_data) / "collections.sqlite")
        return self._service

    def _connect_microsoft(self) -> None:
        self._connect("microsoft")

    def _connect_outlook(self) -> None:
        self._connect("outlook")

    def _connect(self, source: str = "microsoft") -> None:
        if self.is_busy:
            return
        self._invalidate_review()
        provider = self._choose_provider(source)
        operation = "connect_microsoft" if source == "microsoft" else "connect_outlook"
        self._start(operation, lambda stop, _progress: provider.list_inboxes(stop))

    def _disconnect(self) -> None:
        if self.is_busy:
            return
        provider = self._mailbox
        disconnect = getattr(provider, "disconnect", None)
        if callable(disconnect):
            disconnect()
        self._mailbox = None
        self._active_source = ""
        self.inbox.clear()
        self.inbox.addItem("Connect a mailbox to choose an Inbox")
        self._invalidate_review()
        self.status.setText(
            "Mailbox disconnected. Microsoft tokens were cleared from Workbench memory; "
            "Outlook applications stay open."
        )

    def _scan(self) -> None:
        folder = self.inbox.currentData()
        if self.is_busy or not isinstance(folder, MailFolder):
            return
        limit, days = self.latest.value(), self.lookback.value()
        self._invalidate_review()
        self._start(
            "scan",
            lambda stop, progress: self._provider().scan(folder, limit, days, stop, progress),
        )

    def _choose_emails(self) -> None:
        if self.is_busy:
            return
        paths, _filter = QFileDialog.getOpenFileNames(
            self,
            "Choose saved export emails",
            "",
            "Saved emails (*.eml *.msg)",
        )
        if paths:
            self.import_paths(tuple(Path(path) for path in paths))

    def import_paths(self, paths: tuple[Path, ...]) -> None:
        """Explicit file selection, also useful to native drag/drop entry points later."""
        if self.is_busy or not paths:
            return
        selected = tuple(paths)
        self._invalidate_review()

        def import_job(stop: Event, _progress: Callable[[CollectionProgress], None]) -> MailScan:
            if self._importer is not None:
                return self._importer(selected, stop)
            from smaxtec.adapters.mail.messages import import_emails

            return import_emails(selected, stop)

        self._start("import", import_job)

    def _browse(self) -> None:
        if self.is_busy:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Save collections to", self.destination.text()
        )
        if folder:
            self.destination.setText(folder)
            self._invalidate_review()

    def _invalidate_review(self) -> None:
        if self.is_busy:
            return
        self._candidates = ()
        self._result = None
        self._download_started = False
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.hide()
        self.review_title.setText("No emails selected yet")
        self.review_note.setText(EMPTY_REVIEW_NOTE)
        self._update_controls()

    def _download(self) -> None:
        if self.is_busy or self._download_started or not self._has_downloadable():
            return
        self._download_started = True
        selected, destination = self._candidates, Path(self.destination.text())
        self._start(
            "download",
            lambda stop, progress: self._downloader().download(
                selected, destination, stop, progress
            ),
        )

    def _retry(self) -> None:
        if self.is_busy or self._result is None or not self._candidates:
            return
        selected, folder = self._candidates, self._result.folder
        destination = Path(self.destination.text())
        self._start(
            "download",
            lambda stop, progress: self._downloader().download(
                selected, destination, stop, progress, resume_folder=folder
            ),
        )

    def _resume_existing(self) -> None:
        if self.is_busy or not self._candidates:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Choose the existing collection folder", self.destination.text()
        )
        if not folder or self.is_busy:
            return
        # Selection is already reviewed; the service verifies exact saved keys/order
        # and completed file hashes. This action never rediscovers or tops up emails.
        selected, destination = self._candidates, Path(self.destination.text())
        self._download_started = True
        self._start(
            "download",
            lambda stop, progress: self._downloader().download(
                selected, destination, stop, progress, resume_folder=Path(folder)
            ),
        )

    def _has_downloadable(self) -> bool:
        return Path(self.destination.text()).is_absolute() and any(
            item.download_url and not item.issue for item in self._candidates
        )

    def _start(self, operation: str, job: CollectionJob) -> None:
        if self.is_busy:
            return
        self._operation = operation
        self._cancelling = False
        worker = CollectionWorker(job)
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.cancelled.connect(self._on_cancelled)
        worker.finished.connect(self._on_finished)
        self.status.setText(
            {
                "connect_microsoft": "Opening secure Microsoft sign-in in your browser…",
                "connect_outlook": "Looking for signed-in classic Outlook mailboxes…",
                "scan": "Finding matching emails, newest first…",
                "import": "Reading the saved emails you selected…",
                "download": "Downloading this reviewed selection…",
            }[operation]
        )
        self.progress.setRange(0, 0)
        self.progress.show()
        self._update_controls()
        worker.start()

    def _on_progress(self, progress: CollectionProgress) -> None:
        if self._cancelling:
            return
        self.status.setText(_display(progress.message))
        self.progress.setRange(0, progress.total)
        self.progress.setValue(progress.current)

    def _on_success(self, result: object) -> None:
        if self._operation.startswith("connect_") and isinstance(result, tuple):
            self.inbox.clear()
            self.inbox.addItem("Choose an Inbox…")
            for folder in result:
                if isinstance(folder, MailFolder):
                    self.inbox.addItem(_display(folder.label), folder)
            self.status.setText("Choose the Inbox to search. No emails have been read yet.")
            if self.inbox.count() == 1:
                self.status.setText("No usable Inbox was found. Reconnect or import saved emails.")
        elif isinstance(result, MailScan):
            self._candidates = tuple(result.candidates)
            self._show_review(result)
        elif isinstance(result, CollectionResult):
            self._result = result
            self._last_folder = result.folder
            self.open_button.setToolTip(str(result.folder))
            files = {item.key: item for item in result.files}
            for row, candidate in enumerate(self._candidates):
                item = files.get(candidate.key)
                if item is not None:
                    detail = item.filename or item.detail
                    self.table.item(row, 4).setText(_display(f"{item.status}: {detail}"))
                    self.table.item(row, 4).setToolTip(_display(item.detail or detail))
            saved = sum(item.status == "saved" for item in result.files)
            duplicate = sum(item.status == "duplicate" for item in result.files)
            failed = sum(item.status in {"failed", "cancelled"} for item in result.files)
            prefix = "Collection cancelled. " if result.cancelled else "Collection finished. "
            self.status.setText(
                f"{prefix}{saved} saved · {duplicate} duplicate(s) · {failed} incomplete. "
                "Open the collection folder to inspect files and the manifest."
            )
        else:
            self._on_failure(
                CollectionError("unexpected_result", "This step returned no usable result.")
            )

    def _show_review(self, scan: MailScan) -> None:
        self.table.setRowCount(len(self._candidates))
        seen: set[str] = set()
        duplicates = issues = 0
        for row, candidate in enumerate(self._candidates):
            status = "Ready to download"
            if candidate.issue or not candidate.download_url:
                issues += 1
                status = candidate.issue or "No verified download link"
            elif candidate.link_fingerprint in seen:
                duplicates += 1
                status = "Duplicate link in this selection"
            elif candidate.link_fingerprint:
                seen.add(candidate.link_fingerprint)
            values = (
                candidate.received_at.astimezone().strftime("%d/%m/%Y %H:%M"),
                candidate.sender,
                candidate.subject,
                candidate.kind,
                status,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(_display(value))
                item.setToolTip(_display(value))
                self.table.setItem(row, column, item)
        self.table.setVisible(bool(self._candidates))
        source = (
            "Manually selected saved emails"
            if self._operation == "import"
            else (
                "Newest Inbox matches - Microsoft 365"
                if self._active_source == "microsoft"
                else "Newest Inbox matches - classic Outlook"
            )
        )
        self.review_title.setText(f"{source} · {len(self._candidates)} reviewed")
        self.review_note.setText(
            f"{duplicates} duplicate link(s) · {issues} message(s) needing attention. "
            "Download includes exactly this list; failures are not replaced with older emails. "
            "Cow numbers are identified only after downloading each workbook."
        )
        self.status.setText(
            _display(scan.warning)
            or f"Reviewed {len(self._candidates)} matching message(s) "
            f"from {scan.scanned} inspected. "
            "Check the list, then choose Download reviewed emails."
        )

    def _on_failure(self, error: CollectionError) -> None:
        self.status.setText(_display(str(error)))
        # A failure before a result has no resumable folder. Do not invent one.
        if self._operation == "download" and self._result is None:
            self._download_started = False

    def _on_cancelled(self) -> None:
        self.status.setText("Cancelled. Completed files, if any, are kept.")
        if self._operation == "download" and self._result is None:
            self._download_started = False

    def _on_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self.progress.hide()
        self._cancelling = False
        self._update_controls()
        self.idle.emit()

    def _update_controls(self) -> None:
        busy = self.is_busy
        connected = any(
            isinstance(self.inbox.itemData(i), MailFolder) for i in range(self.inbox.count())
        )
        self.source_controls.setEnabled(not busy)
        self.connect_button.setEnabled(not busy and not connected)
        self.classic_connect_button.setEnabled(not busy and not connected)
        self.disconnect_button.setEnabled(not busy and (connected or bool(self._candidates)))
        self.inbox.setEnabled(not busy and connected)
        self.scan_button.setEnabled(not busy and isinstance(self.inbox.currentData(), MailFolder))
        self.download_button.setEnabled(
            not busy and not self._download_started and self._has_downloadable()
        )
        self.resume_controls.setVisible(bool(self._candidates))
        self.resume_button.setEnabled(not busy and self._has_downloadable())
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy and not self._cancelling)
        retryable = self._result is not None and (
            self._result.cancelled
            or any(item.status in {"failed", "cancelled"} for item in self._result.files)
        )
        self.retry_button.setVisible(retryable)
        self.retry_button.setEnabled(not busy and retryable)
        self.open_button.setVisible(self._last_folder is not None)
        self.open_button.setEnabled(not busy and self._last_folder is not None)

    def cancel(self) -> None:
        if self._worker is not None:
            self._cancelling = True
            self._worker.request_stop()
            self.status.setText("Stopping safely; completed files will be kept…")
            self._update_controls()

    def _open_folder(self) -> None:
        if (
            not self.is_busy
            and self._last_folder is not None
            and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_folder)))
        ):
            self.status.setText(
                f"Could not open the collection folder. Open this path in File Explorer: "
                f"{self._last_folder}"
            )
