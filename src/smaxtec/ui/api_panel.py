"""Direct-data workspace: discovery, individual periods and immutable review.

All HTTP and file operations run in a serialized, cancellable worker. Tables carry
the original entity value, so display names, sorting and farm changes cannot change
which animal owns a date range.
"""

import re
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from threading import Event
from typing import Protocol

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
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
        self.resize(1000, 640)
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
        self.table = QTableWidget(len(request.targets), 7)
        self.table.setAccessibleName("All reviewed API targets and individual dates")
        self.table.setHorizontalHeaderLabels(
            ["Farm", "Type", "Target", "From", "To", "Timezone", "Measurements"]
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
                target.entity.farm.timezone,
                ", ".join(target.metrics) or "All available for this target",
            )
            for column, value in enumerate(values):
                cell = _item(value)
                cell.setToolTip(_text(value))
                self.table.setItem(row, column, cell)
        layout.addWidget(self.table, 1)
        formats = "Raw JSON + CSV" + (" + Excel" if request.excel else "")
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
        self._metrics_entity: ApiEntity | None = None
        self._last_folder: Path | None = None
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
        account = QGridLayout(self.account)
        account.setContentsMargins(18, 12, 18, 12)
        self.account_status = label("Connect your smaXtec account", "statusTitle")
        account.addWidget(self.account_status, 0, 0, 1, 4)
        self.username = QLineEdit()
        self.username.setPlaceholderText("smaXtec email address")
        self.username.setAccessibleName("API smaXtec email address")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("smaXtec password")
        self.password.setAccessibleName("API smaXtec password")
        self.connect_button = self._button("Connect", self._connect, primary=True)
        self.disconnect_button = self._button("Disconnect", self.disconnect)
        account.addWidget(self.username, 1, 0)
        account.addWidget(self.password, 1, 1)
        account.addWidget(self.connect_button, 1, 2)
        account.addWidget(self.disconnect_button, 1, 3)
        account.setColumnStretch(0, 1)
        account.setColumnStretch(1, 1)
        account.addWidget(
            label("Credentials and API session stay in memory until you disconnect.", "privacy"),
            2,
            0,
            1,
            4,
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
        page_layout = page.layout()
        if page_layout is not None:
            page_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
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
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(150)
        return table

    def _build_browse(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(10)
        filters = QHBoxLayout()
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
        filters.addWidget(self.farm, 3)
        filters.addWidget(self.kind, 2)
        filters.addWidget(self.archived)
        layout.addLayout(filters)
        self.inventory_note = label("Your connected farms will appear here.", "muted")
        layout.addWidget(self.inventory_note)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by number, name, ear tag or group…")
        self.search.setAccessibleName("Filter API inventory")
        self.search.textChanged.connect(self._filter_inventory)
        layout.addWidget(self.search)
        self.inventory = self._table(
            ["Number / serial", "Name", "Ear tag", "Group", "Status"], "API farm inventory"
        )
        self.inventory.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inventory.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.inventory, 1)
        selection = QHBoxLayout()
        self.select_shown_button = self._button("Select shown", self._select_shown)
        self.clear_selection_button = self._button("Clear selection", self.inventory.clearSelection)
        self.selection_note = label("0 selected", "muted")
        selection.addWidget(self.select_shown_button)
        selection.addWidget(self.clear_selection_button)
        selection.addWidget(self.selection_note, 1)
        self.load_metrics_button = self._button("Explore measurements", self._load_metrics)
        selection.addWidget(self.load_metrics_button)
        layout.addLayout(selection)
        exact = QHBoxLayout()
        self.cow_numbers = QLineEdit()
        self.cow_numbers.setPlaceholderText("Exact cow numbers, e.g. 57, 203, 657")
        self.cow_numbers.setAccessibleName("Exact API cow numbers")
        self.exact_button = self._button("Select cow numbers", self._select_exact)
        exact.addWidget(self.cow_numbers, 1)
        exact.addWidget(self.exact_button)
        layout.addLayout(exact)
        dates = QHBoxLayout()
        dates.addWidget(label("From", "fieldLabel", wrap=False))
        self.shared_from = date_entry(date.today() - timedelta(days=7), "API shared From date")
        dates.addWidget(self.shared_from)
        dates.addWidget(label("To", "fieldLabel", wrap=False))
        self.shared_to = date_entry(date.today(), "API shared To date")
        dates.addWidget(self.shared_to)
        self.add_button = self._button("Add selected to queue", self._add_selected, primary=True)
        dates.addWidget(self.add_button, 1)
        layout.addLayout(dates)
        layout.addWidget(
            label(
                "Dates use DD/MM/YYYY and the farm's timezone. Each queued target keeps its "
                "own dates. Add another period for the same cow whenever needed.",
                "privacy",
            )
        )
        return page

    def _build_queue(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(10)
        self.queue_note = label(
            "Add cows, groups or devices from Browse herd. Double-click any date to edit it.",
            "muted",
        )
        layout.addWidget(self.queue_note)
        self.queue = self._table(
            ["Farm", "Type", "Target", "From · DD/MM/YYYY", "To · DD/MM/YYYY", "Measurements"],
            "API download queue with individual dates",
        )
        self.queue.setItemDelegateForColumn(3, _DateDelegate(self.queue))
        self.queue.setItemDelegateForColumn(4, _DateDelegate(self.queue))
        self.queue.itemChanged.connect(self._queue_changed)
        layout.addWidget(self.queue, 1)
        queue_actions = QHBoxLayout()
        queue_actions.setSpacing(10)
        self.remove_button = self._button("Remove selected", self._remove_selected)
        self.clear_queue_button = self._button("Clear queue", self._clear_queue)
        self.apply_dates_button = self._button("Apply Browse dates to all", self._apply_dates)
        queue_actions.addWidget(self.remove_button)
        queue_actions.addWidget(self.clear_queue_button)
        queue_actions.addStretch()
        queue_actions.addWidget(self.apply_dates_button)
        layout.addLayout(queue_actions)
        options = QHBoxLayout()
        options.setSpacing(12)
        measurements = QFrame()
        measurements.setObjectName("card")
        metric_layout = QVBoxLayout(measurements)
        metric_layout.setContentsMargins(16, 14, 16, 14)
        metric_layout.setSpacing(8)
        metric_layout.addWidget(label("Measurements", "statusTitle"))
        self.all_metrics = QCheckBox("All available measurements for each target")
        self.all_metrics.setChecked(True)
        self.all_metrics.toggled.connect(self._metric_controls)
        metric_layout.addWidget(self.all_metrics)
        self.metric_note = label(
            "Select one item in Browse herd, then Explore measurements to choose specific data.",
            "privacy",
        )
        metric_layout.addWidget(self.metric_note)
        self.metrics = QListWidget()
        self.metrics.setAccessibleName("Available API measurement codes and units")
        self.metrics.setFixedHeight(105)
        metric_layout.addWidget(self.metrics)
        self.apply_metrics_button = self._button("Apply measurements to queue", self._apply_metrics)
        metric_layout.addWidget(self.apply_metrics_button)
        options.addWidget(measurements, 1)
        extras = QFrame()
        extras.setObjectName("card")
        extra_layout = QVBoxLayout(extras)
        extra_layout.setContentsMargins(16, 14, 16, 14)
        extra_layout.setSpacing(8)
        extra_layout.addWidget(label("Resolution & farm datasets", "statusTitle"))
        self.resolution = QComboBox()
        self.resolution.setAccessibleName("API measurement resolution")
        for name, value in (
            ("Native · original resolution", "native"),
            ("10-minute aggregation", "10minutes"),
            ("Hourly aggregation", "hourly"),
            ("Daily aggregation", "daily"),
        ):
            self.resolution.addItem(name, value)
        extra_layout.addWidget(self.resolution)
        self.health_index = QCheckBox("Include farm health index")
        extra_layout.addWidget(self.health_index)
        extra_layout.addWidget(label(EXTRAS_NOTE, "privacy"))
        extra_layout.addStretch()
        options.addWidget(extras, 1)
        layout.addLayout(options)
        destination_row = QHBoxLayout()
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
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(self.browse_button)
        layout.addLayout(destination_row)
        save_row = QHBoxLayout()
        self.collection_name = QLineEdit("Herd data")
        self.collection_name.setAccessibleName("API collection name")
        self.collection_name.setPlaceholderText("Collection name")
        self.collection_name.setMaxLength(80)
        self.excel = QCheckBox("Also create Excel workbook")
        self.excel.setChecked(True)
        self.download_button = self._button(
            "Review & download", self._review_download, primary=True
        )
        save_row.addWidget(self.collection_name, 1)
        save_row.addWidget(self.excel)
        save_row.addWidget(self.download_button)
        layout.addLayout(save_row)
        layout.addWidget(
            label(
                "Every collection includes original JSON, CSV measurements and a "
                "provenance manifest. "
                "Choose a name above; a unique folder prevents overwriting earlier work.",
                "privacy",
            )
        )
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
        self.results = self._table(
            ["Farm", "Target", "From", "To", "Status", "Rows", "Details"],
            "API collection results by target and date range",
        )
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.results, 1)
        self.open_button = self._button("Open collection folder", self._open_folder)
        layout.addWidget(self.open_button)
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
        self._metrics_entity = None
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
        self.metric_note.setText("Explore a target's available measurements after connecting.")
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
        self._reset_measurements()
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
            numbers = parse_cow_numbers(self.cow_numbers.text())
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
        self._metrics_entity = None
        self.metrics.clear()
        self.all_metrics.setChecked(True)
        self.metric_note.setText(
            "Select one target and Explore measurements to choose specific data."
        )

    def _load_metrics(self) -> None:
        selected = self._selected_entities()
        if self.is_busy or len(selected) != 1:
            return
        entity = selected[0]
        client = self._client
        assert client is not None
        self._metrics_entity = entity
        self._start(
            "metrics",
            lambda stop, _progress: client.metrics(entity, stop),
            "Discovering measurement codes and units for this target…",
        )

    def _chosen_metrics(self) -> tuple[str, ...]:
        if self.all_metrics.isChecked():
            return ()
        codes = tuple(
            self.metrics.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.metrics.count())
            if self.metrics.item(index).checkState() == Qt.CheckState.Checked
        )
        if not codes:
            raise ValueError("Choose at least one measurement, or use All available measurements.")
        return codes

    def _metric_controls(self) -> None:
        self.metrics.setEnabled(not self.all_metrics.isChecked() and not self.is_busy)

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
            metrics = self._chosen_metrics()
            targets = tuple(ApiTarget(entity, start, end, metrics) for entity in selected)
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
                ", ".join(target.metrics) or "All available",
            )
            for column, value in enumerate(values):
                cell = _item(value, editable=column in (3, 4))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, target.entity)
                if column == 5:
                    cell.setData(Qt.ItemDataRole.UserRole, target.metrics)
                self.queue.setItem(row, column, cell)
        self._queue_changed()
        self.status.setText(
            f"Added {len(targets):,} targets. Open Download queue to edit individual "
            "dates or review."
        )

    def _queue_changed(self) -> None:
        count = self.queue.rowCount()
        self.steps.setTabText(1, f"2  Download queue ({count:,})")
        self.queue_note.setText(
            f"{count:,} queued targets. Double-click a From or To date to edit that target only. "
            "You can keep adding targets from other farms."
            if count
            else "Add cows, groups or devices from Browse herd. Each target keeps its own dates."
        )
        self._update_controls()

    def _clear_queue(self) -> None:
        self.queue.setRowCount(0)
        self._queue_changed()

    def _remove_selected(self) -> None:
        for index in sorted(
            self.queue.selectionModel().selectedRows(), key=lambda i: i.row(), reverse=True
        ):
            self.queue.removeRow(index.row())
        self._queue_changed()

    def _apply_dates(self) -> None:
        try:
            start, end = self._shared_dates()
            # Validate every farm before mutating even one row.
            for row in range(self.queue.rowCount()):
                ApiTarget(self.queue.item(row, 0).data(Qt.ItemDataRole.UserRole), start, end)
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
        try:
            metrics = self._chosen_metrics()
        except ValueError as error:
            self.status.setText(str(error))
            return
        for row in range(self.queue.rowCount()):
            cell = self.queue.item(row, 5)
            cell.setText(", ".join(metrics) or "All available")
            cell.setData(Qt.ItemDataRole.UserRole, metrics)
        self.status.setText(
            "Measurements applied to every queued target; availability is checked per target."
        )

    def build_request(self) -> ApiDownloadRequest:
        """Read every row once, including off-screen rows; keep identities with dates."""
        targets: list[ApiTarget] = []
        for row in range(self.queue.rowCount()):
            try:
                target = ApiTarget(
                    entity=self.queue.item(row, 0).data(Qt.ItemDataRole.UserRole),
                    start_date=parse_user_date(self.queue.item(row, 3).text(), "From date"),
                    end_date=parse_user_date(self.queue.item(row, 4).text(), "To date"),
                    metrics=self.queue.item(row, 5).data(Qt.ItemDataRole.UserRole),
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
        elif self._operation == "metrics" and isinstance(result, tuple):
            self.metrics.clear()
            for metric in result:
                if isinstance(metric, ApiMetric):
                    suffix = " · " + ", ".join(metric.units) if metric.units else ""
                    item = QListWidgetItem(_text(metric.code + suffix))
                    item.setData(Qt.ItemDataRole.UserRole, metric.code)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                    self.metrics.addItem(item)
            name = (
                self._metrics_entity.label
                if self._metrics_entity is not None
                else "selected target"
            )
            self.metric_note.setText(
                f"{self.metrics.count()} measurements available for {_text(name)}. "
                "Other targets are checked individually during download."
            )
            self.steps.setCurrentIndex(1)
            self.status.setText(
                "Measurements discovered. Use All available or choose specific codes below."
            )
        elif isinstance(result, ApiDownloadResult):
            self._show_result(result)
        elif self._operation == "disconnect":
            self.status.setText("Disconnected. Credentials and API session were released.")

    def _show_result(self, result: ApiDownloadResult) -> None:
        self._last_folder = result.folder
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
            f"{saved:,} of {len(result.files):,} targets saved. Check each status below.\n"
            + "\n".join(_text(warning) for warning in result.warnings)
        )
        self.status.setText(
            f"{prefix}. Open your collection folder to inspect the data and manifest."
        )

    def _on_failure(self, error: ApiError) -> None:
        self.status.setText(_text(str(error)))
        if self._operation == "download":
            self.result_summary.setText("Collection needs attention")
            self.result_note.setText(_text(str(error)))

    def _on_cancelled(self) -> None:
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
        if operation != "disconnect" and (
            self._shutting_down or (operation == "connect" and not self._connected)
        ):
            self.disconnect()
            if self._worker is not None:
                return
        self._update_controls()
        self.idle.emit()

    def _update_controls(self) -> None:
        busy = self.is_busy or self._shutting_down
        self.account.setEnabled(not busy)
        self.username.setEnabled(not busy and not self._connected)
        self.password.setEnabled(not busy and not self._connected)
        self.connect_button.setEnabled(not busy and not self._connected)
        self.disconnect_button.setEnabled(not busy and self._connected)
        self.browse_page.setEnabled(not busy and self._connected)
        self.queue_page.setEnabled(not busy and self._connected)
        self.farm.setEnabled(not busy and self._connected)
        self.add_button.setEnabled(not busy and bool(self._selected_entities()))
        self.load_metrics_button.setEnabled(not busy and len(self._selected_entities()) == 1)
        self.exact_button.setEnabled(not busy and self._catalog is not None)
        self.download_button.setEnabled(not busy and self._connected and self.queue.rowCount() > 0)
        self.apply_dates_button.setEnabled(not busy and self.queue.rowCount() > 0)
        self.apply_metrics_button.setEnabled(not busy and self.queue.rowCount() > 0)
        self.open_button.setEnabled(not busy and self._last_folder is not None)
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
