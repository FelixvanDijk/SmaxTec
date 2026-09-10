"""Classic Outlook checks use COM-shaped fakes and private IPC fakes, never mailboxes."""

import io
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from smaxtec.adapters.mail import outlook, outlook_helper
from smaxtec.application.collection import (
    CollectionCancelled,
    CollectionError,
    MailCandidate,
    MailFolder,
)

NOW = datetime(2026, 9, 9, 15, tzinfo=UTC)


class FakeItems:
    def __init__(self, messages, *, sort_error=False, count_changed=False):
        self.messages = messages
        self.sort_error = sort_error
        self.count_changed = count_changed
        self.count_reads = 0
        self.sort_calls = []

    @property
    def Count(self):
        self.count_reads += 1
        return len(self.messages) + int(self.count_changed and self.count_reads > 1)

    def Sort(self, field, descending):
        self.sort_calls.append((field, descending))
        if self.sort_error:
            raise RuntimeError("private COM callback/data must never leak")

    def Item(self, index):
        item = self.messages[index - 1]
        if isinstance(item, Exception):
            raise item
        return item


class FakeStore:
    def __init__(self, identity, name, messages=(), *, inaccessible=False, **options):
        self.StoreID = identity
        self.DisplayName = name
        self.inbox = SimpleNamespace(Items=FakeItems(list(messages), **options))
        self.inaccessible = inaccessible
        self.requested_folders = []

    def GetDefaultFolder(self, folder):
        self.requested_folders.append(folder)
        if self.inaccessible:
            raise RuntimeError("Private store error")
        assert folder == 6
        return self.inbox


def namespace(*stores):
    return SimpleNamespace(
        Stores=SimpleNamespace(Count=len(stores), Item=lambda index: stores[index - 1])
    )


def mail(identity, *, minutes=1, subject="export", sender="noreply@smaxtec.com", **extra):
    return SimpleNamespace(
        **{
            "Class": 43,
            "EntryID": identity,
            "ReceivedTime": NOW - timedelta(minutes=minutes),
            "Subject": subject,
            "SenderEmailAddress": sender,
            "SenderEmailType": "SMTP",
            "HTMLBody": "<p>synthetic export</p>",
            "Body": "synthetic export",
            **extra,
        }
    )


def request(store="first", *, limit=2, days=7):
    return {
        "action": "scan",
        "folder_key": outlook_helper.store_key(store),
        "limit": limit,
        "days": days,
    }


@pytest.fixture
def parser(monkeypatch):
    read = []

    def candidate(message):
        read.append(message)
        if message.subject == "unrelated":
            return None
        return MailCandidate(
            key=message.key,
            subject=message.subject,
            sender=message.sender,
            received_at=message.received_at,
            kind="direct" if message.sender == "noreply@smaxtec.com" else "forwarded",
            download_url="https://synthetic.invalid/export?private-link",
            link_fingerprint="synthetic-fingerprint",
        )

    monkeypatch.setattr(outlook_helper, "_candidate_from_message", candidate)
    return read


def test_lists_explicit_store_inboxes_with_stable_private_keys():
    first = FakeStore("first", "First account")
    second = FakeStore("second", "Second account")
    archive = FakeStore("archive", "Unavailable archive", inaccessible=True)
    result = outlook_helper.perform_request(
        namespace(first, second, archive), {"action": "list"}, lambda _: None
    )
    assert result["folders"] == [
        {"key": outlook_helper.store_key("first"), "label": "First account · Inbox"},
        {"key": outlook_helper.store_key("second"), "label": "Second account · Inbox"},
    ]
    assert first.requested_folders == second.requested_folders == [6]
    assert outlook_helper.message_key("first", "same") != outlook_helper.message_key(
        "second", "same"
    )


