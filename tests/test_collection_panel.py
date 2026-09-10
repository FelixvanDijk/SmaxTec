"""Synthetic GUI/worker tests: never access Outlook, emails, or production links."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event, get_ident

import pytest
from PySide6.QtCore import Qt

from smaxtec.application.collection import (
    CollectedFile,
    CollectionCancelled,
    CollectionError,
    CollectionProgress,
    CollectionResult,
    MailCandidate,
    MailFolder,
    MailScan,
)
from smaxtec.ui.collection_panel import CollectionPanel


def candidate(number: int, *, issue: str = "") -> MailCandidate:
    return MailCandidate(
        key=f"synthetic-message-{number}",
        subject="Fw: Excel export file successfully created",
        sender="colleague@example.test",
        received_at=datetime(2026, 9, 9, 12, tzinfo=UTC) - timedelta(minutes=number),
        kind="forwarded",
        download_url=f"https://download.example.test/export/{number}?secret=synthetic",
        link_fingerprint=f"synthetic-link-{number}",
        issue=issue,
    )


class FakeMailbox:
    def __init__(self):
        self.calls = []
        self.folders = (
            MailFolder("one", "First account / Inbox"),
            MailFolder("two", "Second / Inbox"),
        )
        self.messages = tuple(candidate(i) for i in range(25))

    def list_inboxes(self, stop):
        self.calls.append(("connect", get_ident()))
        return self.folders

    def scan(self, folder, limit, lookback_days, stop, progress):
        self.calls.append(("scan", folder, limit, lookback_days, get_ident()))
        progress(CollectionProgress("Read-only synthetic scan", 5, 25))
        return MailScan(self.messages[:limit], len(self.messages))


class FakeDownloader:
    def __init__(self):
        self.calls = []
        self.partial = False

    def download(self, candidates, destination, stop, progress, resume_folder=None):
        self.calls.append((candidates, destination, resume_folder, get_ident()))
        progress(CollectionProgress("Saving synthetic workbooks", 1, len(candidates)))
        files = tuple(
            CollectedFile(
                item.key,
                "failed" if self.partial and index == 1 else "saved",
                "" if self.partial and index == 1 else f"cow-{100 + index}.xlsx",
                str(100 + index),
                "Link needs attention" if self.partial and index == 1 else "Saved original bytes",
            )
            for index, item in enumerate(candidates)
        )
        return CollectionResult(resume_folder or destination / "synthetic-collection", files)


@pytest.fixture
def setup_panel(qtbot, tmp_path):
    mailbox, service = FakeMailbox(), FakeDownloader()
    panel = CollectionPanel(mailbox=mailbox, service=service)
    qtbot.addWidget(panel)
    panel.destination.setText(str(tmp_path / "collections"))
    panel.resize(850, 1050)
    panel.show()
    return panel, mailbox, service


def finish(qtbot, panel):
    qtbot.waitUntil(lambda: not panel.is_busy, timeout=5000)


def scan(qtbot, panel, index=1):
    qtbot.mouseClick(panel.connect_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    panel.inbox.setCurrentIndex(index)
    qtbot.mouseClick(panel.scan_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)


def test_initial_panel_does_not_connect_read_or_create_any_folders(setup_panel, tmp_path):
    panel, mailbox, service = setup_panel
    assert not panel.is_busy
    assert not mailbox.calls and not service.calls
    assert not (tmp_path / "collections").exists()
    assert not panel.scan_button.isEnabled()
    assert not panel.download_button.isEnabled()
    assert panel.resume_controls.isHidden()
    assert panel.import_button.isEnabled()  # Independent of the website connection.
    assert panel.latest.value() == 10
    assert panel.lookback.value() == 1


def test_outlook_requires_explicit_inbox_and_passes_latest_n_and_days(setup_panel, qtbot):
    panel, mailbox, _service = setup_panel
    main_thread = get_ident()
    qtbot.mouseClick(panel.connect_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert panel.inbox.currentData() is None
    assert not panel.scan_button.isEnabled()
    assert mailbox.calls[0][1] != main_thread
    panel.inbox.setCurrentIndex(2)
    panel.latest.setValue(3)
    panel.lookback.setValue(7)
    qtbot.mouseClick(panel.scan_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert mailbox.calls[-1][1:4] == (mailbox.folders[1], 3, 7)
    assert mailbox.calls[-1][-1] != main_thread
    assert panel.table.rowCount() == 3
    assert "Newest Inbox matches" in panel.review_title.text()
    assert panel.download_button.isEnabled()


def test_user_can_choose_microsoft_365_or_classic_outlook_connector(qtbot):
    microsoft, classic = FakeMailbox(), FakeMailbox()
    microsoft.disconnected = classic.disconnected = False
    microsoft.disconnect = lambda: setattr(microsoft, "disconnected", True)
    classic.disconnect = lambda: setattr(classic, "disconnected", True)
    panel = CollectionPanel(microsoft_mailbox=microsoft, outlook_mailbox=classic)
    qtbot.addWidget(panel)
    qtbot.mouseClick(panel.classic_connect_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert classic.calls and not microsoft.calls
    assert "classic Outlook" in panel.classic_connect_button.text()
    qtbot.mouseClick(panel.disconnect_button, Qt.MouseButton.LeftButton)
    assert classic.disconnected
    qtbot.mouseClick(panel.connect_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert microsoft.calls
    assert "Microsoft 365" in panel.connect_button.text()


def test_review_frozen_no_topups_and_filenames_differ_for_each_workbook(setup_panel, qtbot):
    panel, mailbox, service = setup_panel
    scan(qtbot, panel)
    frozen = panel._candidates
    assert len(frozen) == 10
    mailbox.messages = (candidate(99), *mailbox.messages)
    qtbot.mouseClick(panel.download_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert service.calls[0][0] == frozen
    assert service.calls[0][-1] != get_ident()
    assert len(mailbox.calls) == 2  # Download never scans again.
    assert "cow-100.xlsx" in panel.table.item(0, 4).text()
    assert "cow-109.xlsx" in panel.table.item(9, 4).text()
    assert not panel.download_button.isEnabled()
    assert panel.open_button.isEnabled()
    assert panel.retry_button.isHidden()


@pytest.mark.parametrize("change", ["latest", "days", "inbox", "disconnect"])
def test_selection_invalidates_on_scope_changes_and_disconnect(setup_panel, qtbot, change):
    panel, _mailbox, _service = setup_panel
    scan(qtbot, panel)
    assert panel._candidates
    if change == "latest":
        panel.latest.setValue(11)
    elif change == "days":
        panel.lookback.setValue(2)
    elif change == "inbox":
        panel.inbox.setCurrentIndex(2)
    else:
        qtbot.mouseClick(panel.disconnect_button, Qt.MouseButton.LeftButton)
    assert panel._candidates == ()
    assert panel.table.rowCount() == 0
    assert not panel.download_button.isEnabled()


def test_saved_import_is_manual_and_does_not_apply_inbox_latest_count(qtbot, tmp_path):
    imported = []

    def importer(paths, stop):
        imported.append((paths, get_ident()))
        return MailScan(tuple(candidate(i) for i in range(len(paths))), len(paths))

    panel = CollectionPanel(importer=importer, mailbox=FakeMailbox(), service=FakeDownloader())
    qtbot.addWidget(panel)
    panel.latest.setValue(1)
    paths = (tmp_path / "first.eml", tmp_path / "second.msg")
    panel.import_paths(paths)
    finish(qtbot, panel)
    assert imported[0][0] == paths
    assert imported[0][1] != get_ident()
    assert panel.table.rowCount() == 2
    assert "Manually selected" in panel.review_title.text()
    assert panel.download_button.isEnabled()


def test_preview_inert_metadata_and_duplicate_issue_rows_are_not_replaced(setup_panel, qtbot):
    panel, mailbox, service = setup_panel
    first = candidate(0)
    mailbox.messages = (
        replace(first, subject="<b>Export</b> https://example.test/?secret=private"),
        replace(
            candidate(1), download_url=first.download_url, link_fingerprint=first.link_fingerprint
        ),
        candidate(2, issue="Multiple export links: choose a single-link email"),
    )
    scan(qtbot, panel)
    assert "[link hidden]" in panel.table.item(0, 2).text()
    assert "<b>Export</b>" in panel.table.item(0, 2).text()  # Text, never rendered HTML.
    assert "private" not in panel.table.item(0, 2).toolTip()
    assert "Duplicate" in panel.table.item(1, 4).text()
    assert "1 duplicate" in panel.review_note.text()
    assert "1 message(s) needing attention" in panel.review_note.text()
    qtbot.mouseClick(panel.download_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert len(service.calls[0][0]) == 3


def test_no_download_when_all_selected_messages_have_unresolved_links(setup_panel, qtbot):
    panel, mailbox, service = setup_panel
    mailbox.messages = (candidate(0, issue="Ambiguous export links"),)
    scan(qtbot, panel)
    assert panel.table.rowCount() == 1
    assert not panel.download_button.isEnabled()
    panel._download()
    assert not service.calls


def test_partial_retry_preserves_original_selection_folder_and_successes(setup_panel, qtbot):
    panel, mailbox, service = setup_panel
    panel.latest.setValue(2)
    scan(qtbot, panel)
    service.partial = True
    qtbot.mouseClick(panel.download_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    frozen, folder = panel._candidates, panel._result.folder
    assert "1 incomplete" in panel.status.text()
    assert panel.retry_button.isEnabled()
    mailbox.messages = (candidate(999),)
    service.partial = False
    qtbot.mouseClick(panel.retry_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert service.calls[1][0] == frozen
    assert service.calls[1][2] == folder
    assert len(mailbox.calls) == 2
    assert "2 saved" in panel.status.text()


def test_resume_after_restart_uses_reviewed_selection_and_chosen_folder(
    setup_panel, qtbot, monkeypatch, tmp_path
):
    panel, mailbox, service = setup_panel
    panel.latest.setValue(2)
    scan(qtbot, panel)
    frozen = panel._candidates
    existing_folder = tmp_path / "earlier-collection"
    monkeypatch.setattr(
        "smaxtec.ui.collection_panel.QFileDialog.getExistingDirectory",
        lambda *_args: str(existing_folder),
    )
    assert panel.resume_button.isEnabled()
    mailbox.messages = (candidate(999),)  # Later arrivals never affect resume.
    qtbot.mouseClick(panel.resume_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert service.calls[0][0] == frozen
    assert service.calls[0][2] == existing_folder
    assert len(mailbox.calls) == 2
    assert panel._result.folder == existing_folder
    assert not panel.download_button.isEnabled()


def test_resume_cancel_or_service_rejection_does_not_replace_review(
    setup_panel, qtbot, monkeypatch, tmp_path
):
    panel, _mailbox, service = setup_panel
    scan(qtbot, panel)
    frozen = panel._candidates
    monkeypatch.setattr(
        "smaxtec.ui.collection_panel.QFileDialog.getExistingDirectory", lambda *_args: ""
    )
    qtbot.mouseClick(panel.resume_button, Qt.MouseButton.LeftButton)
    assert not service.calls
    assert panel._candidates == frozen

    def reject_different_collection(*_args, **_kwargs):
        raise CollectionError("resume_selection", "Re-select the same emails as this collection.")

    service.download = reject_different_collection
    monkeypatch.setattr(
        "smaxtec.ui.collection_panel.QFileDialog.getExistingDirectory",
        lambda *_args: str(tmp_path / "different-collection"),
    )
    qtbot.mouseClick(panel.resume_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert "Re-select the same emails" in panel.status.text()
    assert panel._candidates == frozen
    assert panel.download_button.isEnabled()


def test_busy_controls_cancel_and_idle_wait_for_worker_cleanup(setup_panel, qtbot):
    panel, mailbox, service = setup_panel
    scan(qtbot, panel)
    started = Event()

    def waiting_download(candidates, destination, stop, progress, resume_folder=None):
        started.set()
        if not stop.wait(3):
            raise AssertionError("Cancellation did not reach the worker")
        return CollectionResult(destination / "partial", (), cancelled=True)

    service.download = waiting_download
    qtbot.mouseClick(panel.download_button, Qt.MouseButton.LeftButton)
    assert panel.is_busy
    assert not panel.source_controls.isEnabled()
    assert not panel.import_button.isEnabled()
    assert not panel.download_button.isEnabled()
    qtbot.waitUntil(started.is_set)
    with qtbot.waitSignal(panel.idle, timeout=5000):
        panel.cancel()
        assert not panel.cancel_button.isEnabled()
    assert not panel.is_busy
    assert panel.source_controls.isEnabled()
    assert "cancelled" in panel.status.text()
    assert panel.retry_button.isEnabled()


@pytest.mark.parametrize("known", [False, True])
def test_worker_errors_are_actionable_without_raw_secret_text(setup_panel, qtbot, known):
    panel, mailbox, _service = setup_panel

    def broken_connect(stop):
        if known:
            raise CollectionError(
                "outlook_unavailable", "Open classic Outlook, or import saved emails."
            )
        raise RuntimeError("https://example.test/?secret=do-not-show confidential COM failure")

    mailbox.list_inboxes = broken_connect
    qtbot.mouseClick(panel.connect_button, Qt.MouseButton.LeftButton)
    finish(qtbot, panel)
    assert "secret" not in panel.status.text()
    assert "confidential" not in panel.status.text()
    assert panel.connect_button.isEnabled()
    assert panel.import_button.isEnabled()
    if known:
        assert "Open classic Outlook" in panel.status.text()


def test_cancelled_scan_drops_candidates_and_does_not_download(setup_panel, qtbot):
    panel, mailbox, service = setup_panel

    def cancelled_scan(folder, limit, days, stop, progress):
        raise CollectionCancelled

    mailbox.scan = cancelled_scan
    scan(qtbot, panel)
    assert panel._candidates == ()
    assert not panel.download_button.isEnabled()
    assert "Cancelled" in panel.status.text()
    assert not service.calls


def test_hundreds_of_preview_rows_have_a_bounded_scrollable_table(setup_panel, qtbot):
    panel, mailbox, _service = setup_panel
    mailbox.messages = tuple(candidate(i) for i in range(300))
    panel.latest.setValue(300)
    scan(qtbot, panel)
    assert panel.table.rowCount() == 300
    assert panel.table.height() == 240
    assert panel.table.item(299, 3).text() == "forwarded"
