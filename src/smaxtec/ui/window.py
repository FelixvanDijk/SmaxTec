"""Desktop connection and export-request workspace."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from smaxtec import __version__
from smaxtec.application.exports import (
    ExportBatchResult,
    ExportError,
    ExportProgress,
    ExportRequest,
    ExportStage,
    Farm,
)
from smaxtec.application.login import (
    Credentials,
    LoginError,
    LoginProgress,
    LoginSession,
    LoginStage,
)
from smaxtec.ui.cow_editor import CowRequestsEditor
from smaxtec.ui.export_review import ExportReviewDialog
from smaxtec.ui.widgets import label
from smaxtec.ui.worker import SessionWorker


class MainWindow(QMainWindow):
    def __init__(self, session_factory: Callable[[], LoginSession]) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._worker: SessionWorker | None = None
        self._closing = False
        self._failed = False
        self._connected = False
        self._farms_ready = False
        self._export_busy = False
        self._stopping = False
        self.setWindowTitle("SmaxTec Workbench")
        self.resize(1220, 940)
        self.setMinimumSize(1020, 700)

        root = QWidget()
        root.setObjectName("root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("content")
        body = QVBoxLayout(content)
        body.setContentsMargins(32, 28, 32, 24)
        body.setSpacing(18)

        top = QHBoxLayout()
        top.addWidget(label("WORKSPACE  /  DATA REQUEST", "eyebrow"))
        top.addStretch()
        top.addWidget(label("MILESTONE 2", "badge", wrap=False))
        body.addLayout(top)
        body.addSpacing(8)
        body.addWidget(label("Choose the herd data you need.", "heading"))
        body.addWidget(
            label(
                "Connect your account, choose a farm, and request measured data "
                "with a date range tailored to each cow.",
                "intro",
            )
        )
        body.addWidget(self._connection_card())
        body.addWidget(self._request_card())
        body.addWidget(self._status_card())
        body.addStretch()
        body.addWidget(
            label(
                "Each cow creates one smaXtec export request. Email collection and "
                "workbook processing are the next milestone.",
                "footnote",
            )
        )
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.setCentralWidget(root)
        self.username.setFocus()

    def _sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(238)
        column = QVBoxLayout(side)
        column.setContentsMargins(26, 32, 26, 28)
        column.setSpacing(18)
        column.addWidget(label("S /", "monogram"))
        column.addWidget(label("SmaxTec\nWorkbench", "brand"))
        column.addSpacing(24)
        column.addWidget(label("FROM HERD DATA\nTO A CLEARER VIEW.", "sideCaption"))
        column.addSpacing(12)
        self.connect_step = label("01   Connect account", "activeStep")
        self.select_step = label("02   Select herd & cows", "futureStep")
        column.addWidget(self.connect_step)
        column.addWidget(self.select_step)
        column.addWidget(label("03   Collect email data", "futureStep"))
        column.addWidget(label("04   Explore & report", "futureStep"))
        column.addStretch()
        column.addWidget(label("One workspace.\nEvery cow in context.", "sideNote"))
        column.addWidget(label(f"DESKTOP PREVIEW   /   {__version__}", "sideVersion"))
        return side

    def _connection_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        form = QVBoxLayout(card)
        form.setContentsMargins(28, 22, 28, 24)
        form.setSpacing(9)
        form.addWidget(label("1. Connect your smaXtec account", "cardTitle"))
        self.connection_fields = QWidget()
        inputs = QVBoxLayout(self.connection_fields)
        inputs.setContentsMargins(0, 0, 0, 0)
        inputs.setSpacing(9)
        form.addWidget(self.connection_fields)

        self.username = QLineEdit()
        self.username.setObjectName("username")
        self.username.setPlaceholderText("you@example.com")
        self.username.setAccessibleName("Email address")
        email_label = label("Email address", "fieldLabel")
        email_label.setBuddy(self.username)
        inputs.addWidget(email_label)
        inputs.addWidget(self.username)

        self.password = QLineEdit()
        self.password.setObjectName("password")
        self.password.setPlaceholderText("Enter your password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setAccessibleName("Password")
        self.password.returnPressed.connect(self._start)
        password_label = label("Password", "fieldLabel")
        password_label.setBuddy(self.password)
        inputs.addWidget(password_label)
        inputs.addWidget(self.password)

        self.show_password = QCheckBox("Show password")
        self.show_password.toggled.connect(
            lambda checked: self.password.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        inputs.addWidget(self.show_password)
        self.connect_button = QPushButton("Connect to smaXtec  →")
        self.connect_button.setObjectName("primary")
        self.connect_button.setMinimumHeight(46)
        self.connect_button.clicked.connect(self._start)
        self.stop_button = QPushButton("Cancel")
        self.stop_button.setObjectName("secondary")
        self.stop_button.setMinimumHeight(46)
        self.stop_button.clicked.connect(self._stop)
        self.stop_button.hide()
        buttons = QHBoxLayout()
        buttons.addWidget(self.connect_button, 1)
        buttons.addWidget(self.stop_button)
        form.addLayout(buttons)
        form.addWidget(
            label(
                "Your password is used for this session only and is never saved by Workbench.",
                "privacy",
            )
        )
        return card

    def _request_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        form = QVBoxLayout(card)
        form.setContentsMargins(28, 22, 28, 24)
        form.setSpacing(10)
        form.addWidget(label("2. Select farm, cows and dates", "cardTitle"))
        form.addWidget(
            label("Farms refresh automatically after every successful sign-in.", "muted")
        )

        farm_label = label("Farm", "fieldLabel")
        self.farm = QComboBox()
        self.farm.setObjectName("farm")
        self.farm.setAccessibleName("Farm")
        self.farm.addItem("Connect to load farms")
        self.farm.setEnabled(False)
        farm_label.setBuddy(self.farm)
        form.addWidget(farm_label)
        form.addWidget(self.farm)

        self.cow_editor = CowRequestsEditor()
        form.addWidget(self.cow_editor)
        self.request_button = QPushButton("Review and request exports  →")
        self.request_button.setObjectName("primary")
        self.request_button.setMinimumHeight(48)
        self.request_button.setEnabled(False)
        self.request_button.clicked.connect(self._request_exports)
        form.addWidget(self.request_button)
        self.cow_editor.changed.connect(self._update_request_enabled)
        self.farm.currentIndexChanged.connect(self._update_request_enabled)
        return card

    def _status_card(self) -> QWidget:
        self.status_card = QFrame()
        self.status_card.setObjectName("statusCard")
        status = QVBoxLayout(self.status_card)
        status.setContentsMargins(22, 18, 22, 18)
        status.setSpacing(8)
        self.status_title = label("Ready when you are", "statusTitle")
        self.status_message = label(
            "Enter your choices at any time, then connect your account.", "muted"
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        status.addWidget(self.status_title)
        status.addWidget(self.status_message)
        status.addWidget(self.progress_bar)
        return self.status_card

    def _status(self, title: str, message: str, tone: str = "neutral") -> None:
        self.status_title.setText(title)
        self.status_message.setText(message)
        self.status_card.setProperty("tone", tone)
        self.status_card.style().unpolish(self.status_card)
        self.status_card.style().polish(self.status_card)

    def _set_step(self, connected: bool) -> None:
        self.connect_step.setObjectName("futureStep" if connected else "activeStep")
        self.select_step.setObjectName("activeStep" if connected else "futureStep")
        for widget in (self.connect_step, self.select_step):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _start(self) -> None:
        if self._worker is not None:
            return
        try:
            credentials = Credentials(self.username.text(), self.password.text())
        except ValueError as error:
            self._status("Add your sign-in details", str(error), "error")
            return
        self._failed = self._connected = self._farms_ready = self._stopping = False
        self.show_password.setChecked(False)
        self.password.clear()
        for widget in (self.username, self.password, self.show_password, self.connect_button):
            widget.setEnabled(False)
        self.farm.setEnabled(False)
        self.request_button.setEnabled(False)
        self.connect_button.setText("Connecting…")
        self.stop_button.setText("Cancel")
        self.stop_button.setEnabled(True)
        self.stop_button.show()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self._status("Connecting to smaXtec", "Opening a secure sign-in session…")
        self._worker = SessionWorker(self._session_factory, credentials)
        self._worker.login_progress.connect(self._on_login_progress)
        self._worker.farms_discovered.connect(self._on_farms)
        self._worker.export_progress.connect(self._on_export_progress)
        self._worker.export_completed.connect(self._on_export_complete)
        self._worker.connection_failed.connect(self._on_connection_error)
        self._worker.export_failed.connect(self._on_export_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_login_progress(self, progress: LoginProgress) -> None:
        if self._stopping:
            return
        if progress.stage == LoginStage.CONNECTED:
            self._connected = True
        title = "Connected" if progress.stage == LoginStage.CONNECTED else "Connecting to smaXtec"
        if progress.stage == LoginStage.ACTION_REQUIRED:
            title = "Finish signing in in the browser"
        self._status(title, progress.message, "success" if self._connected else "neutral")
        if self._connected:
            self.connection_fields.hide()
            self.connect_button.setText("Account connected")
            self.stop_button.setText("Disconnect")
            self._set_step(True)

    def _on_farms(self, farms: tuple[Farm, ...]) -> None:
        self._farms_ready = True
        selected = self.farm.currentData()
        selected_name = selected.name if isinstance(selected, Farm) else None
        self.farm.clear()
        for item in farms:
            self.farm.addItem(item.name, item)
        if selected_name:
            selected_index = self.farm.findText(selected_name, Qt.MatchFlag.MatchExactly)
            if selected_index >= 0:
                self.farm.setCurrentIndex(selected_index)
        self.farm.setEnabled(not self._export_busy)
        if self._export_busy:
            return
        self.progress_bar.hide()
        self._status(
            "Ready to request data",
            f"Loaded {len(farms)} farm{'s' if len(farms) != 1 else ''}. Review your choices below.",
            "success",
        )
        self._update_request_enabled()

    def _on_export_progress(self, progress: ExportProgress) -> None:
        if self._stopping:
            return
        if progress.total:
            self.progress_bar.setRange(0, progress.total)
            self.progress_bar.setValue(
                progress.current
                if progress.stage == ExportStage.COW_COMPLETE
                else max(0, progress.current - 1)
            )
        else:
            self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        title = "Preparing your farms"
        if progress.stage == ExportStage.RECONNECTING:
            title = "Reconnecting securely"
        if progress.stage in {
            ExportStage.OPENING_FARM,
            ExportStage.FINDING_COW,
            ExportStage.REQUESTING_EXPORT,
            ExportStage.COW_COMPLETE,
        }:
            title = "Requesting measured data"
        self._status(title, progress.message)

    def _make_request(self) -> ExportRequest:
        farm = self.farm.currentData()
        if not isinstance(farm, Farm):
            raise ValueError("Connect your account and select a farm.")
        return ExportRequest(farm, self.cow_editor.entries())

    def _request_exports(self) -> None:
        if self._worker is None or self._export_busy:
            return
        try:
            request = self._make_request()
        except ValueError as error:
            self._status("Check your request", str(error), "error")
            return
        if not self._review_request(request) or self._worker is None or self._stopping:
            return
        self._export_busy = True
        self._set_request_fields_enabled(False)
        self._update_request_enabled()
        self.request_button.setText("Requesting exports…")
        self.progress_bar.setRange(0, len(request.entries))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self._worker.submit_exports(request)

    def _review_request(self, request: ExportRequest) -> bool:
        dialog = ExportReviewDialog(request, self)
        try:
            return dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            dialog.deleteLater()

    def _on_export_complete(self, result: ExportBatchResult) -> None:
        self._export_busy = False
        self._set_request_fields_enabled(True)
        self.request_button.setText("Review and request exports  →")
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_bar.hide()
        requested = len(result.requested)
        skipped = len(result.skipped_as_already_attempted)
        message = f"Requested {requested} measured-data export{'s' if requested != 1 else ''}."
        if skipped:
            message += f" Skipped {skipped} already attempted in this session."
        message += " A fresh browser will open automatically for your next request."
        self._status("Export requests sent", message, "success")
        self._update_request_enabled()

    def _on_export_error(self, error: ExportError) -> None:
        self._export_busy = False
        self._set_request_fields_enabled(True)
        self.request_button.setText("Review and request exports  →")
        self.progress_bar.hide()
        prefix = f"{len(error.completed)} request(s) completed. " if error.completed else ""
        self._status(
            "Export request needs attention",
            prefix + str(error) + " A fresh browser will be used for your next request.",
            "error",
        )
        self._update_request_enabled()

    def _on_connection_error(self, error: LoginError | ExportError) -> None:
        self._failed = True
        self.progress_bar.hide()
        self._status("Connection needs attention", str(error), "error")

    def _set_request_fields_enabled(self, enabled: bool) -> None:
        self.farm.setEnabled(enabled and self._farms_ready)
        self.cow_editor.setEnabled(enabled)

    def _update_request_enabled(self) -> None:
        valid = False
        if self._connected and self._farms_ready and not self._export_busy and not self._stopping:
            try:
                self._make_request()
                valid = True
            except ValueError:
                pass
        self.request_button.setEnabled(valid)

    def _stop(self) -> None:
        if self._worker is not None:
            self._stopping = True
            self.stop_button.setEnabled(False)
            self.request_button.setEnabled(False)
            self._status(
                "Closing the connection", "Finishing the current step and closing the browser…"
            )
            self._worker.request_stop()

    def _on_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self.progress_bar.hide()
        self.stop_button.hide()
        self.connect_button.setText("Connect to smaXtec  →")
        self.connection_fields.show()
        for widget in (self.username, self.password, self.show_password, self.connect_button):
            widget.setEnabled(True)
        self._connected = self._farms_ready = self._export_busy = False
        self.farm.clear()
        self.farm.addItem("Connect to load farms")
        self.farm.setEnabled(False)
        self._set_request_fields_enabled(True)
        self.request_button.setText("Review and request exports  →")
        self.request_button.setEnabled(False)
        self._set_step(False)
        if not self._failed:
            self._status("Connection closed", "Enter your password to start a new session.")
        if self._closing:
            self.close()
        else:
            self.password.setFocus()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None:
            self._closing = True
            self._stop()
            event.ignore()
        else:
            event.accept()
