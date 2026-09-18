"""Guided, asynchronous client-study workbook creation from a local collection."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smaxtec.application.api_data import ApiCancelled, ApiError, ApiProgress
from smaxtec.application.study_workbook import (
    StudySettings,
    StudySource,
    StudyWorkbookService,
    parse_event_time,
)


class _StudyWorker(QThread):
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, job: Callable[[Event, Callable[[ApiProgress], None]], object]) -> None:
        super().__init__()
        self._job = job
        self._stop = Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            self.succeeded.emit(self._job(self._stop, self.progress.emit))
        except ApiCancelled:
            self.cancelled.emit()
        except (ApiError, ValueError) as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit(
                "The study workbook could not finish. Source files are unchanged; "
                "try a smaller collection or check the selected folder."
            )


class StudyWorkbookDialog(QDialog):
    """Requires explicit source metric roles and one farm-local time zero per cow."""

    def __init__(self, folder: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create client study workbook")
        self.resize(1060, 740)
        self._folder = folder
        self._source: StudySource | None = None
        self._worker: _StudyWorker | None = None
        self._output: Path | None = None
        self._closing = False
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)
        heading = QLabel("Client study workbook")
        heading.setObjectName("heading")
        root.addWidget(heading)
        intro = QLabel(
            "Turn an existing direct-API collection into one cow-per-row parameters, "
            "aligned cow data and mean/95% confidence views. Original files are untouched."
        )
        intro.setWordWrap(True)
        intro.setObjectName("intro")
        root.addWidget(intro)
        picker = QHBoxLayout()
        self.folder_label = QLabel(str(folder) if folder else "No collection selected")
        self.folder_label.setObjectName("muted")
        self.folder_label.setWordWrap(True)
        picker.addWidget(self.folder_label, 1)
        self.browse_button = QPushButton("Choose saved collection…")
        self.browse_button.setObjectName("secondary")
        self.browse_button.clicked.connect(self._browse)
        picker.addWidget(self.browse_button)
        root.addLayout(picker)

        scroll = QScrollArea()
        scroll.setObjectName("apiPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("apiStepPage")
        content = QVBoxLayout(body)
        content.setContentsMargins(4, 8, 4, 8)
        content.setSpacing(14)
        roles_card = QFrame()
        roles_card.setObjectName("card")
        roles = QGridLayout(roles_card)
        roles.setContentsMargins(16, 14, 16, 14)
        roles.setSpacing(8)
        roles.addWidget(self._label("1  Match source measurements", "cardTitle"), 0, 0, 1, 2)
        self.normal_temp = self._role_combo("Normal temperature (Tn)")
        self.temperature = self._role_combo("Temperature without drinking cycles (T points)")
        self.activity = self._role_combo("Activity (AT points)")
        self.rumination = self._role_combo("Rumination (RT points)")
        for row, (name, combo) in enumerate(
            (
                ("Normal temperature", self.normal_temp),
                ("Temperature without drinking cycles", self.temperature),
                ("Activity", self.activity),
                ("Rumination", self.rumination),
            ),
            1,
        ):
            roles.addWidget(self._label(name, "fieldLabel"), row, 0)
            roles.addWidget(combo, row, 1)
        roles.setColumnStretch(1, 1)
        roles.addWidget(
            self._label(
                "Choose exact source code + unit pairs. No metric is assigned by name guessing; "
                "leave unavailable roles blank rather than substituting another metric.",
                "privacy",
            ),
            5,
            0,
            1,
            2,
        )
        content.addWidget(roles_card)

        event_card = QFrame()
        event_card.setObjectName("card")
        event_layout = QVBoxLayout(event_card)
        event_layout.setContentsMargins(16, 14, 16, 14)
        event_layout.addWidget(self._label("2  Enter time zero for every cow", "cardTitle"))
        event_layout.addWidget(
            self._label(
                "Use the actual administration/key-event time in each cow's farm timezone, "
                "DD/MM/YYYY HH:MM. The download From/To dates are not time zero.",
                "privacy",
            )
        )
        shared_row = QHBoxLayout()
        self.shared_event = QLineEdit()
        self.shared_event.setAccessibleName("Shared farm-local study time zero")
        self.shared_event.setPlaceholderText("DD/MM/YYYY HH:MM · only if every cow shares it")
        shared_row.addWidget(self.shared_event, 1)
        self.apply_event_button = QPushButton("Apply to every cow")
        self.apply_event_button.setObjectName("secondary")
        self.apply_event_button.clicked.connect(self._apply_shared_event)
        shared_row.addWidget(self.apply_event_button)
        event_layout.addLayout(shared_row)
        self.cases = QTableWidget(0, 4)
        self.cases.setAccessibleName("Study cow event times")
        self.cases.setHorizontalHeaderLabels(
            ("Cow", "Farm and timezone", "Downloaded From–To", "Time zero · DD/MM/YYYY HH:MM")
        )
        self.cases.verticalHeader().hide()
        self.cases.setAlternatingRowColors(True)
        self.cases.setMinimumHeight(240)
        self.cases.horizontalHeader().setStretchLastSection(True)
        event_layout.addWidget(self.cases)
        content.addWidget(event_card)

        options_card = QFrame()
        options_card.setObjectName("card")
        options = QGridLayout(options_card)
        options.setContentsMargins(16, 14, 16, 14)
        options.setSpacing(8)
        options.addWidget(self._label("3  Study windows", "cardTitle"), 0, 0, 1, 2)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0, 5)
        self.threshold.setDecimals(2)
        self.threshold.setValue(0.8)
        self.threshold.setSuffix(" °C")
        self.followup = self._spin(1, 60, 20, " days")
        self.temp_step = self._spin(1, 240, 6, " h")
        self.temp_horizon = self._spin(1, 1440, 24, " h")
        self.rum_step = self._spin(1, 240, 24, " h")
        self.rum_horizon = self._spin(1, 1440, 120, " h")
        self.before = self._spin(0, 720, 24, " h")
        self.after = self._spin(1, 1440, 120, " h")
        self.aligned_step = self._spin(1, 240, 6, " h")
        option_items = (
            ("R20 temperature differential", self.threshold),
            ("R20 follow-up", self.followup),
            ("Extra T-point spacing", self.temp_step),
            ("Extra T-point horizon", self.temp_horizon),
            ("Extra RT-point spacing", self.rum_step),
            ("Extra RT-point horizon", self.rum_horizon),
            ("Aligned before T0", self.before),
            ("Aligned after T0", self.after),
            ("Aligned spacing", self.aligned_step),
        )
        for index, (name, widget) in enumerate(option_items):
            row = index + 1
            options.addWidget(self._label(name, "fieldLabel"), row, 0)
            options.addWidget(widget, row, 1)
        options.setColumnStretch(1, 1)
        options.addWidget(
            self._label(
                "T6 always means exactly +6 elapsed hours, even if the download used hourly "
                "or daily aggregation. Missing exact points remain blank with QC counts. "
                "Talert/R20 are clearly labelled proxies. Lact/DIM use available lifecycle; "
                "Rback is recovery to Rn in elapsed days when the requested period contains it.",
                "privacy",
            ),
            10,
            0,
            1,
            2,
        )
        content.addWidget(options_card)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        self.status = self._label("Choose a collection to begin.", "muted")
        root.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        root.addWidget(self.progress)
        actions = QHBoxLayout()
        self.cancel_button = QPushButton("Close")
        self.cancel_button.setObjectName("secondary")
        self.cancel_button.clicked.connect(self._cancel_or_close)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        self.open_button = QPushButton("Open new workbook")
        self.open_button.setObjectName("secondary")
        self.open_button.clicked.connect(self._open_output)
        actions.addWidget(self.open_button)
        self.create_button = QPushButton("Create study workbook")
        self.create_button.setObjectName("primary")
        self.create_button.clicked.connect(self._create)
        actions.addWidget(self.create_button)
        root.addLayout(actions)
        self._controls()
        if folder:
            self._load(folder)

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        result = QLabel(text)
        result.setObjectName(object_name)
        result.setWordWrap(True)
        return result

    @staticmethod
    def _spin(low: int, high: int, value: int, suffix: str) -> QSpinBox:
        result = QSpinBox()
        result.setRange(low, high)
        result.setValue(value)
        result.setSuffix(suffix)
        return result

    @staticmethod
    def _role_combo(name: str) -> QComboBox:
        result = QComboBox()
        result.setAccessibleName(name)
        result.addItem("Not available in this collection (leave fields blank)", None)
        return result

    def _controls(self) -> None:
        busy = self._worker is not None
        self.browse_button.setEnabled(not busy)
        self.create_button.setEnabled(not busy and self._source is not None)
        self.open_button.setEnabled(not busy and self._output is not None)
        self.cancel_button.setText("Stop safely" if busy else "Close")
        self.cases.setEnabled(not busy and self._source is not None)
        self.shared_event.setEnabled(not busy and self._source is not None)
        self.apply_event_button.setEnabled(not busy and self._source is not None)
        for widget in (
            self.normal_temp,
            self.temperature,
            self.activity,
            self.rumination,
            self.threshold,
            self.followup,
            self.temp_step,
            self.temp_horizon,
            self.rum_step,
            self.rum_horizon,
            self.before,
            self.after,
            self.aligned_step,
        ):
            widget.setEnabled(not busy and self._source is not None)

    def _start(self, job, message: str) -> None:
        if self._worker is not None:
            return
        self._worker = _StudyWorker(job)
        self._worker.progress.connect(self._progress)
        self._worker.succeeded.connect(self._success)
        self._worker.failed.connect(self._failure)
        self._worker.cancelled.connect(self._cancelled)
        self._worker.finished.connect(self._finished)
        self.status.setText(message)
        self.progress.setRange(0, 0)
        self.progress.show()
        self._controls()
        self._worker.start()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose direct-API collection", str(self._folder or Path.home())
        )
        if folder:
            self._load(Path(folder))

    def _load(self, folder: Path) -> None:
        self._folder = folder
        self._source = None
        self._output = None
        self.folder_label.setText(str(folder))
        self._controls()
        self._start(lambda stop, _progress: StudySource.load(folder, stop), "Checking collection…")

    def _show_source(self, source: StudySource) -> None:
        self._source = source
        for combo in (self.normal_temp, self.temperature, self.activity, self.rumination):
            combo.clear()
            combo.addItem("Not available in this collection (leave fields blank)", None)
            for code, unit in source.pairs:
                combo.addItem(f"{code} · {unit or 'unit not supplied'}", (code, unit))
        self.cases.setRowCount(len(source.cases))
        for row, case in enumerate(source.cases):
            for column, text in enumerate(
                (
                    case.cow,
                    f"{case.farm} · {case.timezone}",
                    f"{case.from_date} to {case.to_date}",
                    "",
                )
            ):
                item = QTableWidgetItem(text)
                if column != 3:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.cases.setItem(row, column, item)
        self.cases.setColumnWidth(0, 100)
        self.cases.setColumnWidth(1, 250)
        self.cases.setColumnWidth(2, 205)
        self.status.setText(
            f"{len(source.cases):,} cow/case rows · {len(source.pairs):,} source code/unit pairs. "
            "Choose metric roles and enter each time zero."
        )

    def _settings(self) -> StudySettings:
        assert self._source is not None
        choices = tuple(
            combo.currentData()
            for combo in (self.normal_temp, self.temperature, self.activity, self.rumination)
        )
        if all(choice is None for choice in choices):
            raise ValueError("Choose at least one source measurement role to create a workbook.")
        events = []
        for row, case in enumerate(self._source.cases):
            text = self.cases.item(row, 3).text()
            try:
                event = parse_event_time(text, case.timezone)
            except ValueError as error:
                self.cases.selectRow(row)
                self.cases.scrollToItem(self.cases.item(row, 3))
                raise ValueError(f"Cow {case.cow}, row {row + 1}: {error}") from None
            events.append((case.key, event))
        result = StudySettings(
            tuple(events),
            *choices,
            threshold_c=self.threshold.value(),
            followup_days=self.followup.value(),
            temp_step_hours=self.temp_step.value(),
            temp_horizon_hours=self.temp_horizon.value(),
            rum_step_hours=self.rum_step.value(),
            rum_horizon_hours=self.rum_horizon.value(),
            aligned_before_hours=self.before.value(),
            aligned_after_hours=self.after.value(),
            aligned_step_hours=self.aligned_step.value(),
        )
        result.validate(self._source)
        return result

    def _apply_shared_event(self) -> None:
        if self._source is None or self._worker is not None:
            return
        text = self.shared_event.text().strip()
        try:
            for case in self._source.cases:
                parse_event_time(text, case.timezone)
        except ValueError as error:
            self.status.setText(str(error))
            return
        for row in range(self.cases.rowCount()):
            self.cases.item(row, 3).setText(text)
        self.status.setText(
            "The shared time zero was explicitly copied to every cow. "
            "Review each row before creating the workbook."
        )

    def _create(self) -> None:
        if self._source is None or self._worker is not None:
            return
        try:
            settings = self._settings()
        except ValueError as error:
            self.status.setText(str(error))
            return
        source = self._source
        self._output = None
        self._start(
            lambda stop, progress: StudyWorkbookService().create(source, settings, stop, progress),
            "Creating the client study workbook from the reviewed local collection…",
        )

    def _progress(self, value: ApiProgress) -> None:
        self.status.setText(value.message)
        self.progress.setRange(0, value.total)
        self.progress.setValue(value.current)

    def _success(self, value: object) -> None:
        if isinstance(value, StudySource):
            self._show_source(value)
        elif isinstance(value, Path):
            self._output = value
            self.status.setText(
                "Study workbook ready. Review its QC/Definitions before interpreting values."
            )

    def _failure(self, message: str) -> None:
        self.status.setText(message)

    def _cancelled(self) -> None:
        self.status.setText("Stopped safely. The original collection was not changed.")

    def _finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self.progress.hide()
        self._controls()
        if self._closing:
            self.reject()

    def _cancel_or_close(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            self.status.setText("Stopping after the current safe file step…")
        else:
            self.reject()

    def _open_output(self) -> None:
        if self._output and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output))):
            self.status.setText(f"Open {self._output.name} from the collection folder.")

    def reject(self) -> None:
        # Escape must not destroy a running QThread while its collection file is open.
        if self._worker is not None:
            self._closing = True
            self._worker.request_stop()
            self.status.setText("Stopping safely before closing…")
        else:
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None:
            self._closing = True
            self._worker.request_stop()
            event.ignore()
            self.status.setText("Stopping safely before closing…")
        else:
            event.accept()
