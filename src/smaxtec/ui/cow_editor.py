"""Editable per-cow rows, compact display and deliberate shared-date application."""

from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from smaxtec.application.exports import CowExport, parse_user_date, validate_date_range
from smaxtec.ui.widgets import date_entry, label


class CowRow(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, start: date, end: date) -> None:
        super().__init__()
        self.setObjectName("cowRow")
        self.setFixedHeight(62)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(10)
        self.ordinal = label("", "rowNumber", wrap=False)
        self.ordinal.setFixedWidth(30)
        self.cow = QLineEdit()
        self.cow.setPlaceholderText("Cow number")
        self.cow.setMinimumWidth(100)
        self.start_date = date_entry(start, "From date")
        self.end_date = date_entry(end, "To date")
        self.remove_button = QPushButton("×")
        self.remove_button.setObjectName("removeRow")
        self.remove_button.setFixedSize(32, 32)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self.ordinal)
        for field in (self.cow, self.start_date, self.end_date):
            layout.addWidget(field, 1)
            field.textChanged.connect(lambda _text: self.changed.emit())
        layout.addWidget(self.remove_button)

    def renumber(self, number: int) -> None:
        self.ordinal.setText(f"{number:02d}")
        self.cow.setAccessibleName(f"Row {number} cow number")
        self.start_date.setAccessibleName(f"Row {number} From date DD/MM/YYYY")
        self.end_date.setAccessibleName(f"Row {number} To date DD/MM/YYYY")
        self.remove_button.setAccessibleName(f"Remove cow row {number}")
        self.remove_button.setToolTip(f"Remove row {number}")

    def entry(self) -> CowExport:
        return CowExport(
            self.cow.text(),
            parse_user_date(self.start_date.text(), "From date"),
            parse_user_date(self.end_date.text(), "To date"),
        )


