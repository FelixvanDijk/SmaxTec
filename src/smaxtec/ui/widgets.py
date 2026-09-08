"""Small presentation helpers shared by the workspace and request editor."""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit


def label(text: str, name: str, *, wrap: bool = True) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def date_entry(value: date, accessible_name: str) -> QLineEdit:
    field = QLineEdit()
    field.setInputMask("00/00/0000;_")
    field.setText(value.strftime("%d/%m/%Y"))
    field.setAccessibleName(accessible_name)
    field.setMinimumWidth(130)
    return field