def test_chosen_mailbox_newest_matching_not_newest_overall(parser):
    first = FakeStore("first", "Wrong account", [mail("wrong")])
    second = FakeStore(
        "second",
        "Chosen account",
        [
            mail("noise", subject="unrelated"),
            mail("direct", minutes=2),
            mail("forward", minutes=3, sender="colleague@example.test"),
            mail("older", minutes=4),
        ],
    )
    events = []
    result = outlook_helper.perform_request(
        namespace(first, second), request("second"), events.append, now=NOW
    )
    assert [item["kind"] for item in result["candidates"]] == ["direct", "forwarded"]
    assert result["scanned"] == 3
    assert result["warning"] == ""
    assert second.inbox.Items.sort_calls == [("[ReceivedTime]", True)]
    assert first.inbox.Items.sort_calls == []
    assert len(parser) == 3
    assert events[-1] == {"type": "progress", "current": 2, "total": 2}


@pytest.mark.parametrize(
    "messages,options",
    [
        ([mail("first")], {"sort_error": True}),
        ([mail("first", ReceivedTime=None)], {}),
        ([mail("first", minutes=4), mail("second", minutes=2)], {}),
    ],
)
def test_unknown_time_or_unsorted_results_fail_closed(parser, messages, options):
    store = FakeStore("first", "Test account", messages, **options)
    with pytest.raises(CollectionError) as error:
        outlook_helper.perform_request(namespace(store), request(), lambda _: None, now=NOW)
    assert error.value.code == "outlook_order"
    assert "private" not in str(error.value).lower()


def test_lookback_and_inaccessible_item_are_explicit(parser):
    store = FakeStore(
        "first",
        "Test account",
        [RuntimeError("Protected mail"), mail("recent"), mail("old", minutes=8 * 24 * 60)],
    )
    result = outlook_helper.perform_request(namespace(store), request(), lambda _: None, now=NOW)
    assert len(result["candidates"]) == 1
    assert result["scanned"] == 3
    assert "could not be read" in result["warning"]
    assert "fewer than the 2" in result["warning"]
    assert len(parser) == 1


def test_oversized_body_is_not_parsed_and_warned(parser, monkeypatch):
    monkeypatch.setattr(outlook_helper, "MAX_BODY_CHARS", 4)
    store = FakeStore("first", "Test account", [mail("big")])
    result = outlook_helper.perform_request(namespace(store), request(), lambda _: None, now=NOW)
    assert not result["candidates"]
    assert "too large" in result["warning"]
    assert not parser


def test_item_limit_warns_instead_of_unbounded_scan(parser, monkeypatch):
    monkeypatch.setattr(outlook_helper, "MAX_SCANNED", 3)
    store = FakeStore(
        "first", "Test account", [mail(str(index), subject="unrelated") for index in range(4)]
    )
    result = outlook_helper.perform_request(namespace(store), request(), lambda _: None, now=NOW)
    assert result["scanned"] == 3
    assert "safety limit" in result["warning"]


@pytest.mark.parametrize("count_changed", [True, False])
def test_changed_inbox_or_duplicate_enumeration_fails(parser, count_changed):
    messages = [mail("same"), mail("other" if count_changed else "same", minutes=2)]
    store = FakeStore("first", "Test account", messages, count_changed=count_changed)
    with pytest.raises(CollectionError) as error:
        outlook_helper.perform_request(namespace(store), request(), lambda _: None, now=NOW)
    assert error.value.code == "outlook_changed"


def test_missing_selected_folder_never_uses_default_inbox():
    with pytest.raises(CollectionError) as error:
        outlook_helper.perform_request(
            namespace(FakeStore("different", "Another account")), request(), lambda _: None
        )
    assert error.value.code == "outlook_folder"


