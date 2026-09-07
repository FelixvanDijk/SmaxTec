"""The first usable desktop screen: connect an account and show honest progress."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from smaxtec import __version__
from smaxtec.application.login import (
    Credentials,
    LoginError,
    LoginProgress,
    LoginSession,
    LoginStage,
)
from smaxtec.ui.worker import LoginWorker


def label(text: str, name: str, *, wrap: bool = True) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    # Website/user strings must never be interpreted as HTML in the UI.
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


class MainWindow(QMainWindow):
    def __init__(self, session_factory: Callable[[], LoginSession]) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._worker: LoginWorker | None = None
        self._closing = False
        self._failed = False
        self._connected = False
        self._stopping = False
        self.setWindowTitle("SmaxTec Workbench")
        self.resize(1080, 780)
        self.setMinimumSize(860, 620)

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
        body.setContentsMargins(48, 34, 48, 28)
        body.setSpacing(18)

        top = QHBoxLayout()
        top.addWidget(label("WORKSPACE  /  CONNECTION", "eyebrow"))
        top.addStretch()
        top.addWidget(label("EARLY PREVIEW", "badge", wrap=False))
        body.addLayout(top)
        body.addSpacing(10)
        body.addWidget(label("Start with your herd.", "heading"))
        body.addWidget(
            label(
                "Connect your smaXtec account to bring your herd data into one workspace.", "intro"
            )
        )
        body.addWidget(self._connection_card())
        body.addWidget(self._status_card())
        body.addStretch()
        body.addWidget(
            label(
                "This first version connects your account. Farm selection, data collection "
                "and reports will follow.",
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
        column.addWidget(label("01   Connect account", "activeStep"))
        column.addWidget(label("02   Select herd & cows", "futureStep"))
        column.addWidget(label("03   Collect data", "futureStep"))
        column.addWidget(label("04   Explore & report", "futureStep"))
        column.addStretch()
        column.addWidget(label("One workspace.\nEvery cow in context.", "sideNote"))
        column.addWidget(label(f"DESKTOP PREVIEW   /   {__version__}", "sideVersion"))
        return side

    def _connection_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        form = QVBoxLayout(card)
        form.setContentsMargins(28, 24, 28, 26)
        form.setSpacing(10)
        form.addWidget(label("Your smaXtec account", "cardTitle"))
        form.addWidget(label("Use the details you normally use to sign in to smaXtec.", "muted"))
        form.addSpacing(6)

        self.username = QLineEdit()
        self.username.setObjectName("username")
        self.username.setPlaceholderText("you@example.com")
        self.username.setAccessibleName("Email address")
        email_label = label("Email address", "fieldLabel")
        email_label.setBuddy(self.username)
        form.addWidget(email_label)
        form.addWidget(self.username)

        self.password = QLineEdit()
        self.password.setObjectName("password")
        self.password.setPlaceholderText("Enter your password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setAccessibleName("Password")
        self.password.returnPressed.connect(self._start)
        password_label = label("Password", "fieldLabel")
        password_label.setBuddy(self.password)
        form.addWidget(password_label)
        form.addWidget(self.password)

        self.show_password = QCheckBox("Show password")
        self.show_password.toggled.connect(
            lambda checked: self.password.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        form.addWidget(self.show_password)
        form.addSpacing(4)
        self.connect_button = QPushButton("Connect to smaXtec  →")
        self.connect_button.setObjectName("primary")
        self.connect_button.setMinimumHeight(48)
        self.connect_button.clicked.connect(self._start)
        self.stop_button = QPushButton("Cancel")
        self.stop_button.setObjectName("secondary")
        self.stop_button.setMinimumHeight(48)
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

    def _status_card(self) -> QWidget:
        self.status_card = QFrame()
        self.status_card.setObjectName("statusCard")
        status = QVBoxLayout(self.status_card)
        status.setContentsMargins(22, 18, 22, 18)
        status.setSpacing(8)
        self.status_title = label("Ready when you are", "statusTitle")
        self.status_message = label(
            "A separate browser window will open when you connect.", "muted"
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

    def _start(self) -> None:
        if self._worker is not None:
            return
        try:
            credentials = Credentials(self.username.text(), self.password.text())
        except ValueError as error:
            self._status("Add your sign-in details", str(error), "error")
            return
        self._failed = self._connected = self._stopping = False
        self.show_password.setChecked(False)
        self.password.clear()
        for widget in (self.username, self.password, self.show_password, self.connect_button):
            widget.setEnabled(False)
        self.connect_button.setText("Connecting…")
        self.stop_button.setText("Cancel")
        self.stop_button.setEnabled(True)
        self.stop_button.show()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self._status("Connecting to smaXtec", "Opening a secure sign-in session…")
        self._worker = LoginWorker(self._session_factory, credentials)
        self._worker.progress.connect(self._on_progress)
        self._worker.failed.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, progress: LoginProgress) -> None:
        if self._stopping:
            return
        self._connected = progress.stage == LoginStage.CONNECTED
        title = "Connected" if self._connected else "Connecting to smaXtec"
        if progress.stage == LoginStage.ACTION_REQUIRED:
            title = "Finish signing in in the browser"
        self._status(title, progress.message, "success" if self._connected else "neutral")
        if self._connected:
            self.connect_button.setText("Account connected")
            self.stop_button.setText("Disconnect")
            self.progress_bar.hide()

    def _on_error(self, error: LoginError) -> None:
        self._failed = True
        self.progress_bar.hide()
        self._status("Connection needs attention", str(error), "error")

    def _stop(self) -> None:
        if self._worker is not None:
            self._stopping = True
            self.stop_button.setEnabled(False)
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
        for widget in (self.username, self.password, self.show_password, self.connect_button):
            widget.setEnabled(True)
        if not self._failed:
            self._status("Connection closed", "Enter your password to start a new session.")
        self._connected = False
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
