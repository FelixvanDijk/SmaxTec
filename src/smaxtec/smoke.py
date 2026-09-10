"""Offline packaging smoke test. No live site, credentials, or private artifacts."""

import json
import os
import subprocess
from datetime import UTC, datetime

from PySide6.QtWidgets import QApplication

from smaxtec.main import create_window


def _check_collection_runtime() -> None:
    """Exercise bundled parser imports and private helper pipes without opening Outlook."""
    import msal
    import olefile
    from defusedxml import ElementTree

    from smaxtec.adapters.mail.messages import candidate_from_message
    from smaxtec.adapters.mail.outlook import helper_command
    from smaxtec.application.collection import MailMessage

    assert callable(olefile.isOleFile)
    assert callable(msal.PublicClientApplication)
    assert ElementTree.fromstring("<smoke>ready</smoke>").text == "ready"
    if os.name == "nt":
        # Verify bundled COM DLL/module availability without creating Outlook or
        # explicitly initializing a COM session in this smoke path.
        import pythoncom
        import win32com.client

        assert callable(pythoncom.CoInitialize)
        assert callable(win32com.client.Dispatch)
    assert (
        candidate_from_message(
            MailMessage(
                "offline-smoke", "Not an export email", "nobody@example.test", datetime.now(UTC)
            )
        )
        is None
    )
    # Invalid actions are rejected before importing COM or accessing a mailbox.
    result = subprocess.run(
        helper_command(),
        input='{"action":"offline-smoke-invalid"}\n',
        capture_output=True,
        encoding="utf-8",
        timeout=12,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"type": "error", "code": "outlook_invalid"}


def run_smoke_test(app: QApplication) -> int:
    from playwright.sync_api import sync_playwright

    window = create_window()
    try:
        window.show()
        app.processEvents()
        assert window.isVisible() and window.connect_button.isEnabled()
        assert window.collection.import_button.isEnabled() and not window.collection.is_busy
        _check_collection_runtime()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chromium")
            page = browser.new_page()
            page.set_content("<title>Bundled browser ready</title><h1>Ready</h1>")
            assert page.get_by_role("heading", name="Ready").is_visible()
            browser.close()
        return 0
    except Exception:
        return 1
    finally:
        window.close()
        app.processEvents()
