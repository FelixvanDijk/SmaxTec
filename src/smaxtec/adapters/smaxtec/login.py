"""Verified smaXtec login flow; all browser-specific details stay in this adapter."""

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from threading import Event
from time import monotonic
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Locator, Page, Playwright, sync_playwright
from playwright.sync_api import Error as BrowserError
from playwright.sync_api import TimeoutError as BrowserTimeout

from smaxtec.application.login import (
    Credentials,
    FailureCode,
    LoginCancelled,
    LoginError,
    LoginProgress,
    LoginStage,
    ProgressCallback,
)


@dataclass(frozen=True)
class LoginSettings:
    entry_url: str = "https://web.smaxtec.com/login?callbackUrl=%2F"
    app_origin: str = "https://web.smaxtec.com"
    identity_origin: str = "https://sso.smaxtec.com"
    headless: bool = False
    navigation_timeout_ms: int = 15000
    element_timeout_ms: int = 20000
    action_timeout_ms: int = 5000
    verification_timeout_ms: int = 60000
    challenge_timeout_ms: int = 120000


def origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


class SmaxtecLoginSession:
    def __init__(self, settings: LoginSettings | None = None) -> None:
        self.settings = settings or LoginSettings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def connect(self, credentials: Credentials, progress: ProgressCallback, stop: Event) -> None:
        try:
            self._connect(credentials, progress, stop)
        except BrowserTimeout:
            self._checkpoint(stop)
            raise LoginError(
                FailureCode.SITE_UNAVAILABLE,
                "The website took too long to respond. Check your connection and try again.",
            ) from None
        except BrowserError:
            self._checkpoint(stop)
            closed = self._page is not None and self._page.is_closed()
            raise LoginError(
                FailureCode.BROWSER_CLOSED if closed else FailureCode.SITE_UNAVAILABLE,
                "The sign-in browser was closed. Connect again when you are ready."
                if closed
                else "The website could not be reached. Check your connection and try again.",
            ) from None

    def _connect(self, credentials: Credentials, progress: ProgressCallback, stop: Event) -> None:
        self._checkpoint(stop)
        progress(LoginProgress(LoginStage.OPENING, "Opening smaXtec in a separate browser…"))
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.settings.headless,
                channel="chromium",
                timeout=self.settings.navigation_timeout_ms,
            )
        except BrowserError:
            raise LoginError(
                FailureCode.BROWSER_UNAVAILABLE,
                "The sign-in browser could not start. Close the app and try again. "
                "If this continues, reinstall the complete application or contact support.",
            ) from None
        self._context = self._browser.new_context(accept_downloads=False, locale="en-GB")
        self._page = page = self._context.new_page()
        page.set_default_timeout(self.settings.action_timeout_ms)
        page.set_default_navigation_timeout(self.settings.navigation_timeout_ms)
        self._checkpoint(stop)
        page.goto(self.settings.entry_url, wait_until="domcontentloaded")
        self._require_origin(self.settings.app_origin)

        entry = page.get_by_role("button", name="Go to log in", exact=True)
        self._wait_visible(entry, stop)
        self._checkpoint(stop)
        entry.click()
        username = page.locator("input#username")
        password = page.locator("input#password")
        self._wait_visible(username, stop)
        self._wait_visible(password, stop)
        self._require_origin(self.settings.identity_origin)
        # Guard both the page and the actual form destination before filling secrets.
        form_action = password.evaluate("el => el.form ? el.form.action : ''")
        if origin(form_action) != self.settings.identity_origin:
            raise LoginError(
                FailureCode.UNTRUSTED_PAGE,
                "The sign-in form has an unexpected destination. Contact support before retrying.",
            )
        if password.get_attribute("type") != "password":
            raise self._page_changed()

        progress(LoginProgress(LoginStage.LOGIN_FORM, "The smaXtec sign-in form is ready."))
        self._checkpoint(stop)
        username.fill(credentials.username)
        password.fill(credentials.password)
        progress(
            LoginProgress(LoginStage.CREDENTIALS_ENTERED, "Your sign-in details have been entered.")
        )
        self._checkpoint(stop)
        self._require_origin(self.settings.identity_origin)
        submit = page.locator("input#kc-login[type=submit]")
        self._wait_visible(submit, stop)
        self._checkpoint(stop)
        # Exactly one submission. A timeout must never cause an automatic resubmit.
        submit.click(no_wait_after=True)
        progress(LoginProgress(LoginStage.VERIFYING, "Checking that smaXtec has signed you in…"))
        self._wait_for_authenticated(progress, stop)
        self._checkpoint(stop)
        progress(
            LoginProgress(
                LoginStage.CONNECTED,
                "Your smaXtec account is connected. This version stops here; "
                "the browser stays open until you disconnect.",
            )
        )

    def _require_origin(self, expected: str) -> None:
        assert self._page is not None
        if origin(self._page.url) != expected:
            raise LoginError(
                FailureCode.UNTRUSTED_PAGE,
                "The website opened an unexpected sign-in address. "
                "Contact support before retrying.",
            )

    @staticmethod
    def _checkpoint(stop: Event) -> None:
        if stop.is_set():
            raise LoginCancelled()

    @staticmethod
    def _page_changed() -> LoginError:
        return LoginError(
            FailureCode.PAGE_CHANGED,
            "The expected sign-in controls did not appear. Try again; if this continues, "
            "the website may have changed and the app may need an update.",
        )

    def _wait_visible(self, locator: Locator, stop: Event) -> None:
        deadline = monotonic() + self.settings.element_timeout_ms / 1000
        while monotonic() < deadline:
            self._checkpoint(stop)
            try:
                locator.wait_for(state="visible", timeout=250)
                return
            except BrowserTimeout:
                continue
        raise self._page_changed()

    def _authenticated(self) -> bool:
        assert self._page is not None
        page = self._page
        location = urlsplit(page.url)
        return (
            origin(page.url) == self.settings.app_origin
            and not location.path.startswith(("/login", "/api/auth"))
            and page.get_by_test_id("navigationHeader").is_visible()
            and page.get_by_test_id("menuItems").is_visible()
            and not page.locator("#username").is_visible()
        )

    def _wait_for_authenticated(self, progress: ProgressCallback, stop: Event) -> None:
        assert self._page is not None
        page = self._page
        deadline = monotonic() + self.settings.verification_timeout_ms / 1000
        challenge_reported = False
        while monotonic() < deadline:
            self._checkpoint(stop)
            if self._authenticated():
                return
            if origin(page.url) == self.settings.identity_origin:
                rejected = page.locator("#input-error, .pf-c-alert.pf-m-danger, #kc-error-message")
                if self._any_visible(rejected):
                    raise LoginError(
                        FailureCode.LOGIN_REJECTED,
                        "smaXtec could not sign you in. Check your details and account access, "
                        "then try again. Your sign-in was not retried automatically.",
                    )
                challenge = page.locator(
                    'input[name="otp"], input[autocomplete="one-time-code"], '
                    '#kc-webauthn, iframe[src*="recaptcha"], iframe[title*="challenge" i]'
                )
                if not challenge_reported and self._any_visible(challenge):
                    challenge_reported = True
                    deadline = monotonic() + self.settings.challenge_timeout_ms / 1000
                    progress(
                        LoginProgress(
                            LoginStage.ACTION_REQUIRED,
                            "smaXtec needs an extra verification step. Complete it in the browser "
                            "window, or cancel to try later.",
                        )
                    )
            # Deliberate event-pump heartbeat while observing mutually exclusive states.
            # This is not a fixed sleep used to guess when a page has finished loading.
            page.wait_for_timeout(150)
        raise LoginError(
            FailureCode.LOGIN_TIMEOUT,
            "Sign-in could not be confirmed in time. There may be an extra verification step "
            "or a website change. Try again, or contact support if this continues.",
        )

    @staticmethod
    def _any_visible(locator: Locator) -> bool:
        return any(item.is_visible() for item in locator.all())

    def keep_open(self, stop: Event) -> None:
        assert self._page is not None
        try:
            while not stop.is_set() and not self._page.is_closed():
                self._page.wait_for_timeout(200)
        except BrowserError:
            if not stop.is_set() and not self._page.is_closed():
                raise LoginError(
                    FailureCode.BROWSER_CLOSED,
                    "The browser connection ended. Connect again to continue.",
                ) from None

    def close(self) -> None:
        # Best-effort cleanup of every owned resource, even if an earlier close fails.
        closers: list[Callable[[], None]] = []
        if self._context is not None:
            closers.append(self._context.close)
        if self._browser is not None:
            closers.append(self._browser.close)
        if self._playwright is not None:
            closers.append(self._playwright.stop)
        for close in closers:
            with suppress(BrowserError):
                close()
        self._page = self._context = self._browser = self._playwright = None
