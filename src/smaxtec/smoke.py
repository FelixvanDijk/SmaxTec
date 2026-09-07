"""Offline packaging smoke test. No live site, credentials, or private artifacts."""

from PySide6.QtWidgets import QApplication

from smaxtec.main import create_window


def run_smoke_test(app: QApplication) -> int:
    from playwright.sync_api import sync_playwright

    window = create_window()
    try:
        window.show()
        app.processEvents()
        assert window.isVisible() and window.connect_button.isEnabled()
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
