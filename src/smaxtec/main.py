"""Application composition and entry point."""

import os
import sys
from importlib.resources import files

from PySide6.QtWidgets import QApplication

from smaxtec.adapters.smaxtec.login import SmaxtecLoginSession
from smaxtec.ui.window import MainWindow


def configure_runtime() -> None:
    # The packaged browser lives beside Playwright. No first-run downloads.
    if getattr(sys, "frozen", False):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    else:
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")


def create_window() -> MainWindow:
    window = MainWindow(SmaxtecLoginSession)
    window.setStyleSheet(files("smaxtec.ui").joinpath("theme.qss").read_text(encoding="utf-8"))
    return window


def main() -> int:
    configure_runtime()
    app = QApplication(sys.argv)
    app.setApplicationName("SmaxTec Workbench")
    app.setOrganizationName("SmaxTec Workbench")
    if "--smoke-test" in sys.argv:
        # Developer/build verification, offline and without credentials.
        from smaxtec.smoke import run_smoke_test

        return run_smoke_test(app)
    window = create_window()
    window.show()
    return app.exec()
