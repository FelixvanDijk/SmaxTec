"""Microsoft Graph connector tests use synthetic HTTP/auth fakes only."""

import io
import json
import sys
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from smaxtec.adapters.mail import graph
from smaxtec.application.collection import CollectionCancelled, CollectionError

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)
LINK = "https://api.smaxtec.com/api/v2/data/downloads/export-synthetic-graph.xlsx"
NEXT = graph.GRAPH_MESSAGES_URL + "?$skiptoken=opaque-pagination-value"
TOKEN = "synthetic-secret-access-token"


class FakeAuth:
    def __init__(self):
        self.calls = []

    def sign_in(self, stop):
        self.calls.append("sign-in")
        return graph._Session("a" * 64, "analyst@example.test - Microsoft 365 Inbox", TOKEN)

    def disconnect(self):
        self.calls.append("disconnect")


class Response(io.BytesIO):
    def __init__(self, payload, *, content_type="application/json"):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.headers = {"Content-Type": content_type}

    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def item(identity, minutes, *, subject="Noise", sender="person@example.test", body="Hello"):
    return {
        "id": identity,
        "subject": subject,
        "sender": {"emailAddress": {"address": sender}},
        "receivedDateTime": (NOW - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
        "body": {"contentType": "html", "content": body},
    }


def mailbox(*responses):
    auth = FakeAuth()
    opener = FakeOpener(*responses)
    result = graph.GraphMailbox(authenticator=auth, opener=opener, clock=lambda: NOW)
    folder = result.list_inboxes(Event())[0]
    return result, folder, auth, opener


def test_missing_or_invalid_app_registration_is_a_curated_setup_error(monkeypatch):
    monkeypatch.delenv("SMAXTEC_MICROSOFT_CLIENT_ID", raising=False)
    monkeypatch.setattr(graph, "EMBEDDED_MICROSOFT_CLIENT_ID", "")
    for value in (None, "not-a-client-id"):
        with pytest.raises(CollectionError) as error:
            graph.GraphMailbox(value).list_inboxes(Event())
        assert error.value.code == "graph_config"
        assert "application registration" in str(error.value)


def test_microsoft_sign_in_exposes_one_opaque_inbox_and_keeps_token_out_of_repr():
    result, folder, auth, _opener = mailbox()
    assert folder.key == "a" * 64
    assert folder.label == "analyst@example.test - Microsoft 365 Inbox"
    assert auth.calls == ["disconnect", "sign-in"]
    assert TOKEN not in repr(result)
    assert TOKEN not in repr(result._session)


def test_default_authenticator_uses_system_browser_flow_without_password_or_secret(monkeypatch):
    calls = {}

    class PublicClientApplication:
        def __init__(self, client_id, **options):
            calls["constructor"] = (client_id, options)

        def acquire_token_interactive(self, **options):
            calls["interactive"] = options
            return {
                "access_token": TOKEN,
                "id_token_claims": {
                    "tid": "synthetic-tenant",
                    "oid": "synthetic-user",
                    "preferred_username": "person@example.test",
                },
            }

    monkeypatch.setitem(
        sys.modules,
        "msal",
        SimpleNamespace(PublicClientApplication=PublicClientApplication, TokenCache=object),
    )
    auth = graph._MsalAuthenticator("00000000-0000-4000-8000-000000000001", timeout_seconds=2)
    session = auth.sign_in(Event())
    assert session.label == "person@example.test - Microsoft 365 Inbox"
    assert calls["constructor"][1]["authority"].endswith("/organizations")
    assert calls["interactive"] == {
        "scopes": ["Mail.Read"],
        "timeout": 2,
        "prompt": "select_account",
    }
    assert "password" not in repr(calls).casefold()
    assert TOKEN not in repr(session)


def test_newest_matching_scan_pages_read_only_and_recognizes_nested_forward():
    protected = "https://eur01.safelinks.protection.outlook.com/?url=" + quote(LINK, safe="")
    first = {
        "value": [
            item("noise", 1),
            item(
                "nested-forward",
                2,
                subject="Fw: Fw: requested information",
                body=f'<blockquote><a href="{protected}">Open file</a></blockquote>',
            ),
        ],
        "@odata.nextLink": NEXT,
    }
    second = {
        "value": [
            item(
                "direct",
                3,
                subject="Excel export file successfully created",
                sender="noreply@smaxtec.com",
                body=f'<p>smaXtec Excel export file</p><a href="{LINK}">Download</a>',
            )
        ]
    }
    source, folder, _auth, opener = mailbox(Response(first), Response(second))
    progress = []
    scan = source.scan(folder, 2, 7, Event(), progress.append)
    assert scan.scanned == 3
    assert [candidate.kind for candidate in scan.candidates] == ["forwarded", "direct"]
    assert scan.candidates[0].download_url == protected
    assert scan.warning == ""
    assert len(opener.calls) == 2
    initial = opener.calls[0][0]
    assert initial.get_method() == "GET"
    assert initial.get_header("Authorization") == "Bearer " + TOKEN
    assert parse_qs(urlsplit(initial.full_url).query)["$orderby"] == ["receivedDateTime desc"]
    assert opener.calls[1][0].full_url == NEXT
    assert progress[-1].current == progress[-1].total == 2


@pytest.mark.parametrize(
    "next_link",
    [
        "https://attacker.example/v1.0/me/mailFolders/inbox/messages?$skiptoken=secret",
        "http://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$skiptoken=secret",
        "https://graph.microsoft.com/v1.0/me/messages?$skiptoken=secret",
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages#private",
    ],
)
def test_pagination_never_sends_bearer_token_to_an_unverified_target(next_link):
    source, folder, _auth, opener = mailbox(Response({"value": [], "@odata.nextLink": next_link}))
    with pytest.raises(CollectionError) as error:
        source.scan(folder, 1, 1, Event(), lambda _progress: None)
    assert error.value.code == "graph_response"
    assert len(opener.calls) == 1
    assert next_link not in str(error.value)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "graph_session"),
        (403, "graph_permission"),
        (429, "graph_throttled"),
        (500, "graph_unavailable"),
    ],
)
def test_http_failures_are_curated_without_response_or_token_leak(status, code):
    failure = HTTPError(
        graph.GRAPH_MESSAGES_URL,
        status,
        "private server detail " + TOKEN,
        {},
        io.BytesIO(b'{"private":"mailbox detail"}'),
    )
    source, folder, _auth, _opener = mailbox(failure)
    with pytest.raises(CollectionError) as error:
        source.scan(folder, 1, 1, Event(), lambda _progress: None)
    assert error.value.code == code
    assert TOKEN not in str(error.value)
    assert "private" not in str(error.value)


def test_cancellation_and_disconnect_drop_memory_only_session_without_http():
    source, folder, auth, opener = mailbox()
    stop = Event()
    stop.set()
    with pytest.raises(CollectionCancelled):
        source.scan(folder, 1, 1, stop, lambda _progress: None)
    assert not opener.calls
    source.disconnect()
    assert source._session is None
    assert auth.calls[-1] == "disconnect"
    with pytest.raises(CollectionError) as error:
        source.scan(folder, 1, 1, Event(), lambda _progress: None)
    assert error.value.code == "graph_session"


def test_wrong_folder_and_malformed_json_fail_closed():
    source, folder, _auth, _opener = mailbox(Response([]))
    with pytest.raises(CollectionError) as error:
        source.scan(type(folder)("b" * 64, "other"), 1, 1, Event(), lambda _progress: None)
    assert error.value.code == "graph_invalid"

    source, folder, _auth, _opener = mailbox(Response([]))
    with pytest.raises(CollectionError) as error:
        source.scan(folder, 1, 1, Event(), lambda _progress: None)
    assert error.value.code == "graph_response"
