from dataclasses import replace
from threading import Event

import pytest

from smaxtec.adapters.smaxtec.login import LoginSettings, SmaxtecLoginSession
from smaxtec.application.login import (
    Credentials,
    FailureCode,
    LoginCancelled,
    LoginError,
    LoginStage,
)

SYNTHETIC_CREDENTIALS = Credentials("analyst@example.test", "synthetic-password")


@pytest.fixture
def session(website):
    adapter = SmaxtecLoginSession(
        LoginSettings(
            entry_url=f"{website.origin}/login",
            app_origin=website.origin,
            identity_origin=website.origin,
            headless=True,
            element_timeout_ms=600,
            verification_timeout_ms=1200,
            challenge_timeout_ms=1200,
        )
    )
    try:
        yield adapter
    finally:
        adapter.close()


def test_real_form_submission_and_verified_navigation(session, website):
    events = []
    session.connect(SYNTHETIC_CREDENTIALS, events.append, Event())
    assert [event.stage for event in events] == [
        LoginStage.OPENING,
        LoginStage.LOGIN_FORM,
        LoginStage.CREDENTIALS_ENTERED,
        LoginStage.VERIFYING,
        LoginStage.CONNECTED,
    ]
    assert website.submissions == 1
    assert session._authenticated()
    assert not session._page.is_closed()
    session.close()
    session.close()  # Cleanup is safe when called again.


@pytest.mark.parametrize(
    ("mode", "code", "submissions"),
    [
        ("reject", FailureCode.LOGIN_REJECTED, 1),
        ("changed", FailureCode.PAGE_CHANGED, 0),
        ("false-success", FailureCode.LOGIN_TIMEOUT, 1),
        ("untrusted-form", FailureCode.UNTRUSTED_PAGE, 0),
    ],
)
def test_failures_do_not_leak_secrets_or_retry(session, website, mode, code, submissions):
    website.mode = mode
    events = []
    with pytest.raises(LoginError) as caught:
        session.connect(SYNTHETIC_CREDENTIALS, events.append, Event())
    assert caught.value.code == code
    assert website.submissions == submissions
    assert SYNTHETIC_CREDENTIALS.password not in str(caught.value)
    assert SYNTHETIC_CREDENTIALS.username not in str(caught.value)
    assert LoginStage.CONNECTED not in [event.stage for event in events]
    if mode == "untrusted-form":
        assert session._page.locator("#password").input_value() == ""
        assert session._page.locator("#username").input_value() == ""


def test_credentials_never_filled_on_unexpected_identity_origin(session, website):
    session.settings = replace(session.settings, identity_origin="https://unexpected.example.test")
    with pytest.raises(LoginError) as caught:
        session.connect(SYNTHETIC_CREDENTIALS, lambda _event: None, Event())
    assert caught.value.code == FailureCode.UNTRUSTED_PAGE
    assert website.submissions == 0
    assert session._page.locator("#username").input_value() == ""


def test_cancellation_prevents_submission_after_filling(session, website):
    stop = Event()

    def cancel_at_credentials(event):
        if event.stage == LoginStage.CREDENTIALS_ENTERED:
            stop.set()

    with pytest.raises(LoginCancelled):
        session.connect(SYNTHETIC_CREDENTIALS, cancel_at_credentials, stop)
    assert website.submissions == 0


def test_cancellation_before_start_opens_no_browser(session):
    stop = Event()
    stop.set()
    with pytest.raises(LoginCancelled):
        session.connect(SYNTHETIC_CREDENTIALS, lambda _event: None, stop)
    assert session._browser is None


def test_challenge_requires_human_action(session, website):
    website.mode = "challenge"
    events = []
    with pytest.raises(LoginError) as caught:
        session.connect(SYNTHETIC_CREDENTIALS, events.append, Event())
    assert caught.value.code == FailureCode.LOGIN_TIMEOUT
    assert [event.stage for event in events].count(LoginStage.ACTION_REQUIRED) == 1
    assert website.submissions == 1


def test_human_can_complete_challenge_in_same_session(session, website):
    website.mode = "challenge"
    events = []

    def human_action(event):
        events.append(event)
        if event.stage == LoginStage.ACTION_REQUIRED:
            session._page.locator('[name="otp"]').fill("123456")
            session._page.get_by_role("button", name="Verify").click()

    session.connect(SYNTHETIC_CREDENTIALS, human_action, Event())
    assert events[-1].stage == LoginStage.CONNECTED


def test_browser_closed_during_login_has_actionable_error(session):
    def close_browser(event):
        if event.stage == LoginStage.LOGIN_FORM:
            session._page.close()

    with pytest.raises(LoginError) as caught:
        session.connect(SYNTHETIC_CREDENTIALS, close_browser, Event())
    assert caught.value.code == FailureCode.BROWSER_CLOSED


def test_session_stops_when_user_closes_browser(session):
    session.connect(SYNTHETIC_CREDENTIALS, lambda _event: None, Event())
    session._page.close()
    session.keep_open(Event())


def test_credentials_repr_is_private_and_password_is_not_trimmed():
    credentials = Credentials("  analyst@example.test  ", "  synthetic-password  ")
    assert credentials.username == "analyst@example.test"
    assert credentials.password == "  synthetic-password  "
    assert repr(credentials) == "Credentials()"


@pytest.mark.parametrize(("username", "password"), [("", "a"), ("a", ""), ("  ", "a")])
def test_missing_credentials_are_rejected(username, password):
    with pytest.raises(ValueError, match="Enter your email address and password"):
        Credentials(username, password)
