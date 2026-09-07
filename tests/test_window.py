from threading import get_ident

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit, QMessageBox

from smaxtec.application.exports import (
    ExportBatchResult,
    ExportProgress,
    ExportStage,
    Farm,
)
from smaxtec.application.login import FailureCode, LoginError, LoginProgress, LoginStage
from smaxtec.ui.window import MainWindow


class FakeSession:
    def __init__(self, error=None):
        self.error = error
        self.closed = False
        self.thread_ids = []
        self.requests = []
        self.credentials_seen = []

    def connect(self, credentials, progress, stop):
        self.thread_ids.append(get_ident())
        self.credentials_seen.append((credentials.username, credentials.password))
        if self.error:
            raise self.error
        progress(LoginProgress(LoginStage.CONNECTED, "Connected to the synthetic test account."))

    def discover_farms(self, progress, stop):
        self.thread_ids.append(get_ident())
        progress(ExportProgress(ExportStage.FARMS_READY, "Farms loaded."))
        return (Farm("Maes Gwyrdd LTD"), Farm("TYB Farms LTD"))

    def request_exports(self, request, progress, stop):
        self.thread_ids.append(get_ident())
        self.requests.append(request)
        progress(
            ExportProgress(
                ExportStage.COW_COMPLETE,
                "Export requested.",
                len(request.cow_numbers),
                len(request.cow_numbers),
            )
        )
        return ExportBatchResult(request.cow_numbers)

    def is_open(self):
        return not self.closed

    def close(self):
        self.thread_ids.append(get_ident())
        self.closed = True


class FakeSessionFactory:
    def __init__(self):
        self.sessions = []

    def __call__(self):
        session = FakeSession()
        self.sessions.append(session)
        return session


def fill(window):
    window.username.setText("analyst@example.test")
    window.password.setText("synthetic-password")


def test_fields_are_required_and_password_is_masked(qtbot):
    window = MainWindow(FakeSession)
    qtbot.addWidget(window)
    assert window.password.echoMode() == QLineEdit.EchoMode.Password
    window._start()
    assert window._worker is None
    assert window.status_title.text() == "Add your sign-in details"


def test_connect_is_responsive_and_disconnect_cleans_worker(qtbot):
    session = FakeSession()
    window = MainWindow(lambda: session)
    qtbot.addWidget(window)
    fill(window)
    window._start()
    assert window.password.text() == ""
    assert not window.connect_button.isEnabled()
    qtbot.waitUntil(lambda: window._connected)
    qtbot.waitUntil(lambda: window._farms_ready)
    heartbeat = []
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat))
    assert window.stop_button.text() == "Disconnect"
    window._stop()
    qtbot.waitUntil(lambda: window._worker is None)
    assert session.closed
    assert len(set(session.thread_ids)) == 1
    assert session.thread_ids[0] != get_ident()
    assert window.connect_button.isEnabled()


def test_window_close_waits_for_browser_cleanup(qtbot):
    session = FakeSession()
    window = MainWindow(lambda: session)
    qtbot.addWidget(window)
    window.show()
    fill(window)
    window._start()
    qtbot.waitUntil(lambda: window._connected)
    qtbot.waitUntil(lambda: window._farms_ready)
    window.close()
    qtbot.waitUntil(lambda: window._worker is None)
    assert session.closed
    qtbot.waitUntil(lambda: not window.isVisible())


def test_raw_exception_is_never_shown_and_retry_is_available(qtbot):
    session = FakeSession(RuntimeError("private-password-in-raw-exception"))
    window = MainWindow(lambda: session)
    qtbot.addWidget(window)
    fill(window)
    window._start()
    qtbot.waitUntil(lambda: window._worker is None)
    assert session.closed
    assert "private-password" not in window.status_message.text()
    assert window.connect_button.isEnabled()
    assert window.status_title.text() == "Connection needs attention"


def test_curated_error_survives_worker_cleanup(qtbot):
    session = FakeSession(LoginError(FailureCode.LOGIN_REJECTED, "Check your details."))
    window = MainWindow(lambda: session)
    qtbot.addWidget(window)
    fill(window)
    window._start()
    qtbot.waitUntil(lambda: window._worker is None)
    assert window.status_message.text() == "Check your details."
    assert window.password.text() == ""


def test_user_can_submit_multiple_cows_and_dates_after_farms_load(qtbot, monkeypatch):
    session = FakeSession()
    window = MainWindow(lambda: session)
    qtbot.addWidget(window)
    fill(window)
    window.cows.setPlainText("057, 57\n257")
    window._start()
    qtbot.waitUntil(lambda: window._farms_ready)
    assert [window.farm.itemText(index) for index in range(window.farm.count())] == [
        "Maes Gwyrdd LTD",
        "TYB Farms LTD",
    ]
    assert window.request_button.isEnabled()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    window._request_exports()
    qtbot.waitUntil(lambda: len(session.requests) == 1)
    qtbot.waitUntil(lambda: not window._export_busy)
    assert session.requests[0].cow_numbers == ("057", "57", "257")
    assert window.status_title.text() == "Export requests sent"
    window._stop()
    qtbot.waitUntil(lambda: window._worker is None)


def test_second_batch_reconnects_without_reentering_credentials(qtbot, monkeypatch):
    factory = FakeSessionFactory()
    window = MainWindow(factory)
    qtbot.addWidget(window)
    fill(window)
    window.cows.setPlainText("57")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    window._start()
    qtbot.waitUntil(lambda: window._farms_ready)
    window._request_exports()
    qtbot.waitUntil(lambda: not window._export_busy)
    assert len(factory.sessions) == 1
    assert factory.sessions[0].closed
    assert window.password.text() == ""

    window.farm.setCurrentText("TYB Farms LTD")
    window.cows.setPlainText("12")
    window._request_exports()
    qtbot.waitUntil(lambda: not window._export_busy)
    assert len(factory.sessions) == 2
    assert factory.sessions[1].closed
    assert factory.sessions[1].requests[0].farm == Farm("TYB Farms LTD")
    assert factory.sessions[1].requests[0].cow_numbers == ("12",)
    assert factory.sessions[0].credentials_seen == factory.sessions[1].credentials_seen
    assert factory.sessions[1].credentials_seen == [("analyst@example.test", "synthetic-password")]

    # An identical farm/cow/date target remains protected across fresh browsers.
    window._request_exports()
    qtbot.waitUntil(lambda: not window._export_busy)
    assert len(factory.sessions) == 2
    assert "Skipped 1" in window.status_message.text()

    window._stop()
    qtbot.waitUntil(lambda: window._worker is None)
