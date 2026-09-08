"""GUI -> worker -> real browser -> offline endpoint, with distinct dates per row."""

from datetime import date

from smaxtec.adapters.smaxtec.login import LoginSettings, SmaxtecLoginSession
from smaxtec.application.exports import CowExport
from smaxtec.ui.window import MainWindow


def connected_window(qtbot, website, monkeypatch):
    def factory():
        return SmaxtecLoginSession(
            LoginSettings(
                entry_url=f"{website.origin}/login",
                app_origin=website.origin,
                identity_origin=website.origin,
                headless=True,
                export_confirmation_timeout_ms=1000,
            )
        )

    window = MainWindow(factory)
    qtbot.addWidget(window)
    window.username.setText("analyst@example.test")
    window.password.setText("synthetic-password")
    monkeypatch.setattr(window, "_review_request", lambda _request: True)
    window._start()
    qtbot.waitUntil(lambda: window._farms_ready, timeout=30000)
    return window


def test_gui_sends_each_reviewed_period_and_retains_dates_when_new_batch_reconnects(
    qtbot, website, monkeypatch
):
    window = connected_window(qtbot, website, monkeypatch)
    try:
        first = window.cow_editor.rows[0]
        for field, text in (
            (first.cow, "57"),
            (first.start_date, "01/09/2026"),
            (first.end_date, "03/09/2026"),
        ):
            field.selectAll()
            qtbot.keyClicks(field, text)
        second = window.cow_editor.add_row(CowExport("257", date(2026, 8, 10), date(2026, 8, 14)))
        window._request_exports()
        assert not window.cow_editor.isEnabled()
        qtbot.waitUntil(lambda: not window._export_busy, timeout=30000)
        assert [(e["cow"], e["from"], e["to"]) for e in website.exports] == [
            ("57", "01/09/2026", "03/09/2026"),
            ("257", "10/08/2026", "14/08/2026"),
        ]
        window.cow_editor.remove_row(second)
        first.end_date.setText("04/09/2026")
        window._request_exports()
        qtbot.waitUntil(lambda: not window._export_busy, timeout=30000)
        assert website.submissions == 2
        assert len(website.exports) == 3
        assert website.exports[-1]["from"] == "01/09/2026"
        assert website.exports[-1]["to"] == "04/09/2026"
    finally:
        window._stop()
        qtbot.waitUntil(lambda: window._worker is None, timeout=20000)


def test_partial_failure_remembers_exact_attempts_across_reconnect_and_keeps_pending_dates(
    qtbot, website, monkeypatch
):
    window = connected_window(qtbot, website, monkeypatch)
    try:
        first = window.cow_editor.rows[0]
        first.cow.setText("57")
        first.start_date.setText("01/09/2026")
        first.end_date.setText("02/09/2026")
        failed = CowExport("257", date(2026, 8, 1), date(2026, 8, 5))
        pending = CowExport("57", date(2026, 7, 1), date(2026, 7, 3))
        window.cow_editor.add_row(failed)
        window.cow_editor.add_row(pending)
        website.mode = "reject-cow-257"
        window._request_exports()
        qtbot.waitUntil(lambda: not window._export_busy, timeout=30000)
        assert len(website.exports) == 1
        assert "1 request(s) completed" in window.status_message.text()
        website.mode = "success"
        window._request_exports()
        qtbot.waitUntil(lambda: not window._export_busy, timeout=30000)
        assert website.submissions == 2
        assert [(e["cow"], e["from"], e["to"]) for e in website.exports] == [
            ("57", "01/09/2026", "02/09/2026"),
            ("57", "01/07/2026", "03/07/2026"),
        ]
        assert "Skipped 2" in window.status_message.text()
    finally:
        window._stop()
        qtbot.waitUntil(lambda: window._worker is None, timeout=20000)
