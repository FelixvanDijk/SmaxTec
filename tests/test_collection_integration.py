"""Offline desktop composition, coordinated shutdown and helper entrypoint checks."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import Qt

from smaxtec.application.collection import CollectionCancelled, MailCandidate, MailScan
from smaxtec.application.exports import Farm
from smaxtec.application.login import LoginProgress, LoginStage
from smaxtec.ui.collection_panel import CollectionPanel
from smaxtec.ui.window import MainWindow


class SyntheticSession:
    def __init__(self, release: Event | None = None):
        self.release = release
        self.closing = Event()
        self.closed = False

    def connect(self, credentials, progress, stop):
        progress(LoginProgress(LoginStage.CONNECTED, "Synthetic website connected."))

    def discover_farms(self, progress, stop):
        return (Farm("Synthetic farm"),)

    def close(self):
        self.closing.set()
        if self.release is not None:
            assert self.release.wait(5)
        self.closed = True


def test_collection_works_before_any_website_login(qtbot, tmp_path):
    website_calls = []
    imported = []
    selected = MailCandidate(
        "synthetic", "Export ready", "sender@example.test", datetime.now(UTC), "forwarded"
    )

    def importer(paths, stop):
        imported.append(paths)
        return MailScan((selected,), 1)

    panel = CollectionPanel(importer=importer)
    window = MainWindow(lambda: website_calls.append(True), collection_panel=panel)
    qtbot.addWidget(window)
    window.show()
    assert window.username.text() == ""
    assert panel.import_button.isEnabled()
    assert panel.connect_button.isEnabled()
    qtbot.mouseClick(window.collection_jump, Qt.MouseButton.LeftButton)
    panel.import_paths((tmp_path / "synthetic.eml",))
    qtbot.waitUntil(lambda: not panel.is_busy)
    assert imported == [(tmp_path / "synthetic.eml",)]
    assert panel.table.rowCount() == 1
    assert window._worker is None
    assert not website_calls
    window.close()
    assert not window.isVisible()


def test_window_close_waits_for_collection_without_website_session(qtbot, tmp_path):
    started, stopping, release = Event(), Event(), Event()

    def importer(paths, stop):
        started.set()
        assert stop.wait(5)
        stopping.set()
        assert release.wait(5)
        raise CollectionCancelled

    panel = CollectionPanel(importer=importer)
    window = MainWindow(SyntheticSession, collection_panel=panel)
    qtbot.addWidget(window)
    window.show()
    panel.import_paths((tmp_path / "synthetic.eml",))
    try:
        qtbot.waitUntil(started.is_set)
        window.close()
        qtbot.waitUntil(stopping.is_set)
        assert window.isVisible()
        assert not window.centralWidget().isEnabled()
        assert window._closing
    finally:
        release.set()
        qtbot.waitUntil(lambda: not panel.is_busy)
    qtbot.waitUntil(lambda: not window.isVisible())


@pytest.mark.parametrize("first_finished", ["website", "collection"])
def test_window_waits_for_both_workers_regardless_of_finish_order(qtbot, tmp_path, first_finished):
    website_release, collection_release = Event(), Event()
    collection_started, collection_stopping = Event(), Event()
    session = SyntheticSession(website_release)

    def importer(paths, stop):
        collection_started.set()
        assert stop.wait(5)
        collection_stopping.set()
        assert collection_release.wait(5)
        raise CollectionCancelled

    panel = CollectionPanel(importer=importer)
    window = MainWindow(lambda: session, collection_panel=panel)
    qtbot.addWidget(window)
    window.show()
    window.username.setText("analyst@example.test")
    window.password.setText("synthetic-test-password")
    window._start()
    qtbot.waitUntil(lambda: window._farms_ready)
    panel.import_paths((tmp_path / "synthetic.eml",))
    try:
        qtbot.waitUntil(collection_started.is_set)
        window.close()
        qtbot.waitUntil(session.closing.is_set)
        qtbot.waitUntil(collection_stopping.is_set)
        if first_finished == "website":
            website_release.set()
            qtbot.waitUntil(lambda: window._worker is None)
            assert panel.is_busy
        else:
            collection_release.set()
            qtbot.waitUntil(lambda: not panel.is_busy)
            assert window._worker is not None
        assert window.isVisible()  # The other worker still owns resources.
    finally:
        website_release.set()
        collection_release.set()
        qtbot.waitUntil(lambda: window._worker is None and not panel.is_busy)
    qtbot.waitUntil(lambda: not window.isVisible())
    assert session.closed


@pytest.mark.parametrize("windowless", [False, True])
def test_application_helper_entrypoint_roundtrips_private_pipes_without_qt_or_com(windowless):
    executable = Path(sys.executable)
    if windowless:
        if os.name != "nt":
            pytest.skip("pythonw is a Windows entrypoint")
        executable = executable.with_name("pythonw.exe")
        if not executable.is_file():
            pytest.skip("This Python environment has no pythonw executable")
    script = (
        "import sys; from smaxtec.main import main; "
        "sys.argv.append('--outlook-helper'); result = main(); "
        "assert not any(name.startswith('PySide6') for name in sys.modules); "
        "assert 'pythoncom' not in sys.modules; "
        "raise SystemExit(result)"
    )
    completed = subprocess.run(
        [str(executable), "-c", script],
        input='{"action":"invalid-offline-test"}\n',
        capture_output=True,
        encoding="utf-8",
        timeout=15,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {"type": "error", "code": "outlook_invalid"}


def test_module_entrypoint_dispatches_helper_before_normal_app_startup():
    completed = subprocess.run(
        [sys.executable, "-m", "smaxtec", "--outlook-helper"],
        input='{"action":"invalid-offline-test"}\n',
        capture_output=True,
        encoding="utf-8",
        timeout=15,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {"type": "error", "code": "outlook_invalid"}


def test_offline_collection_smoke_checks_parser_dependencies_and_helper_only():
    from smaxtec.smoke import _check_collection_runtime

    _check_collection_runtime()
