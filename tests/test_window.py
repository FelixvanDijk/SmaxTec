from threading import get_ident

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit

from smaxtec.application.login import FailureCode, LoginError, LoginProgress, LoginStage
from smaxtec.ui.window import MainWindow


class FakeSession:
    def __init__(self, error=None):
        self.error = error
        self.closed = False
        self.thread_ids = []

    def connect(self, credentials, progress, stop):
        self.thread_ids.append(get_ident())
        if self.error:
            raise self.error
        progress(LoginProgress(LoginStage.CONNECTED, "Connected to the synthetic test account."))

    def keep_open(self, stop):
        self.thread_ids.append(get_ident())
        stop.wait(timeout=5)

    def close(self):
        self.thread_ids.append(get_ident())
        self.closed = True


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
