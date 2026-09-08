from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from smaxtec.application.exports import CowExport, ExportRequest, Farm
from smaxtec.ui.cow_editor import CowRequestsEditor
from smaxtec.ui.export_review import ExportReviewDialog


def target(number, month=8):
    return CowExport(str(number), date(2026, month, 1), date(2026, month, 3))


def populated(qtbot, count):
    editor = CowRequestsEditor()
    qtbot.addWidget(editor)
    editor.resize(760, 800)
    # Keep the initial row and fill it just as a user would.
    editor.rows[0].cow.setText("0")
    editor.rows[0].start_date.setText("01/08/2026")
    editor.rows[0].end_date.setText("03/08/2026")
    for index in range(1, count):
        editor.add_row(target(index, 7 if index % 2 else 8))
    editor.show()
    return editor


def test_first_five_grow_then_fold_keeps_every_value_and_deletion_identity(qtbot):
    editor = populated(qtbot, 5)
    assert all(not row.isHidden() for row in editor.rows)
    before = editor.entries()
    new_row = editor.add_row(target("057", 9))
    assert [i for i, row in enumerate(editor.rows) if not row.isHidden()] == [0, 4, 5]
    assert "3 rows folded" in editor.fold_button.text()
    assert editor.entries() == (*before, target("057", 9))
    qtbot.mouseClick(editor.fold_button, Qt.MouseButton.LeftButton)
    editor.rows[2].start_date.selectAll()
    qtbot.keyClicks(editor.rows[2].start_date, "02/08/2026")
    edited = editor.rows[2].entry()
    editor.remove_row(editor.rows[1])
    assert editor.rows[1].entry() == edited
    assert editor.rows[-1] is new_row
    assert new_row.ordinal.text() == "05"


def test_hidden_invalid_row_blocks_all_entries_and_can_be_revealed(qtbot):
    editor = populated(qtbot, 9)
    editor.rows[3].end_date.setText("31/02/2026")
    assert editor.rows[3].isHidden()
    with pytest.raises(ValueError, match="Row 4"):
        editor.entries()
    assert "Row 4" in editor.summary.text()
    qtbot.mouseClick(editor.fix_button, Qt.MouseButton.LeftButton)
    assert editor.expanded
    assert not editor.rows[3].isHidden()


def test_shared_dates_are_explicit_apply_to_hidden_rows_and_undo_restores_individuals(qtbot):
    editor = populated(qtbot, 10)
    before = editor.entries()
    editor.shared_start.setText("02/09/2026")
    editor.shared_end.setText("05/09/2026")
    assert editor.entries() == before
    editor.apply_shared_dates()
    assert all(entry.start_date == date(2026, 9, 2) for entry in editor.entries())
    assert all(entry.end_date == date(2026, 9, 5) for entry in editor.entries())
    editor.undo_shared_dates()
    assert editor.entries() == before
    editor.shared_end.setText("01/09/2026")
    editor.apply_shared_dates()
    assert editor.entries() == before  # Invalid shared range is an atomic no-op.


def test_hundreds_of_rows_stay_bounded_and_survive_expand_edit_and_refold(qtbot):
    editor = populated(qtbot, 300)
    before = editor.entries()
    assert len(before) == 300
    assert len([row for row in editor.rows if not row.isHidden()]) == 3
    assert editor.scroll.height() < 500
    editor.toggle_expanded()
    assert editor.scroll.height() < 500
    editor.rows[149].cow.setText("00149")
    editor.toggle_expanded()
    after = editor.entries()
    assert after[:149] == before[:149]
    assert after[150:] == before[150:]
    assert after[149].cow_number == "00149"
    assert after[149].start_date == before[149].start_date


def test_new_rows_use_applied_defaults_and_removing_last_row_keeps_editor_usable(qtbot):
    editor = populated(qtbot, 1)
    editor.shared_start.setText("02/09/2026")
    editor.shared_end.setText("05/09/2026")
    editor.apply_shared_dates()
    qtbot.mouseClick(editor.add_button, Qt.MouseButton.LeftButton)
    added = editor.rows[-1]
    added.cow.setText("057")
    assert added.entry() == CowExport("057", date(2026, 9, 2), date(2026, 9, 5))
    assert editor.undo_button.isHidden()  # Later row edits invalidate the one-step undo.
    editor.remove_row(editor.rows[0])
    qtbot.mouseClick(added.remove_button, Qt.MouseButton.LeftButton)
    assert len(editor.rows) == 1
    assert editor.rows[0] is not added
    editor.rows[0].cow.setText("257")
    assert editor.entries() == (CowExport("257", date(2026, 9, 2), date(2026, 9, 5)),)


def test_review_lists_all_exact_dates_and_cancel_does_not_approve(qtbot):
    request = ExportRequest(Farm("Example farm"), tuple(target(i) for i in range(300)))
    review = ExportReviewDialog(request)
    qtbot.addWidget(review)
    review.show()
    assert review.table.rowCount() == 300
    assert review.table.item(299, 0).text() == "299"
    assert review.table.item(299, 1).text() == "01/08/2026"
    assert review.table.item(299, 2).text() == "03/08/2026"
    qtbot.mouseClick(review.back_button, Qt.MouseButton.LeftButton)
    assert review.result() == QDialog.DialogCode.Rejected