class CowRequestsEditor(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[CowRow] = []
        self.expanded = False
        self._changing = False
        self._undo_dates: list[tuple[CowRow, str, str]] = []
        self._defaults = (date.today() - timedelta(days=7), date.today())
        self._first_invalid: CowRow | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        tools = QHBoxLayout()
        tools.addWidget(label("Cow requests", "fieldLabel"))
        tools.addStretch()
        self.count = label("", "badge", wrap=False)
        tools.addWidget(self.count)
        self.expand_button = QPushButton("Expand all")
        self.expand_button.setObjectName("textButton")
        self.expand_button.clicked.connect(self.toggle_expanded)
        tools.addWidget(self.expand_button)
        layout.addLayout(tools)
        layout.addWidget(label("One cow per row. Give each its own From and To dates.", "muted"))

        self.shared_toggle = QPushButton("Use the same dates for all…")
        self.shared_toggle.setObjectName("textButton")
        self.shared_toggle.setCheckable(True)
        layout.addWidget(self.shared_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.shared_panel = QFrame()
        self.shared_panel.setObjectName("sharedDates")
        shared = QVBoxLayout(self.shared_panel)
        shared.addWidget(label("Apply one period to every row, including folded rows.", "muted"))
        fields = QHBoxLayout()
        self.shared_start = date_entry(self._defaults[0], "Shared From date DD/MM/YYYY")
        self.shared_end = date_entry(self._defaults[1], "Shared To date DD/MM/YYYY")
        for title, field in (("From", self.shared_start), ("To", self.shared_end)):
            column = QVBoxLayout()
            column.addWidget(label(title, "fieldLabel"))
            column.addWidget(field)
            fields.addLayout(column, 1)
        self.apply_button = QPushButton("Apply to all")
        self.apply_button.setObjectName("secondary")
        self.apply_button.clicked.connect(self.apply_shared_dates)
        fields.addWidget(self.apply_button, alignment=Qt.AlignmentFlag.AlignBottom)
        shared.addLayout(fields)
        self.shared_feedback = label("New rows use the last applied period.", "privacy")
        shared.addWidget(self.shared_feedback)
        self.undo_button = QPushButton("Undo date change")
        self.undo_button.setObjectName("textButton")
        self.undo_button.clicked.connect(self.undo_shared_dates)
        self.undo_button.hide()
        shared.addWidget(self.undo_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.shared_panel.hide()
        self.shared_toggle.toggled.connect(self.shared_panel.setVisible)
        layout.addWidget(self.shared_panel)

        header = QHBoxLayout()
        header.setContentsMargins(50, 0, 60, 0)
        header.setSpacing(10)
        for text in ("Cow number", "From · DD/MM/YYYY", "To · DD/MM/YYYY"):
            header.addWidget(label(text, "columnLabel"), 1)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("cowScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.row_container = QWidget()
        self.row_container.setObjectName("cowRows")
        self.row_layout = QVBoxLayout(self.row_container)
        self.row_layout.setContentsMargins(0, 0, 8, 0)
        self.row_layout.setSpacing(6)
        self.row_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.fold_button = QPushButton()
        self.fold_button.setObjectName("foldRows")
        self.fold_button.setFixedHeight(46)
        self.fold_button.clicked.connect(self.toggle_expanded)
        self.row_layout.addWidget(self.fold_button)
        self.scroll.setWidget(self.row_container)
        layout.addWidget(self.scroll)

        self.add_button = QPushButton("+  Add cow")
        self.add_button.setObjectName("secondary")
        self.add_button.clicked.connect(lambda: self.add_row(focus=True))
        layout.addWidget(self.add_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.summary = label("", "privacy")
        layout.addWidget(self.summary)
        self.fix_button = QPushButton("Go to incomplete row")
        self.fix_button.setObjectName("textButton")
        self.fix_button.clicked.connect(self.reveal_invalid)
        layout.addWidget(self.fix_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.add_row()

    def add_row(self, entry: CowExport | None = None, *, focus: bool = False) -> CowRow:
        row = CowRow(*self._defaults)
        if entry is not None:
            row.cow.setText(entry.cow_number)
            row.start_date.setText(entry.site_start_date)
            row.end_date.setText(entry.site_end_date)
        self.rows.append(row)
        self.row_layout.addWidget(row)
        row.changed.connect(self._edited)
        row.remove_requested.connect(self.remove_row)
        self._refresh_layout()
        self._edited()
        if focus:
            QTimer.singleShot(0, lambda: self._focus_row(row))
        return row

    def remove_row(self, row: CowRow) -> None:
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.row_layout.removeWidget(row)
        row.hide()
        row.deleteLater()
        if not self.rows:
            self.add_row(focus=True)
        else:
            self._refresh_layout()
            self._edited()

    def entries(self) -> tuple[CowExport, ...]:
        entries = []
        for number, row in enumerate(self.rows, 1):
            try:
                entries.append(row.entry())
            except ValueError as error:
                raise ValueError(f"Row {number}: {error}") from None
        return tuple(entries)

    def _edited(self) -> None:
        if self._changing:
            return
        self._undo_dates.clear()
        self.undo_button.hide()
        self._update_summary()
        self.changed.emit()

    def _update_summary(self) -> None:
        self._first_invalid = None
        for number, row in enumerate(self.rows, 1):
            try:
                row.entry()
            except ValueError as error:
                self._first_invalid = row
                self.summary.setText(f"Row {number}: {error}")
                break
        if self._first_invalid is None:
            unique = len(set(self.entries()))
            repeats = len(self.rows) - unique
            message = f"{unique} export request{'s' if unique != 1 else ''} ready for review."
            if repeats:
                message += f" {repeats} identical row(s) will be requested only once."
            self.summary.setText(message)
        self.fix_button.setVisible(self._first_invalid is not None and len(self.rows) > 1)
        self.count.setText(f"{len(self.rows)} ROW{'S' if len(self.rows) != 1 else ''}")

    def toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        self._refresh_layout()

    def _refresh_layout(self) -> None:
        count = len(self.rows)
        folded = count > 5 and not self.expanded
        self.row_layout.removeWidget(self.fold_button)
        self.row_layout.insertWidget(1, self.fold_button)
        self.fold_button.setVisible(folded)
        self.fold_button.setText(f"⋮   {count - 3} rows folded · Expand all")
        self.expand_button.setVisible(count > 5)
        self.expand_button.setText("Compact view" if self.expanded else "Expand all")
        for index, row in enumerate(self.rows):
            row.renumber(index + 1)
            row.setVisible(not folded or index in (0, count - 2, count - 1))
        height = 3 * 68 + 52 if folded else min(count, 7) * 68
        self.scroll.setFixedHeight(height)

    def _focus_row(self, row: CowRow) -> None:
        if row in self.rows:
            self.row_layout.activate()
            self.scroll.ensureWidgetVisible(row)
            row.cow.setFocus()

    def reveal_invalid(self) -> None:
        if self._first_invalid is not None:
            self.expanded = True
            self._refresh_layout()
            self._focus_row(self._first_invalid)

    def apply_shared_dates(self) -> None:
        try:
            start = parse_user_date(self.shared_start.text(), "shared From date")
            end = parse_user_date(self.shared_end.text(), "shared To date")
            validate_date_range(start, end)
        except ValueError as error:
            self.shared_feedback.setText(str(error))
            return
        self._undo_defaults = self._defaults
        self._undo_dates = [(row, row.start_date.text(), row.end_date.text()) for row in self.rows]
        self._changing = True
        try:
            for row in self.rows:
                row.start_date.setText(start.strftime("%d/%m/%Y"))
                row.end_date.setText(end.strftime("%d/%m/%Y"))
            self._defaults = (start, end)
        finally:
            self._changing = False
        self.shared_feedback.setText(f"Applied to all {len(self.rows)} rows and future rows.")
        self.undo_button.show()
        self._update_summary()
        self.changed.emit()

    def undo_shared_dates(self) -> None:
        if not self._undo_dates:
            return
        self._changing = True
        try:
            for row, start, end in self._undo_dates:
                row.start_date.setText(start)
                row.end_date.setText(end)
            self._defaults = self._undo_defaults
        finally:
            self._changing = False
        self.shared_feedback.setText("Previous individual date ranges restored.")
        self._edited()