def test_sender_exchange_address_is_resolved_when_available(parser):
    sender = SimpleNamespace(
        GetExchangeUser=lambda: SimpleNamespace(PrimarySmtpAddress="forwarder@example.test")
    )
    store = FakeStore(
        "first",
        "Test account",
        [mail("first", sender="/O=EXAMPLE/OU=EXCHANGE", SenderEmailType="EX", Sender=sender)],
    )
    outlook_helper.perform_request(namespace(store), request(), lambda _: None, now=NOW)
    assert parser[0].sender == "forwarder@example.test"


class CapturedInput(io.StringIO):
    value = ""

    def close(self):
        if not self.closed:
            self.value = self.getvalue()
        super().close()


class FakeProcess:
    def __init__(self, messages):
        self.stdin = CapturedInput()
        self.stdout = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
        self.terminated = False
        self.killed = False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout):
        return 0


def mock_process(monkeypatch, messages):
    process = FakeProcess(messages)
    calls = []

    def create(command, **kwargs):
        calls.append((command, kwargs))
        return process

    monkeypatch.setattr(outlook.subprocess, "Popen", create)
    return process, calls


def test_parent_private_ipc_and_curated_progress(monkeypatch):
    raw = {
        "key": "synthetic-message",
        "subject": "Export",
        "sender": "noreply@smaxtec.com",
        "received_at": NOW.isoformat(),
        "kind": "direct",
        "download_url": "https://synthetic.invalid/export?private-link",
        "link_fingerprint": "fingerprint",
        "issue": "",
    }
    process, calls = mock_process(
        monkeypatch,
        [
            {"type": "progress", "current": 1, "total": 1, "message": "private should not show"},
            {"type": "result", "data": {"candidates": [raw], "scanned": 2, "warning": ""}},
        ],
    )
    progress = []
    result = outlook.OutlookMailbox().scan(
        MailFolder(outlook_helper.store_key("first"), "First"), 1, 7, Event(), progress.append
    )
    assert result.candidates[0].received_at == NOW
    assert result.candidates[0].download_url == raw["download_url"]
    assert "private-link" not in repr(result)
    assert all("private" not in event.message for event in progress)
    assert json.loads(process.stdin.value) == request(limit=1)
    assert "private" not in " ".join(calls[0][0])
    assert calls[0][1]["stderr"] == subprocess.DEVNULL
    assert process.terminated and process.stdout.closed


def test_parent_list_decodes_only_hashed_folder_ids(monkeypatch):
    folders = [{"key": outlook_helper.store_key("first"), "label": "First · Inbox"}]
    process, _ = mock_process(monkeypatch, [{"type": "result", "data": {"folders": folders}}])
    result = outlook.OutlookMailbox().list_inboxes(Event())
    assert result == (MailFolder(**folders[0]),)
    assert json.loads(process.stdin.value) == {"action": "list"}


@pytest.mark.parametrize("code", ["outlook_unavailable", "unexpected-secret-code"])
def test_parent_errors_never_echo_raw_helper_data(monkeypatch, code):
    mock_process(monkeypatch, [{"type": "error", "code": code, "message": "secret-private-data"}])
    with pytest.raises(CollectionError) as error:
        outlook.OutlookMailbox().list_inboxes(Event())
    assert "secret" not in str(error.value)
    assert error.value.code in {"outlook_unavailable", "outlook_protocol"}


def test_cancel_terminates_only_owned_helper(monkeypatch):
    process, _ = mock_process(monkeypatch, [{"type": "progress", "current": 0, "total": 1}])
    stop = Event()
    with pytest.raises(CollectionCancelled):
        outlook.OutlookMailbox()._request({"action": "scan"}, stop, lambda _: stop.set())
    assert process.terminated


def test_pre_cancel_starts_no_process(monkeypatch):
    _, calls = mock_process(monkeypatch, [])
    stop = Event()
    stop.set()
    with pytest.raises(CollectionCancelled):
        outlook.OutlookMailbox().list_inboxes(stop)
    assert not calls


