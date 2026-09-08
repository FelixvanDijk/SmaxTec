"""Scrollable review of the exact immutable targets that will be submitted."""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smaxtec.application.exports import ExportRequest
from smaxtec.ui.widgets import label


class ExportReviewDialog(QDialog):
    def __init__(self, request: ExportRequest, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review export requests")
        self.resize(700, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(label("Ready to request your data?", "cardTitle"))
        layout.addWidget(label(request.farm.name, "fieldLabel"))
        layout.addWidget(
            label(
                f"{len(request.entries)} individual export requests. "
                "Check each cow's dates below. Identical rows appear only once.",
                "muted",
            )
        )
        self.table = QTableWidget(len(request.entries), 3)
        self.table.setAccessibleName("Reviewed cow numbers and individual date ranges")
        self.table.setHorizontalHeaderLabels(["Cow number", "From · DD/MM/YYYY", "To · DD/MM/YYYY"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        for index, entry in enumerate(request.entries):
            for column, text in enumerate(
                (entry.cow_number, entry.site_start_date, entry.site_end_date)
            ):
                self.table.setItem(index, column, QTableWidgetItem(text))
        layout.addWidget(self.table, 1)
        layout.addWidget(
            label("One measured-data export per cow and period listed above.", "privacy")
        )
        buttons = QDialogButtonBox()
        self.back_button = buttons.addButton("Back to edit", QDialogButtonBox.ButtonRole.RejectRole)
        self.back_button.setObjectName("secondary")
        self.back_button.setDefault(True)
        self.send_button = buttons.addButton(
            f"Request {len(request.entries)} export{'s' if len(request.entries) != 1 else ''}",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.send_button.setObjectName("primary")
        self.send_button.setAutoDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
