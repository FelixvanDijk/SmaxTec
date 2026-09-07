"""Verified smaXtec login flow; all browser-specific details stay in this adapter."""

import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from threading import Event
from time import monotonic
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Locator, Page, Playwright, sync_playwright
from playwright.sync_api import Error as BrowserError
from playwright.sync_api import TimeoutError as BrowserTimeout

from smaxtec.application.exports import (
    ExportBatchResult,
    ExportError,
    ExportFailureCode,
    ExportProgress,
    ExportProgressCallback,
    ExportRequest,
    ExportStage,
    Farm,
)
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
    export_confirmation_timeout_ms: int = 15000


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
        self._attempted_exports: set[tuple[str, str, str, str]] = set()

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
                "Your smaXtec account is connected. Loading the farms available to this account…",
            )
        )

    def discover_farms(self, progress: ExportProgressCallback, stop: Event) -> tuple[Farm, ...]:
        try:
            self._require_active_session()
            assert self._page is not None
            page = self._page
            progress(
                ExportProgress(
                    ExportStage.DISCOVERING_FARMS,
                    "Checking which farms are available to this account…",
                )
            )
            switch = page.locator(
                '[data-testid="tooltip"][aria-label="Change herd"] button:visible'
            )
            self._wait_workflow_visible(switch, stop)
            switch.click()
            search = page.locator('[data-testid="search-modal-input"]:visible')
            self._wait_workflow_visible(search, stop)
            items = page.locator('[data-testid="search-modal-list-item"]:visible')
            self._wait_workflow_visible(items.first, stop)
            farms = tuple(
                dict.fromkeys(Farm(self._farm_name(item.inner_text())) for item in items.all())
            )
            page.keyboard.press("Escape")
            self._wait_hidden(search, stop)
            if not farms:
                raise ExportError(
                    ExportFailureCode.FARM_NOT_FOUND,
                    "No farms were available for this smaXtec account.",
                )
            progress(
                ExportProgress(
                    ExportStage.FARMS_READY,
                    f"Found {len(farms)} available farm{'s' if len(farms) != 1 else ''}.",
                )
            )
            return farms
        except BrowserTimeout:
            raise ExportError(
                ExportFailureCode.SITE_UNAVAILABLE,
                "The farm list took too long to load. Disconnect and try again.",
            ) from None
        except BrowserError:
            raise self._workflow_browser_error() from None

    @staticmethod
    def _farm_name(raw: str) -> str:
        return " ".join(part.strip() for part in raw.splitlines() if part.strip() != "↵")

    def request_exports(
        self,
        request: ExportRequest,
        progress: ExportProgressCallback,
        stop: Event,
    ) -> ExportBatchResult:
        completed: list[str] = []
        attempted: list[str] = []
        skipped: list[str] = []
        try:
            self._require_active_session()
            self._open_farm_animals(request.farm, progress, stop)
            for position, cow_number in enumerate(request.cow_numbers, start=1):
                self._checkpoint(stop)
                fingerprint = (
                    request.farm.name,
                    cow_number,
                    request.site_start_date,
                    request.site_end_date,
                )
                if fingerprint in self._attempted_exports:
                    skipped.append(cow_number)
                    continue
                progress(
                    ExportProgress(
                        ExportStage.FINDING_COW,
                        f"Finding cow {cow_number}…",
                        position,
                        len(request.cow_numbers),
                    )
                )
                row = self._find_exact_cow(cow_number, stop)
                self._open_export_dialog(row, stop)
                progress(
                    ExportProgress(
                        ExportStage.REQUESTING_EXPORT,
                        f"Requesting measured data for cow {cow_number}…",
                        position,
                        len(request.cow_numbers),
                    )
                )
                # From this point a retry could create a duplicate email. Record the
                # attempt before the single click, even if confirmation later times out.
                self._attempted_exports.add(fingerprint)
                attempted.append(cow_number)
                self._submit_export_dates(request, completed, stop)
                completed.append(cow_number)
                progress(
                    ExportProgress(
                        ExportStage.COW_COMPLETE,
                        f"Export requested for cow {cow_number}.",
                        position,
                        len(request.cow_numbers),
                    )
                )
            return ExportBatchResult(tuple(completed), tuple(skipped))
        except ExportError as error:
            raise ExportError(
                error.code,
                str(error),
                error.completed or tuple(completed),
                error.attempted or tuple(attempted),
            ) from None
        except BrowserTimeout:
            raise ExportError(
                ExportFailureCode.SITE_UNAVAILABLE,
                "The website took too long to respond. Completed requests were not repeated.",
                tuple(completed),
                tuple(attempted),
            ) from None
        except BrowserError:
            error = self._workflow_browser_error()
            raise ExportError(
                error.code,
                str(error),
                tuple(completed),
                tuple(attempted),
            ) from None

    def _require_active_session(self) -> None:
        if not self._authenticated():
            raise ExportError(
                ExportFailureCode.SESSION_EXPIRED,
                "The smaXtec session is no longer signed in. Disconnect and sign in again.",
            )

    def _open_farm_animals(self, farm: Farm, progress: ExportProgressCallback, stop: Event) -> None:
        assert self._page is not None
        page = self._page
        progress(ExportProgress(ExportStage.OPENING_FARM, f"Opening {farm.name} and its animals…"))
        switch = page.locator('[data-testid="tooltip"][aria-label="Change herd"] button:visible')
        self._wait_workflow_visible(switch, stop)
        switch.click()
        search = page.locator('[data-testid="search-modal-input"]:visible')
        self._wait_workflow_visible(search, stop)
        items = page.locator('[data-testid="search-modal-list-item"]:visible')
        self._wait_workflow_visible(items.first, stop)
        matches: list[Locator] = []
        for item in items.all():
            if self._farm_name(item.inner_text()) == farm.name:
                matches.append(item)
        if len(matches) != 1:
            page.keyboard.press("Escape")
            raise ExportError(
                ExportFailureCode.FARM_NOT_FOUND,
                f"The farm “{farm.name}” is no longer available. Disconnect and refresh the list.",
            )
        matches[0].get_by_text(farm.name, exact=True).click()
        self._wait_hidden(search, stop)
        animals = page.locator('a[href^="/animals?orgId="]:visible')
        self._wait_workflow_visible(animals, stop)
        animals.click()
        try:
            page.wait_for_url(re.compile(r".*/animals\?orgId="), wait_until="domcontentloaded")
        except BrowserTimeout:
            # Navigation is read-only; one fresh click handles a menu rerender after
            # changing farm without ever duplicating an export request.
            animals = page.locator('a[href^="/animals?orgId="]:visible')
            self._wait_workflow_visible(animals, stop)
            animals.click()
            page.wait_for_url(re.compile(r".*/animals\?orgId="), wait_until="domcontentloaded")
        self._wait_workflow_visible(page.get_by_test_id("animalHeader"), stop)

    def _find_exact_cow(self, cow_number: str, stop: Event) -> Locator:
        assert self._page is not None
        page = self._page
        headers = page.locator("th").filter(has=page.get_by_test_id("orderByMark"))
        if headers.count() != 1:
            raise self._workflow_page_changed("animal number search")
        search = headers.locator('input[data-testid="textInput"][placeholder="Search"]')
        if search.count() != 1:
            raise self._workflow_page_changed("animal number search")
        search.fill("")
        search.fill(cow_number)
        deadline = monotonic() + self.settings.element_timeout_ms / 1000
        settled = 0
        previous: tuple[str, ...] | None = None
        marks = page.locator(
            '[data-testid="animalTable-row"] td[data-testid="mark-link"] '
            '[data-testid="sxText"]:visible'
        )
        while monotonic() < deadline:
            self._checkpoint(stop)
            values = tuple(value.strip() for value in marks.all_inner_texts())
            filtered = bool(values) and all(
                cow_number.casefold() in value.casefold() for value in values
            )
            footer = page.get_by_test_id("animalFooter")
            empty = (
                not values
                and footer.count() == 1
                and re.search(r"\b0\s*[–-]\s*0\s+of\s+0\b", footer.inner_text())
            )
            if (filtered or empty) and values == previous:
                settled += 1
            else:
                settled = 0
            previous = values
            if settled >= 1:
                exact_indices = [index for index, value in enumerate(values) if value == cow_number]
                if not exact_indices:
                    location = "the results" if values else "this farm"
                    raise ExportError(
                        ExportFailureCode.COW_NOT_FOUND,
                        f"No exact animal number “{cow_number}” was found in {location}.",
                    )
                if len(exact_indices) > 1:
                    raise ExportError(
                        ExportFailureCode.COW_AMBIGUOUS,
                        f"More than one exact row was found for animal number “{cow_number}”. "
                        "No export was requested.",
                    )
                return page.get_by_test_id("animalTable-row").nth(exact_indices[0])
            page.wait_for_timeout(150)
        raise ExportError(
            ExportFailureCode.SITE_UNAVAILABLE,
            f"The search for animal number “{cow_number}” did not finish in time.",
        )

    def _open_export_dialog(self, row: Locator, stop: Event) -> None:
        assert self._page is not None
        button = row.locator('[data-testid="tooltip"][aria-label="Export data"] button:visible')
        if button.count() != 1:
            raise self._workflow_page_changed("cow export button")
        self._checkpoint(stop)
        button.click()
        self._wait_workflow_visible(self._page.get_by_role("dialog"), stop)

    def _submit_export_dates(
        self, request: ExportRequest, completed: list[str], stop: Event
    ) -> None:
        assert self._page is not None
        dialog = self._page.get_by_role("dialog")
        dates = dialog.locator('[data-testid="datePicker"] input[placeholder="DD/MM/YYYY"]')
        if dates.count() != 2:
            raise self._workflow_page_changed("export date fields")
        measured = dialog.get_by_role("radio", name="Measured data", exact=True)
        if measured.count() != 1:
            raise self._workflow_page_changed("measured data option")
        measured.check()
        dates.nth(0).fill(request.site_start_date)
        dates.nth(0).press("Tab")
        dates.nth(1).fill(request.site_end_date)
        dates.nth(1).press("Tab")
        if (
            dates.nth(0).input_value() != request.site_start_date
            or dates.nth(1).input_value() != request.site_end_date
        ):
            raise ExportError(
                ExportFailureCode.EXPORT_REJECTED,
                "smaXtec did not accept the selected date range. No export was requested.",
                tuple(completed),
            )
        submit = dialog.get_by_role("button", name="EXPORT", exact=True)
        if submit.count() != 1 or not submit.is_enabled():
            raise self._workflow_page_changed("final export button")
        self._checkpoint(stop)
        submit.click(no_wait_after=True)
        try:
            dialog.wait_for(state="hidden", timeout=self.settings.export_confirmation_timeout_ms)
        except BrowserTimeout:
            alerts = dialog.get_by_role("alert")
            if self._any_visible(alerts):
                raise ExportError(
                    ExportFailureCode.EXPORT_REJECTED,
                    "smaXtec rejected the export request. It was not submitted again.",
                    tuple(completed),
                ) from None
            raise ExportError(
                ExportFailureCode.EXPORT_UNCONFIRMED,
                "The export was clicked, but confirmation did not arrive. Check the email "
                "inbox before trying this cow again; the app will not repeat it in this session.",
                tuple(completed),
            ) from None

    def _wait_workflow_visible(self, locator: Locator, stop: Event) -> None:
        deadline = monotonic() + self.settings.element_timeout_ms / 1000
        while monotonic() < deadline:
            self._checkpoint(stop)
            try:
                locator.wait_for(state="visible", timeout=250)
                return
            except BrowserTimeout:
                continue
        raise self._workflow_page_changed("website controls")

    def _wait_hidden(self, locator: Locator, stop: Event) -> None:
        deadline = monotonic() + self.settings.element_timeout_ms / 1000
        while monotonic() < deadline:
            self._checkpoint(stop)
            try:
                locator.wait_for(state="hidden", timeout=250)
                return
            except BrowserTimeout:
                continue
        raise self._workflow_page_changed("website dialog")

    @staticmethod
    def _workflow_page_changed(control: str) -> ExportError:
        return ExportError(
            ExportFailureCode.PAGE_CHANGED,
            f"The expected {control} did not appear. No further exports were requested; "
            "the website may have changed and the app may need an update.",
        )

    def _workflow_browser_error(self) -> ExportError:
        closed = self._page is None or self._page.is_closed()
        return ExportError(
            ExportFailureCode.SESSION_EXPIRED if closed else ExportFailureCode.SITE_UNAVAILABLE,
            "The smaXtec browser was closed. Disconnect and sign in again."
            if closed
            else "The website connection ended unexpectedly. Disconnect and try again.",
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

    def is_open(self) -> bool:
        return self._page is not None and not self._page.is_closed()

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
