"""Direct-data workspace: discovery, individual periods and immutable review.

All HTTP and file operations run in a serialized, cancellable worker. Tables carry
the original entity value, so display names, sorting and farm changes cannot change
which animal owns a date range.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from threading import Event
from typing import Protocol
from zoneinfo import ZoneInfo

from PySide6.QtCore import QItemSelectionModel, QStandardPaths, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from smaxtec.application.api_data import (
    ApiCancelled,
    ApiCatalog,
    ApiDownloadRequest,
    ApiDownloadResult,
    ApiEntity,
    ApiError,
    ApiFarm,
    ApiMetric,
    ApiProgress,
    ApiTarget,
)
from smaxtec.application.exports import parse_cow_numbers, parse_user_date
from smaxtec.application.login import Credentials
from smaxtec.application.study_workbook import (
    AutomaticStudyWorkbookService,
    parse_event_time,
)
from smaxtec.ui.widgets import date_entry, label


class ApiClient(Protocol):
    def connect(self, credentials: Credentials, stop: Event) -> tuple[ApiFarm, ...]: ...

    def catalog(self, farm: ApiFarm, archived: bool, stop: Event) -> ApiCatalog: ...

    def metrics(self, entity: ApiEntity, stop: Event) -> tuple[ApiMetric, ...]: ...

    def disconnect(self) -> None: ...


class ApiDownloader(Protocol):
    def download(
        self,
        request: ApiDownloadRequest,
        stop: Event,
        progress: Callable[[ApiProgress], None],
    ) -> ApiDownloadResult: ...


ApiJob = Callable[[Event, Callable[[ApiProgress], None]], object]
KIND_LABELS = {"animals": "Cow", "groups": "Group", "devices": "Device"}
EXTRAS_NOTE = (
    "Optional farm datasets cover the entire farm, from its earliest queued From date "
    "through its latest To date. They are not limited to the selected cows."
)


@dataclass(frozen=True)
class _MetricDiscovery:
    """Measurements supported by every entity in one frozen queue selection."""

    entities: tuple[ApiEntity, ...]
    metrics: tuple[ApiMetric, ...]


def _text(value: str) -> str:
    """Remote names are inert and bounded; credential-like URLs stay out of UI."""
    return re.sub(r"(?i)\b(?:https?://|www\.)\S+", "[link hidden]", str(value))[:500]


def _item(value: str, *, editable: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(_text(value))
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class _DateDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):  # noqa: N802
        editor = date_entry(date.today(), "Individual From or To date, DD/MM/YYYY")
        editor.setParent(parent)
        return editor


class _ApiWorker(QThread):
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(self, job: ApiJob) -> None:
        super().__init__()
        self._job: ApiJob | None = job
        self._stop = Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            if self._stop.is_set():
                raise ApiCancelled
            assert self._job is not None
            result = self._job(self._stop, self.progress.emit)
            if self._stop.is_set() and not isinstance(result, ApiDownloadResult):
                raise ApiCancelled
            self.succeeded.emit(result)
        except ApiCancelled:
            self.cancelled.emit()
        except ApiError as error:
            self.failed.emit(ApiError(error.code, str(error)))
        except Exception:
            self.failed.emit(
                ApiError(
                    "unexpected",
                    "This data step could not finish. Any completed files are kept. "
                    "Try again, or disconnect and sign in again if the issue continues.",
                )
            )
        finally:
            self._job = None


class ApiReviewDialog(QDialog):
    """Every farm/entity/date/measurement association is visible before collection."""

    def __init__(self, request: ApiDownloadRequest, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review your direct data download")
        self.resize(1120, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(label("Your data, ready to collect", "cardTitle"))
        layout.addWidget(
            label(
                f"{len(request.targets):,} individual targets · {request.name}\n"
                "From and To include whole days in each farm's timezone. "
                "Saved measurement timestamps use UTC.",
                "muted",
            )
        )
        self.table = QTableWidget(len(request.targets), 8)
        self.table.setAccessibleName("All reviewed API targets and individual dates")
        self.table.setHorizontalHeaderLabels(
            ["Farm", "Type", "Target", "From", "To", "Study T0", "Timezone", "Measurements"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row, target in enumerate(request.targets):
            values = (
                target.entity.farm.name,
                KIND_LABELS[target.entity.kind],
                target.entity.label,
                target.start_date.strftime("%d/%m/%Y"),
                target.end_date.strftime("%d/%m/%Y"),
                (
                    target.study_event_utc.astimezone(
                        ZoneInfo(target.entity.farm.timezone)
                    ).strftime("%d/%m/%Y %H:%M")
                    if target.study_event_utc
                    else "Default: From 00:00 · period anchor"
                ),
                target.entity.farm.timezone,
                ", ".join(target.metrics) or "All available for this target",
            )
            for column, value in enumerate(values):
                cell = _item(value)
                cell.setToolTip(_text(value))
                self.table.setItem(row, column, cell)
        layout.addWidget(self.table, 1)
        formats = "Raw JSON + audit CSV + graph-ready CSV" + (
            " + polished Excel" if request.excel else ""
        )
        if any(target.entity.kind == "animals" for target in request.targets):
            formats += " + automatic client analysis"
        layout.addWidget(
            label(
                f"{formats} · Resolution: {request.aggregation}\n"
                f"A new collection folder will be created inside {request.destination}.",
                "muted",
            )
        )
        extras = []
        if request.include_health_index:
            extras.append("Farm health index")
        if extras:
            layout.addWidget(label(", ".join(extras) + ". " + EXTRAS_NOTE, "privacy"))
        layout.addWidget(
            label(
                "Availability depends on your account, sensors and smaXtec's data retention. "
                "Unavailable or empty data will be reported; no emails are requested.",
                "privacy",
            )
        )
        buttons = QDialogButtonBox()
        back = buttons.addButton("Back to edit", QDialogButtonBox.ButtonRole.RejectRole)
        back.setObjectName("secondary")
        back.setDefault(True)
        download = buttons.addButton("Download data", QDialogButtonBox.ButtonRole.AcceptRole)
        download.setObjectName("primary")
        download.setAutoDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ApiPanel(QWidget):
    """Independent API connection and download lifecycle for the main workspace."""

    idle = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        client: ApiClient | None = None,
        service: ApiDownloader | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._service = service
        self._worker: _ApiWorker | None = None
        self._operation = ""
        self._connected = False
        self._cancelling = False
        self._shutting_down = False
        self._catalog: ApiCatalog | None = None
        self._entities: tuple[ApiEntity, ...] = ()
        self._metrics_entities: tuple[ApiEntity, ...] = ()
        self._last_folder: Path | None = None
        self._last_analysis: Path | None = None
        self._last_workbook: Path | None = None
        self._last_client_workbook: Path | None = None
        self._reviewing = False
        self.setObjectName("apiPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(13)
        heading = QHBoxLayout()
        heading.addWidget(label("Direct data studio", "heading"), 1)
        heading.addWidget(label("OFFICIAL API · NO EMAILS", "badge"))
        layout.addLayout(heading)
        layout.addWidget(
            label(
                "Browse your herd, build a collection and save your data directly. "
                "Choose individual dates for every cow, group or device.",
                "intro",
            )
        )
        self.account = QFrame()
        self.account.setObjectName("card")
        account = QVBoxLayout(self.account)
        account.setContentsMargins(18, 12, 18, 12)
        account.setSpacing(8)
        account_heading = QHBoxLayout()
        self.account_status = label("Connect your smaXtec account", "statusTitle")
        account_heading.addWidget(self.account_status, 1)
        self.disconnect_button = self._button("Disconnect", self.disconnect)
        account_heading.addWidget(self.disconnect_button)
        account.addLayout(account_heading)
        self.account_fields = QWidget()
        account_fields = QGridLayout(self.account_fields)
        account_fields.setContentsMargins(0, 0, 0, 0)
        account_fields.setHorizontalSpacing(10)
        account_fields.setVerticalSpacing(5)
        self.username = QLineEdit()
        self.username.setPlaceholderText("smaXtec email address")
        self.username.setAccessibleName("API smaXtec email address")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("smaXtec password")
        self.password.setAccessibleName("API smaXtec password")
        self.connect_button = self._button("Connect", self._connect, primary=True)
        account_fields.addWidget(label("Email address", "fieldLabel"), 0, 0)
        account_fields.addWidget(label("Password", "fieldLabel"), 0, 1)
        account_fields.addWidget(self.username, 1, 0)
        account_fields.addWidget(self.password, 1, 1)
        account_fields.addWidget(self.connect_button, 1, 2)
        account_fields.setColumnStretch(0, 1)
        account_fields.setColumnStretch(1, 1)
        account.addWidget(self.account_fields)
        account.addWidget(
            label("Credentials and API session stay in memory until you disconnect.", "privacy")
        )
        layout.addWidget(self.account)
        self.steps = QTabWidget()
        self.steps.setObjectName("apiSteps")
        self.steps.setDocumentMode(True)
        self.browse_page = self._build_browse()
        self.queue_page = self._build_queue()
        self.results_page = self._build_results()
        self.browse_scroll = self._scrollable_page(
            self.browse_page, "Scrollable farm and target browser"
        )
        self.queue_scroll = self._scrollable_page(
            self.queue_page, "Scrollable direct data download queue"
        )
        self.results_scroll = self._scrollable_page(
            self.results_page, "Scrollable direct data results"
        )
        self.steps.addTab(self.browse_scroll, "1  Browse herd")
        self.steps.addTab(self.queue_scroll, "2  Download queue (0)")
        self.steps.addTab(self.results_scroll, "3  Results")
        layout.addWidget(self.steps, 1)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        status_row = QHBoxLayout()
        self.status = label(
            "Sign in to discover the farms and data available to your account.", "muted"
        )
        status_row.addWidget(self.status, 1)
        self.cancel_button = self._button("Cancel", self.cancel)
        status_row.addWidget(self.cancel_button)
        layout.addLayout(status_row)
        self._update_controls()

    @staticmethod
    def _button(text: str, action: Callable, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("primary" if primary else "secondary")
        button.clicked.connect(action)
        return button

    @staticmethod
    def _scrollable_page(page: QWidget, accessible_name: str) -> QScrollArea:
        """Keep styled controls at usable heights on short laptop displays."""
        page.setObjectName("apiStepPage")
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        scroll = QScrollArea()
        scroll.setObjectName("apiPageScroll")
        scroll.setAccessibleName(accessible_name)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    @staticmethod
    def _table(columns: list[str], accessible_name: str) -> QTableWidget:
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setAccessibleName(accessible_name)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(38)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # MultiSelection lets nontechnical users toggle several rows with ordinary
        # clicks; Ctrl/Command knowledge is not required.
        table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(150)
        return table

    def _build_browse(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(10)
        filters = QGridLayout()
        filters.setHorizontalSpacing(12)
        filters.setVerticalSpacing(5)
        self.farm = QComboBox()
        self.farm.setAccessibleName("API farm")
        self.farm.addItem("Connect to choose a farm")
        self.farm.currentIndexChanged.connect(self._load_catalog)
        self.kind = QComboBox()
        self.kind.setAccessibleName("API inventory type")
        for title, key in (
            ("Cows", "animals"),
            ("Animal groups", "groups"),
            ("Devices", "devices"),
        ):
            self.kind.addItem(title, key)
        self.kind.currentIndexChanged.connect(self._show_inventory)
        self.archived = QCheckBox("Include archived cows")
        self.archived.toggled.connect(self._load_catalog)
        filters.addWidget(label("Farm", "fieldLabel"), 0, 0)
        filters.addWidget(label("Browse", "fieldLabel"), 0, 1)
        filters.addWidget(label("Catalogue", "fieldLabel"), 0, 2)
        filters.addWidget(self.farm, 1, 0)
        filters.addWidget(self.kind, 1, 1)
        filters.addWidget(self.archived, 1, 2)
        filters.setColumnStretch(0, 3)
        filters.setColumnStretch(1, 2)
        filters.setColumnStretch(2, 2)
        layout.addLayout(filters)
        self.inventory_note = label("Your connected farms will appear here.", "muted")
        layout.addWidget(self.inventory_note)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search this farm by number, name, ear tag or group…")
        self.search.setAccessibleName("Filter API inventory")
        self.search.textChanged.connect(self._filter_inventory)
        layout.addWidget(self.search)
        self.inventory = self._table(
            ["Number / serial", "Name", "Ear tag", "Group", "Status"], "API farm inventory"
        )
        self.inventory.setMinimumHeight(340)
        self.inventory.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inventory.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.inventory, 1)

        selection_card = QFrame()
        selection_card.setObjectName("card")
        selection_layout = QVBoxLayout(selection_card)
        selection_layout.setContentsMargins(16, 14, 16, 14)
        selection_layout.setSpacing(10)
        selection = QHBoxLayout()
        self.selection_note = label("0 targets selected", "statusTitle")
        selection.addWidget(self.selection_note, 1)
        self.select_shown_button = self._button("Select all filtered", self._select_shown)
        self.clear_selection_button = self._button("Clear selected", self.inventory.clearSelection)
        selection.addWidget(self.select_shown_button)
        selection.addWidget(self.clear_selection_button)
        selection_layout.addLayout(selection)
        selection_layout.addWidget(
            label(
                "Click any cow row to add or remove it from the selection—Ctrl is not required.",
                "privacy",
            )
        )
        exact = QHBoxLayout()
        self.cow_numbers = QPlainTextEdit()
        self.cow_numbers.setPlaceholderText(
            "Paste exact cow numbers — one per line, or separated by commas or spaces"
        )
        self.cow_numbers.setAccessibleName("Exact API cow numbers")
        self.cow_numbers.setMinimumHeight(82)
        self.cow_numbers.setMaximumHeight(110)
        self.exact_button = self._button("Select these cow numbers", self._select_exact)
        exact.addWidget(self.cow_numbers, 1)
        exact.addWidget(self.exact_button, alignment=Qt.AlignmentFlag.AlignTop)
        selection_layout.addLayout(exact)
        dates = QHBoxLayout()
        dates.addWidget(label("From", "fieldLabel", wrap=False))
        self.shared_from = date_entry(date.today() - timedelta(days=7), "API shared From date")
        dates.addWidget(self.shared_from)
        dates.addWidget(label("To", "fieldLabel", wrap=False))
        self.shared_to = date_entry(date.today(), "API shared To date")
        dates.addWidget(self.shared_to)
        self.add_button = self._button("Add selected to queue", self._add_selected, primary=True)
        dates.addWidget(self.add_button, 1)
        selection_layout.addLayout(dates)
        selection_layout.addWidget(
            label(
                "Dates use DD/MM/YYYY and the farm's timezone. Each queued target keeps its "
                "own dates. Choose measurements for one or many targets in Download queue.",
                "privacy",
            )
        )
        layout.addWidget(selection_card)
        return page

    def _build_queue(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(10)
        self.queue_note = label(
            "Add targets from Browse. Double-click dates or optional study T0 to edit a row.",
            "muted",
        )
        layout.addWidget(self.queue_note)
        layout.addWidget(
            label(
                "Cow collections automatically get a client-analysis.xlsx companion. "
                "Study T0 is optional. If blank, the client-analysis workbook uses "
                "From 00:00 as a clearly labelled period anchor to pivot readings. "
                "Enter the actual per-cow T0 for treatment-relative studies.",
                "privacy",
            )
        )
        self.queue = self._table(
            [
                "Farm",
                "Type",
                "Target",
                "From · DD/MM/YYYY",
                "To · DD/MM/YYYY",
                "Study T0 · DD/MM/YYYY HH:MM",
                "Measurements",
            ],
            "API download queue with individual dates",
        )
        self.queue.setMinimumHeight(220)
        self.queue.setItemDelegateForColumn(3, _DateDelegate(self.queue))
        self.queue.setItemDelegateForColumn(4, _DateDelegate(self.queue))
        self.queue.itemChanged.connect(self._queue_changed)
        self.queue.itemSelectionChanged.connect(self._queue_selection_changed)
        layout.addWidget(self.queue, 1)
        queue_tools = QFrame()
        queue_tools.setObjectName("card")
        queue_actions = QGridLayout(queue_tools)
        queue_actions.setContentsMargins(18, 14, 18, 14)
        queue_actions.setHorizontalSpacing(10)
        queue_actions.setVerticalSpacing(8)
        self.select_queue_button = self._button("Select every queued target", self._select_queue)
        self.clear_queue_selection_button = self._button(
            "Clear row selection", self.queue.clearSelection
        )
        self.remove_button = self._button("Remove selected rows", self._remove_selected)
        self.clear_queue_button = self._button("Clear entire queue", self._clear_queue)
        self.apply_dates_button = self._button("Apply Browse dates to all", self._apply_dates)
        queue_actions.addWidget(label("Selected rows", "fieldLabel"), 0, 0, 1, 2)
        queue_actions.addWidget(self.select_queue_button, 1, 0)
        queue_actions.addWidget(self.clear_queue_selection_button, 1, 1)
        queue_actions.addWidget(self.remove_button, 2, 0)
        queue_actions.addWidget(label("Whole queue", "fieldLabel"), 3, 0, 1, 2)
        queue_actions.addWidget(self.apply_dates_button, 4, 0)
        queue_actions.addWidget(self.clear_queue_button, 4, 1)
        queue_actions.setColumnStretch(0, 1)
        queue_actions.setColumnStretch(1, 1)
        layout.addWidget(queue_tools)
        measurements = QFrame()
        measurements.setObjectName("card")
        metric_layout = QVBoxLayout(measurements)
        metric_layout.setContentsMargins(18, 16, 18, 16)
        metric_layout.setSpacing(10)
        metric_heading = QHBoxLayout()
        metric_heading.addWidget(label("Measurements for selected queue rows", "cardTitle"), 1)
        self.metric_selection_note = label("No queue rows selected", "muted", wrap=False)
        metric_heading.addWidget(self.metric_selection_note)
        metric_layout.addLayout(metric_heading)
        metric_actions = QHBoxLayout()
        self.load_metrics_button = self._button("Find common measurements", self._load_metrics)
        metric_actions.addWidget(self.load_metrics_button)
        self.all_metrics = QCheckBox(
            "Download every available measurement for each selected target"
        )
        self.all_metrics.setChecked(True)
        self.all_metrics.toggled.connect(self._metric_controls)
        metric_actions.addWidget(self.all_metrics, 1)
        metric_layout.addLayout(metric_actions)
        self.metric_note = label(
            "Select one or more rows above. Use all available data, or discover the "
            "measurement codes supported by every selected target.",
            "privacy",
        )
        metric_layout.addWidget(self.metric_note)
        self.metrics = QListWidget()
        self.metrics.setAccessibleName("Available API measurement codes and units")
        self.metrics.setMinimumHeight(190)
        metric_layout.addWidget(self.metrics)
        self.apply_metrics_button = self._button(
            "Apply measurements to selected rows", self._apply_metrics, primary=True
        )
        metric_layout.addWidget(self.apply_metrics_button, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(measurements)
        settings = QFrame()
        settings.setObjectName("card")
        settings_layout = QGridLayout(settings)
        settings_layout.setContentsMargins(18, 16, 18, 16)
        settings_layout.setHorizontalSpacing(12)
        settings_layout.setVerticalSpacing(9)
        settings_layout.addWidget(label("Collection settings", "cardTitle"), 0, 0, 1, 4)
        self.resolution = QComboBox()
        self.resolution.setAccessibleName("API measurement resolution")
        for name, value in (
            ("Native · original resolution", "native"),
            ("10-minute aggregation", "10minutes"),
            ("Hourly aggregation", "hourly"),
            ("Daily aggregation", "daily"),
        ):
            self.resolution.addItem(name, value)
        settings_layout.addWidget(label("Measurement resolution", "fieldLabel"), 1, 0, 1, 2)
        settings_layout.addWidget(self.resolution, 2, 0, 1, 2)
        self.health_index = QCheckBox("Include farm health index")
        settings_layout.addWidget(self.health_index, 2, 2, 1, 2)
        settings_layout.addWidget(label(EXTRAS_NOTE, "privacy"), 3, 0, 1, 4)
        self.destination = QLineEdit()
        self.destination.setReadOnly(True)
        self.destination.setAccessibleName("API collection output folder")
        self.destination.setPlaceholderText("Choose where to save your data…")
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        if documents and Path(documents).is_absolute():
            self.destination.setText(str(Path(documents) / "SmaxTec Workbench" / "API Collections"))
        self.browse_button = self._button("Browse…", self._browse)
        settings_layout.addWidget(label("Save collections inside", "fieldLabel"), 4, 0, 1, 4)
        settings_layout.addWidget(self.destination, 5, 0, 1, 3)
        settings_layout.addWidget(self.browse_button, 5, 3)
        self.collection_name = QLineEdit("Herd data")
        self.collection_name.setAccessibleName("API collection name")
        self.collection_name.setPlaceholderText("Collection name")
        self.collection_name.setMaxLength(80)
        self.excel = QCheckBox("Also create Excel workbook")
        self.excel.setChecked(True)
        self.download_button = self._button(
            "Review & download", self._review_download, primary=True
        )
        settings_layout.addWidget(label("Collection name", "fieldLabel"), 6, 0, 1, 2)
        settings_layout.addWidget(self.collection_name, 7, 0, 1, 2)
        settings_layout.addWidget(self.excel, 7, 2)
        settings_layout.addWidget(self.download_button, 7, 3)
        settings_layout.setColumnStretch(0, 2)
        settings_layout.setColumnStretch(1, 2)
        settings_layout.setColumnStretch(2, 1)
        settings_layout.setColumnStretch(3, 1)
        settings_layout.addWidget(
            label(
                "Every collection includes original JSON, an audit CSV, graph-ready "
                "analysis_ready.csv and a provenance manifest. "
                "Choose a name above; a unique folder prevents overwriting earlier work.",
                "privacy",
            ),
            8,
            0,
            1,
            4,
        )
        layout.addWidget(settings)
        return page

    def _build_results(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(10)
        self.result_summary = label("Your collections will appear here", "cardTitle")
        layout.addWidget(self.result_summary)
        self.result_note = label(
            "Review your download queue to begin. You can keep working on another collection "
            "after the current download finishes.",
            "muted",
        )
        layout.addWidget(self.result_note)
        self.file_card = QFrame()
        self.file_card.setObjectName("resultFiles")
        file_layout = QGridLayout(self.file_card)
        file_layout.setContentsMargins(18, 16, 18, 16)
        file_layout.setHorizontalSpacing(16)
        file_layout.setVerticalSpacing(10)
        file_layout.addWidget(label("Your collection files", "cardTitle"), 0, 0, 1, 3)
        self.open_analysis_button = self._button(
            "Open graph-ready CSV", lambda: self._open_file(self._last_analysis, "CSV")
        )
        self.open_workbook_button = self._button(
            "Open Excel workbook", lambda: self._open_file(self._last_workbook, "workbook")
        )
        self.open_client_workbook_button = self._button(
            "Open client analysis",
            lambda: self._open_file(self._last_client_workbook, "client analysis workbook"),
        )
        self.open_button = self._button("Open collection folder", self._open_folder)
        file_rows = (
            (
                "ANALYSE",
                "Graph-ready CSV",
                "Clean, tidy rows for filtering and future charts.",
                self.open_analysis_button,
            ),
            (
                "PRESENT",
                "Excel workbook",
                "Styled overview, measurement index and source data.",
                self.open_workbook_button,
            ),
            (
                "ANALYSE",
                "Client analysis workbook",
                "One sheet, one cow per row, in the client's 28-column order.",
                self.open_client_workbook_button,
            ),
            (
                "AUDIT",
                "Complete collection",
                "Raw JSON, both CSV views, workbook and manifest.",
                self.open_button,
            ),
        )
        for row, (purpose, title, description, button) in enumerate(file_rows, start=1):
            file_layout.addWidget(label(purpose, "eyebrow", wrap=False), row, 0)
            file_layout.addWidget(label(f"{title}\n{description}", "statusTitle"), row, 1)
            file_layout.addWidget(button, row, 2)
        file_layout.setColumnStretch(1, 1)
        layout.addWidget(self.file_card)
        study_actions = QVBoxLayout()
        study_actions.addWidget(
            label(
                "Client study view · one row per cow, exact time points and aligned 95% limits",
                "muted",
            ),
        )
        self.auto_saved_button = self._button(
            "Rebuild automatic analysis from saved collection…",
            self._rebuild_automatic_saved,
        )
        study_actions.addWidget(self.auto_saved_button, alignment=Qt.AlignmentFlag.AlignLeft)
        study_buttons = QHBoxLayout()
        self.saved_study_button = self._button(
            "Choose saved collection…", lambda: self._open_study(None)
        )
        self.study_button = self._button(
            "Create study workbook", lambda: self._open_study(self._last_folder), primary=True
        )
        study_buttons.addWidget(self.saved_study_button)
        study_buttons.addWidget(self.study_button)
        study_buttons.addStretch(1)
        study_actions.addLayout(study_buttons)
        layout.addLayout(study_actions)
        self.results = self._table(
            ["Farm", "Target", "From", "To", "Status", "Rows", "Details"],
            "API collection results by target and date range",
        )
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.results, 1)
        return page

    @property
    def is_busy(self) -> bool:
        return self._worker is not None or self._reviewing

    def _connect(self) -> None:
        if self.is_busy or self._connected:
            return
        try:
            credentials = Credentials(self.username.text(), self.password.text())
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.password.clear()

        def connect_job(stop: Event, _progress: Callable[[ApiProgress], None]):
            if self._client is None:
                from smaxtec.adapters.smaxtec.api import SmaxtecApiClient

                self._client = SmaxtecApiClient()
            try:
                return self._client.connect(credentials, stop)
            except Exception:
                self._client.disconnect()
                raise

        self._start("connect", connect_job, "Connecting directly to smaXtec…")

    def disconnect(self) -> None:
        if self._worker is not None:
            return
        self.password.clear()
        self._connected = False
        self._catalog = None
        self._entities = ()
        self._metrics_entities = ()
        self.farm.blockSignals(True)
        self.farm.clear()
        self.farm.addItem("Connect to choose a farm")
        self.farm.blockSignals(False)
        self.inventory.setRowCount(0)
        self.metrics.clear()
        self.all_metrics.setChecked(True)
        self._clear_queue()
        self.account_status.setText("Connect your smaXtec account")
        self.inventory_note.setText("Your connected farms will appear here.")
        self.metric_note.setText(
            "Add targets to the queue, then select rows to assign measurements."
        )
        if self._client is not None:
            client = self._client
            self._start(
                "disconnect", lambda _stop, _progress: client.disconnect(), "Disconnecting…"
            )
        else:
            self._update_controls()

    def shutdown(self) -> None:
        """Wait for a running operation, then release API session before emitting idle."""
        self._shutting_down = True
        self.password.clear()
        if self._worker is not None:
            self.cancel()
        else:
            self.disconnect()

    def _load_catalog(self) -> None:
        if self.is_busy or not self._connected:
            return
        self._catalog = None
        self._entities = ()
        self.inventory.setRowCount(0)
        farm = self.farm.currentData()
        if not isinstance(farm, ApiFarm):
            self._update_controls()
            return
        archived = self.archived.isChecked()
        client = self._client
        assert client is not None
        self._start(
            "catalog",
            lambda stop, _progress: client.catalog(farm, archived, stop),
            "Loading this farm's cows, groups and devices…",
        )

    def _show_inventory(self) -> None:
        if self._catalog is None:
            self._entities = ()
        else:
            self._entities = getattr(self._catalog, self.kind.currentData())
        self.inventory.setRowCount(0)
        self.inventory.setRowCount(len(self._entities))
        for row, entity in enumerate(self._entities):
            values = (
                entity.number,
                entity.name,
                entity.official_id,
                entity.group,
                "Archived" if entity.archived else "Current",
            )
            for column, value in enumerate(values):
                self.inventory.setItem(row, column, _item(value))
            self.inventory.item(row, 0).setData(Qt.ItemDataRole.UserRole, entity)
        if self._catalog is not None:
            catalog = self._catalog
            self.inventory_note.setText(
                f"{len(catalog.animals):,} cows · {len(catalog.groups):,} groups · "
                f"{len(catalog.devices):,} devices · Farm timezone: {_text(catalog.farm.timezone)}"
            )
        self._filter_inventory()
        self._update_controls()

    def _filter_inventory(self) -> None:
        self.inventory.clearSelection()
        query = self.search.text().strip().casefold()
        for row, entity in enumerate(self._entities):
            values = (entity.number, entity.name, entity.official_id, entity.group)
            self.inventory.setRowHidden(
                row, bool(query) and not any(query in value.casefold() for value in values)
            )
        self._selection_changed()

    def _selected_entities(self) -> tuple[ApiEntity, ...]:
        return tuple(
            self.inventory.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            for index in sorted(
                self.inventory.selectionModel().selectedRows(), key=lambda i: i.row()
            )
        )

    def _selection_changed(self) -> None:
        selected = self._selected_entities()
        visible = sum(
            not self.inventory.isRowHidden(row) for row in range(self.inventory.rowCount())
        )
        self.selection_note.setText(f"{len(selected):,} selected · {visible:,} shown")
        self._update_controls()

    def _select_shown(self) -> None:
        self.inventory.clearSelection()
        for row in range(self.inventory.rowCount()):
            if not self.inventory.isRowHidden(row):
                self.inventory.selectionModel().select(
                    self.inventory.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

    def _select_exact(self) -> None:
        if self._catalog is None or self.is_busy:
            return
        try:
            numbers = parse_cow_numbers(self.cow_numbers.toPlainText())
            by_number: dict[str, list[ApiEntity]] = {}
            for entity in self._catalog.animals:
                by_number.setdefault(entity.number, []).append(entity)
            missing = [number for number in numbers if number not in by_number]
            ambiguous = [number for number in numbers if len(by_number.get(number, ())) > 1]
            if missing or ambiguous:
                parts = []
                if missing:
                    parts.append("Not found: " + ", ".join(missing[:20]))
                if ambiguous:
                    parts.append("More than one exact match: " + ", ".join(ambiguous[:20]))
                raise ValueError("; ".join(parts) + ". Check the numbers and archived filter.")
        except ValueError as error:
            self.inventory.clearSelection()
            self.status.setText(_text(str(error)))
            return
        self.kind.setCurrentIndex(0)
        self.search.clear()
        self.inventory.clearSelection()
        chosen = {by_number[number][0].id for number in numbers}
        for row, entity in enumerate(self._entities):
            if entity.id in chosen:
                self.inventory.selectionModel().select(
                    self.inventory.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
        self.status.setText(
            f"Selected {len(chosen):,} exact cow numbers. Choose dates and add to queue."
        )

    def _reset_measurements(self) -> None:
        self._metrics_entities = ()
        self.metrics.clear()
        self.all_metrics.setChecked(True)
        self.metric_note.setText(
            "Select one or more queue rows. Use all available data, or discover the "
            "measurement codes supported by every selected target."
        )

    def _load_metrics(self) -> None:
        entities = self._selected_queue_entities()
        if self.is_busy or not entities:
            return
        client = self._client
        assert client is not None

        def discover_job(stop: Event, progress: Callable[[ApiProgress], None]):
            discovered: list[tuple[ApiEntity, tuple[ApiMetric, ...]]] = []
            for index, entity in enumerate(entities, 1):
                if stop.is_set():
                    raise ApiCancelled
                progress(
                    ApiProgress(
                        f"Checking measurements for {entity.label}…",
                        index - 1,
                        len(entities),
                    )
                )
                discovered.append((entity, client.metrics(entity, stop)))
            first_metrics = discovered[0][1]
            common_codes = {metric.code for metric in first_metrics}
            for _entity, entity_metrics in discovered[1:]:
                common_codes.intersection_update(metric.code for metric in entity_metrics)
            metrics: list[ApiMetric] = []
            for first_metric in first_metrics:
                if first_metric.code not in common_codes:
                    continue
                units: list[str] = []
                for _entity, entity_metrics in discovered:
                    match = next(
                        metric for metric in entity_metrics if metric.code == first_metric.code
                    )
                    units.extend(unit for unit in match.units if unit not in units)
                metrics.append(ApiMetric(first_metric.code, tuple(units)))
            return _MetricDiscovery(entities, tuple(metrics))

        self._reset_measurements()
        self._start(
            "metrics",
            discover_job,
            f"Finding measurements shared by {len(entities):,} selected targets…",
        )

    def _chosen_metrics(self) -> tuple[str, ...]:
        if self.all_metrics.isChecked():
            return ()
        if self._metrics_entities != self._selected_queue_entities():
            raise ValueError(
                "Select queue rows and find their common measurements before "
                "choosing specific data."
            )
        codes = tuple(
            self.metrics.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.metrics.count())
            if self.metrics.item(index).checkState() == Qt.CheckState.Checked
        )
        if not codes:
            raise ValueError("Choose at least one measurement, or use All available measurements.")
        return codes

    def _metric_controls(self) -> None:
        selection_matches = (
            bool(self._metrics_entities)
            and self._metrics_entities == self._selected_queue_entities()
        )
        self.metrics.setEnabled(
            not self.all_metrics.isChecked() and selection_matches and not self.is_busy
        )

    def _shared_dates(self) -> tuple[date, date]:
        return (
            parse_user_date(self.shared_from.text(), "From date"),
            parse_user_date(self.shared_to.text(), "To date"),
        )

    def _add_selected(self) -> None:
        if self.is_busy:
            return
        selected = self._selected_entities()
        if not selected:
            return
        try:
            start, end = self._shared_dates()
            targets = tuple(ApiTarget(entity, start, end) for entity in selected)
            if self.queue.rowCount() + len(targets) > 5000:
                raise ValueError(
                    "A collection can contain at most 5,000 targets. Download this queue first."
                )
        except ValueError as error:
            self.status.setText(_text(str(error)))
            return
        for target in targets:
            row = self.queue.rowCount()
            self.queue.insertRow(row)
            values = (
                target.entity.farm.name,
                KIND_LABELS[target.entity.kind],
                target.entity.label,
                target.start_date.strftime("%d/%m/%Y"),
                target.end_date.strftime("%d/%m/%Y"),
                "",
                ", ".join(target.metrics) or "All available",
            )
            for column, value in enumerate(values):
                cell = _item(value, editable=column in (3, 4, 5))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, target.entity)
                if column == 6:
                    cell.setData(Qt.ItemDataRole.UserRole, target.metrics)
                self.queue.setItem(row, column, cell)
        self._queue_changed()
        self.status.setText(
            f"Added {len(targets):,} targets. Open Download queue to edit individual "
            "dates and assign measurements."
        )

    def _selected_queue_rows(self) -> tuple[int, ...]:
        return tuple(
            index.row()
            for index in sorted(
                self.queue.selectionModel().selectedRows(), key=lambda index: index.row()
            )
        )

    def _selected_queue_entities(self) -> tuple[ApiEntity, ...]:
        entities: list[ApiEntity] = []
        for row in self._selected_queue_rows():
            item = self.queue.item(row, 0)
            entity = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(entity, ApiEntity) and entity not in entities:
                entities.append(entity)
        return tuple(entities)

    def _queue_selection_changed(self) -> None:
        rows = self._selected_queue_rows()
        entities = self._selected_queue_entities()
        self.metric_selection_note.setText(
            f"{len(rows):,} rows · {len(entities):,} unique targets selected"
            if rows
            else "No queue rows selected"
        )
        if self._metrics_entities and self._metrics_entities != entities:
            self._reset_measurements()
        self._update_controls()

    def _select_queue(self) -> None:
        self.queue.selectAll()

    def _queue_changed(self) -> None:
        count = self.queue.rowCount()
        # Small jobs should reach measurement controls quickly; large jobs get a
        # taller viewport for scanning many targets without crowding the rows.
        self.queue.setMinimumHeight(220 if count <= 3 else 320 if count <= 8 else 380)
        self.steps.setTabText(1, f"2  Download queue ({count:,})")
        self.queue_note.setText(
            f"{count:,} queued targets. Click rows to select one or many without Ctrl. "
            "Double-click dates or optional study T0 (DD/MM/YYYY HH:MM) to edit that row only."
            if count
            else "Add cows, groups or devices from Browse herd, then assign measurements here."
        )
        self._queue_selection_changed()
        self._update_controls()

    def _clear_queue(self) -> None:
        self.queue.setRowCount(0)
        self._queue_changed()

    def _remove_selected(self) -> None:
        for row in reversed(self._selected_queue_rows()):
            self.queue.removeRow(row)
        self._queue_changed()

    def _apply_dates(self) -> None:
        try:
            start, end = self._shared_dates()
            # Validate every farm before mutating even one row.
            for row in range(self.queue.rowCount()):
                entity = self.queue.item(row, 0).data(Qt.ItemDataRole.UserRole)
                event_text = self.queue.item(row, 5).text().strip()
                event = parse_event_time(event_text, entity.farm.timezone) if event_text else None
                ApiTarget(entity, start, end, study_event_utc=event)
        except ValueError as error:
            self.status.setText(_text(str(error)))
            return
        for row in range(self.queue.rowCount()):
            self.queue.item(row, 3).setText(start.strftime("%d/%m/%Y"))
            self.queue.item(row, 4).setText(end.strftime("%d/%m/%Y"))
        self.status.setText(
            "The Browse From and To dates were explicitly applied to every queued target."
        )

    def _apply_metrics(self) -> None:
        rows = self._selected_queue_rows()
        if not rows:
            self.status.setText("Select one or more queue rows before applying measurements.")
            return
        try:
            metrics = self._chosen_metrics()
        except ValueError as error:
            self.status.setText(str(error))
            return
        for row in rows:
            cell = self.queue.item(row, 6)
            cell.setText(", ".join(metrics) or "All available")
            cell.setData(Qt.ItemDataRole.UserRole, metrics)
        self.status.setText(f"Measurements applied to {len(rows):,} selected queue rows.")

    def build_request(self) -> ApiDownloadRequest:
        """Read every row once, including off-screen rows; keep identities with dates."""
        targets: list[ApiTarget] = []
        for row in range(self.queue.rowCount()):
            try:
                entity = self.queue.item(row, 0).data(Qt.ItemDataRole.UserRole)
                event_text = self.queue.item(row, 5).text().strip()
                target = ApiTarget(
                    entity=entity,
                    start_date=parse_user_date(self.queue.item(row, 3).text(), "From date"),
                    end_date=parse_user_date(self.queue.item(row, 4).text(), "To date"),
                    metrics=self.queue.item(row, 6).data(Qt.ItemDataRole.UserRole),
                    study_event_utc=(
                        parse_event_time(event_text, entity.farm.timezone) if event_text else None
                    ),
                )
            except ValueError as error:
                self.queue.selectRow(row)
                self.queue.scrollToItem(self.queue.item(row, 3))
                raise ValueError(f"Queue row {row + 1}: {error}") from None
            if target not in targets:
                targets.append(target)
        return ApiDownloadRequest(
            targets=tuple(targets),
            destination=Path(self.destination.text()),
            name=self.collection_name.text(),
            aggregation=self.resolution.currentData(),
            excel=self.excel.isChecked(),
            include_health_index=self.health_index.isChecked(),
        )

    def _review_download(self) -> None:
        if self.is_busy or not self._connected:
            return
        try:
            request = self.build_request()
        except ValueError as error:
            self.status.setText(_text(str(error)))
            return
        self._reviewing = True
        self._update_controls()
        dialog = ApiReviewDialog(request, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        dialog.deleteLater()
        self._reviewing = False
        self._update_controls()
        if not accepted:
            self.status.setText("Review cancelled. No data was requested.")
            return

        def download_job(stop: Event, progress: Callable[[ApiProgress], None]):
            if self._service is None:
                from smaxtec.application.api_downloads import ApiDownloadService

                self._service = ApiDownloadService(self._client)
            return self._service.download(request, stop, progress)

        self.results.setRowCount(0)
        self._last_analysis = None
        self._last_workbook = None
        self._last_client_workbook = None
        self.result_summary.setText("Collecting your data…")
        self.result_note.setText("Completed files will be kept if you cancel this collection.")
        self.steps.setCurrentIndex(2)
        self._start(
            "download", download_job, "Downloading the reviewed data directly from smaXtec…"
        )

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Save API collections to", self.destination.text()
        )
        if folder:
            self.destination.setText(folder)

    def _start(self, operation: str, job: ApiJob, message: str) -> None:
        if self._worker is not None:
            return
        self._operation = operation
        self._cancelling = False
        self._worker = _ApiWorker(job)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(self._on_finished)
        self.status.setText(message)
        self.progress.setRange(0, 0)
        self.progress.show()
        self._update_controls()
        self._worker.start()

    def _on_progress(self, progress: ApiProgress) -> None:
        if not self._cancelling:
            self.status.setText(_text(progress.message))
            self.progress.setRange(0, progress.total)
            self.progress.setValue(progress.current)

    def _on_success(self, result: object) -> None:
        if self._cancelling and not isinstance(result, ApiDownloadResult):
            return
        if self._operation == "connect" and isinstance(result, tuple):
            self._connected = True
            self.account_status.setText("Connected to smaXtec · direct data access")
            self.farm.blockSignals(True)
            self.farm.clear()
            self.farm.addItem("Choose a farm…")
            for farm in result:
                if isinstance(farm, ApiFarm):
                    self.farm.addItem(_text(farm.name), farm)
            self.farm.blockSignals(False)
            self.status.setText("Connected. Choose a farm to discover cows, groups and devices.")
        elif isinstance(result, ApiCatalog):
            self._catalog = result
            self._show_inventory()
            self.status.setText("Farm loaded. Select targets and choose the dates you need.")
        elif self._operation == "metrics" and isinstance(result, _MetricDiscovery):
            self.metrics.clear()
            self._metrics_entities = result.entities
            for metric in result.metrics:
                suffix = " · " + ", ".join(metric.units) if metric.units else ""
                item = QListWidgetItem(_text(metric.code + suffix))
                item.setData(Qt.ItemDataRole.UserRole, metric.code)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.metrics.addItem(item)
            if result.metrics:
                self.all_metrics.setChecked(False)
                self.metric_note.setText(
                    f"{len(result.metrics):,} measurement codes are available on every one of "
                    f"the {len(result.entities):,} selected targets. Uncheck anything "
                    "you do not need."
                )
            else:
                self.all_metrics.setChecked(True)
                self.metric_note.setText(
                    "The selected targets have no measurement code in common. Select fewer rows, "
                    "or apply all available measurements so each target uses its own data."
                )
            self.steps.setCurrentIndex(1)
            self.status.setText(
                "Common measurements discovered. Review the checked codes, then "
                "apply to selected rows."
            )
        elif isinstance(result, ApiDownloadResult):
            self._show_result(result)
        elif self._operation == "auto_saved" and isinstance(result, Path):
            self._last_folder = result.parent
            self._last_client_workbook = result
            self.open_button.setToolTip(str(result.parent))
            self.steps.setCurrentIndex(2)
            self.result_summary.setText("Client analysis rebuilt")
            self.result_note.setText(
                "The new workbook is beside the original collection. If Study T0 "
                "was not supplied, its named hours use From 00:00 as a period anchor, "
                "not a treatment event. Earlier baselines may be blank if not downloaded."
            )
            self.status.setText("Client analysis ready. Open it from Results.")
        elif self._operation == "disconnect":
            self.status.setText("Disconnected. Credentials and API session were released.")
        # Normally finished follows this queued signal and refreshes controls. Keep
        # this handler complete on its own as Qt does not promise ordering between
        # our custom result signal and QThread.finished across every platform.
        self._update_controls()

    def _show_result(self, result: ApiDownloadResult) -> None:
        self._last_folder = result.folder
        self._last_analysis = result.analysis_csv
        self._last_workbook = result.workbook
        self._last_client_workbook = result.client_workbook
        self.open_button.setToolTip(str(result.folder))
        self.results.setRowCount(len(result.files))
        for row, entry in enumerate(result.files):
            values = (
                entry.target.entity.farm.name,
                entry.target.entity.label,
                entry.target.start_date.strftime("%d/%m/%Y"),
                entry.target.end_date.strftime("%d/%m/%Y"),
                entry.status,
                f"{entry.rows:,}",
                entry.detail,
            )
            for column, value in enumerate(values):
                item = _item(value)
                item.setToolTip(_text(value))
                self.results.setItem(row, column, item)
        saved = sum(entry.status == "saved" for entry in result.files)
        prefix = "Collection cancelled" if result.cancelled else "Collection finished"
        self.result_summary.setText(f"{prefix} · {result.rows:,} measurement rows")
        self.result_note.setText(
            f"{saved:,} of {len(result.files):,} targets saved. Your graph-ready CSV"
            + (" and Excel workbook are ready.\n" if result.workbook else " is ready.\n")
            + (
                "Client analysis was also created. Missing study T0 used From 00:00 "
                "as a period anchor, not a treatment event. The one-sheet table "
                "keeps unavailable fields blank.\n"
                if result.client_workbook
                else ""
            )
            + "\n".join(_text(warning) for warning in result.warnings)
        )
        self.status.setText(
            f"{prefix}. Open the graph-ready CSV, workbook or complete collection below."
        )

    def _on_failure(self, error: ApiError) -> None:
        self.status.setText(_text(str(error)))
        if self._operation == "connect":
            self.account_status.setText("Could not connect to smaXtec")
        elif self._operation == "download":
            self.result_summary.setText("Collection needs attention")
            self.result_note.setText(_text(str(error)))

    def _on_cancelled(self) -> None:
        if self._operation == "connect":
            self.account_status.setText("Connect your smaXtec account")
            self.status.setText("Connection cancelled. Enter your password to try again.")
        else:
            self.status.setText("Cancelled. Completed files, if any, are kept.")
        if self._operation == "download":
            self.result_summary.setText("Collection cancelled")

    def _on_finished(self) -> None:
        operation = self._operation
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self.progress.hide()
        self._cancelling = False
        if operation != "disconnect" and self._shutting_down:
            self.disconnect()
            if self._worker is not None:
                return
        self._update_controls()
        self.idle.emit()

    def _update_controls(self) -> None:
        busy = self.is_busy or self._shutting_down
        queue_rows = self._selected_queue_rows()
        queue_entities = self._selected_queue_entities()
        queue_count = self.queue.rowCount()
        self.account.setEnabled(not busy)
        self.account_fields.setVisible(not self._connected)
        self.username.setEnabled(not busy and not self._connected)
        self.password.setEnabled(not busy and not self._connected)
        self.connect_button.setEnabled(not busy and not self._connected)
        self.disconnect_button.setVisible(self._connected)
        self.disconnect_button.setEnabled(not busy and self._connected)
        self.browse_page.setEnabled(not busy and self._connected)
        self.queue_page.setEnabled(not busy and self._connected)
        self.farm.setEnabled(not busy and self._connected)
        self.add_button.setEnabled(not busy and bool(self._selected_entities()))
        self.select_queue_button.setEnabled(not busy and queue_count > 0)
        self.clear_queue_selection_button.setEnabled(not busy and bool(queue_rows))
        self.remove_button.setEnabled(not busy and bool(queue_rows))
        self.clear_queue_button.setEnabled(not busy and queue_count > 0)
        self.load_metrics_button.setEnabled(not busy and bool(queue_entities))
        self.exact_button.setEnabled(not busy and self._catalog is not None)
        self.download_button.setEnabled(not busy and self._connected and queue_count > 0)
        self.apply_dates_button.setEnabled(not busy and queue_count > 0)
        metrics_ready = self.all_metrics.isChecked() or (
            bool(self._metrics_entities) and self._metrics_entities == queue_entities
        )
        self.apply_metrics_button.setEnabled(not busy and bool(queue_rows) and metrics_ready)
        self.open_analysis_button.setEnabled(not busy and self._last_analysis is not None)
        self.open_workbook_button.setEnabled(not busy and self._last_workbook is not None)
        self.open_client_workbook_button.setEnabled(
            not busy and self._last_client_workbook is not None
        )
        self.open_button.setEnabled(not busy and self._last_folder is not None)
        self.saved_study_button.setEnabled(not busy)
        self.auto_saved_button.setEnabled(not busy)
        self.study_button.setEnabled(not busy and self._last_folder is not None)
        self.cancel_button.setVisible(self._worker is not None and self._operation != "disconnect")
        self.cancel_button.setEnabled(self._worker is not None and not self._cancelling)
        self._metric_controls()

    def cancel(self) -> None:
        if self._worker is not None and self._operation != "disconnect":
            self._cancelling = True
            self._worker.request_stop()
            self.status.setText("Stopping safely; completed files will be kept…")
            self._update_controls()

    def _open_folder(self) -> None:
        if (
            self._last_folder is not None
            and not self.is_busy
            and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_folder)))
        ):
            self.status.setText(f"Open this folder in File Explorer: {self._last_folder}")

    def _open_file(self, path: Path | None, label_name: str) -> None:
        if path is None or self.is_busy:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.status.setText(f"Open this {label_name} from the collection folder: {path.name}")

    def _rebuild_automatic_saved(self) -> None:
        if self.is_busy:
            return
        start = str(self._last_folder or Path(self.destination.text()))
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose a saved direct-API cow collection", start
        )
        if not chosen:
            return
        folder = Path(chosen)
        self._start(
            "auto_saved",
            lambda stop, progress: AutomaticStudyWorkbookService().create(folder, stop, progress),
            "Checking the saved collection and rebuilding client analysis…",
        )

    def _open_study(self, folder: Path | None) -> None:
        if self.is_busy:
            return
        from smaxtec.ui.study_dialog import StudyWorkbookDialog

        dialog = StudyWorkbookDialog(folder, self)
        dialog.exec()
        dialog.deleteLater()
