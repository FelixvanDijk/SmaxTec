"""Guided study UI operates asynchronously on synthetic local collections."""

from pathlib import Path

from PySide6.QtWidgets import QScrollArea
from test_study_workbook import _collection

from smaxtec.ui.study_dialog import StudyWorkbookDialog


def test_study_dialog_reviews_every_cow_and_writes_without_blocking_gui(qtbot, tmp_path):
    _collection(tmp_path)
    dialog = StudyWorkbookDialog(tmp_path)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: dialog._source is not None and dialog._worker is None)
    assert dialog.cases.rowCount() == 2
    assert [dialog.cases.item(row, 0).text() for row in range(2)] == ["57", "657"]
    for combo, pair in (
        (dialog.normal_temp, ("normal_temp", "celsius")),
        (dialog.temperature, ("temp_no_drink", "celsius")),
        (dialog.activity, ("activity", "index")),
        (dialog.rumination, ("rumination", "minutes")),
    ):
        index = next((i for i in range(combo.count()) if combo.itemData(i) == pair), -1)
        assert index > 0
        combo.setCurrentIndex(index)
    dialog.shared_event.setText("15/09/2026 09:10")
    dialog._apply_shared_event()
    assert all(dialog.cases.item(row, 3).text() == "15/09/2026 09:10" for row in range(2))
    dialog._create()
    assert dialog._worker is not None, dialog.status.text()
    qtbot.waitUntil(lambda: dialog._worker is None and dialog._output is not None)
    assert dialog._output == Path(tmp_path) / "client-study.xlsx"
    assert dialog.open_button.isEnabled()


def test_study_dialog_small_screen_scrolls_and_requires_all_event_times(qtbot, tmp_path):
    _collection(tmp_path)
    dialog = StudyWorkbookDialog(tmp_path)
    qtbot.addWidget(dialog)
    dialog.resize(760, 560)
    dialog.show()
    qtbot.waitUntil(lambda: dialog._source is not None and dialog._worker is None)
    assert dialog.cases.rowCount() == 2
    assert dialog.create_button.isVisible()
    assert dialog.cancel_button.isVisible()
    scroll = dialog.findChild(QScrollArea, "apiPageScroll")
    assert scroll is not None
    assert scroll.verticalScrollBar().maximum() > 0
    dialog._create()
    assert "Choose at least one" in dialog.status.text()
    assert not (tmp_path / "client-study.xlsx").exists()
    dialog._cancel_or_close()
    assert not dialog.isVisible()