def test_timeout_closes_owned_helper(monkeypatch):
    process, _ = mock_process(monkeypatch, [])
    with pytest.raises(CollectionError) as error:
        outlook.OutlookMailbox(timeout_seconds=0).list_inboxes(Event())
    assert error.value.code == "outlook_timeout"
    assert process.terminated


def test_malformed_helper_response_is_sanitized(monkeypatch):
    process, _ = mock_process(monkeypatch, [])
    process.stdout = io.StringIO("private secret traceback\n")
    with pytest.raises(CollectionError) as error:
        outlook.OutlookMailbox().list_inboxes(Event())
    assert error.value.code == "outlook_protocol"
    assert "private" not in str(error.value)


@pytest.mark.parametrize("limit,days", [(0, 7), (1001, 7), (True, 7), (1, 0), (1, 31)])
def test_public_input_limits_are_checked_before_spawn(monkeypatch, limit, days):
    _, calls = mock_process(monkeypatch, [])
    with pytest.raises(CollectionError):
        outlook.OutlookMailbox().scan(
            MailFolder(outlook_helper.store_key("first"), "First"),
            limit,
            days,
            Event(),
            lambda _: None,
        )
    assert not calls


def test_frozen_helper_has_no_personal_data_on_command_line(monkeypatch):
    monkeypatch.setattr(outlook.sys, "frozen", True, raising=False)
    monkeypatch.setattr(outlook.sys, "executable", "C:/Program Files/Workbench/Workbench.exe")
    assert outlook.helper_command() == [
        "C:/Program Files/Workbench/Workbench.exe",
        "--outlook-helper",
    ]


def test_helper_main_validates_before_opening_outlook(monkeypatch, capsys):
    monkeypatch.setattr(outlook_helper.sys, "stdin", io.StringIO('{"action":"bad"}\n'))
    connected = []
    monkeypatch.setattr(outlook_helper, "_with_outlook", lambda *_: connected.append(True))
    assert outlook_helper.main() == 1
    assert not connected
    assert json.loads(capsys.readouterr().out) == {"type": "error", "code": "outlook_invalid"}


def test_helper_main_does_not_expose_exception_contents(monkeypatch, capsys):
    monkeypatch.setattr(outlook_helper.sys, "stdin", io.StringIO('{"action":"list"}\n'))

    def failure(*_):
        raise RuntimeError("secret download URL and private COM details")

    monkeypatch.setattr(outlook_helper, "_with_outlook", failure)
    assert outlook_helper.main() == 1
    assert json.loads(capsys.readouterr().out) == {"type": "error", "code": "outlook_scan"}


def test_missing_windowless_streams_are_restored_from_parent_pipes(monkeypatch):
    incoming = io.StringIO('{"action":"bad"}\n')
    outgoing = io.StringIO()
    opened = []

    def pipe(identity, mode):
        opened.append((identity, mode))
        return incoming if mode == "r" else outgoing

    monkeypatch.setattr(outlook_helper, "_inherited_pipe", pipe)
    monkeypatch.setattr(outlook_helper.sys, "stdin", None)
    monkeypatch.setattr(outlook_helper.sys, "stdout", None)
    result = outlook_helper.main()
    # Restore stdout before pytest can emit its own progress.
    monkeypatch.undo()
    assert result == 1
    assert opened == [(-10, "r"), (-11, "w")]
    assert json.loads(outgoing.getvalue()) == {"type": "error", "code": "outlook_invalid"}


@pytest.mark.skipif(os.name != "nt", reason="Windows windowless interpreter smoke")
def test_windowless_source_helper_pipes_without_opening_outlook():
    executable = Path(sys.executable).with_name("pythonw.exe")
    if not executable.exists():
        pytest.skip("No windowless interpreter in this test environment")
    result = subprocess.run(
        [str(executable), "-m", "smaxtec.adapters.mail.outlook_helper"],
        input='{"action":"invalid-offline-smoke"}\n',
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"type": "error", "code": "outlook_invalid"}
    assert result.stderr == ""
