"""Private, one-command classic Outlook worker. Never called by ordinary tests live."""

import contextlib
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from smaxtec.adapters.mail.outlook import _error
from smaxtec.application.collection import CollectionError, MailCandidate, MailMessage

MAX_SCANNED = 10000
MAX_BODY_CHARS = 2 * 1024 * 1024


def _inherited_pipe(stream_id: int, mode: str) -> Any:
    """Restore redirected pipes when pythonw/PyInstaller sets Python streams to None."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetFileType.argtypes = [wintypes.HANDLE]
    kernel.GetFileType.restype = wintypes.DWORD
    handle = kernel.GetStdHandle(stream_id)
    if not handle or handle == ctypes.c_void_p(-1).value or kernel.GetFileType(handle) != 3:
        # Never fall back to files or allocate a visible console.
        raise OSError("A private parent pipe is required")
    access = os.O_RDONLY if mode == "r" else os.O_WRONLY
    descriptor = msvcrt.open_osfhandle(handle, access | os.O_BINARY)
    return os.fdopen(descriptor, mode, encoding="utf-8", errors="strict", newline="\n")


def _ensure_protocol_streams() -> None:
    if sys.stdin is None:
        sys.stdin = _inherited_pipe(-10, "r")
    if sys.stdout is None:
        sys.stdout = _inherited_pipe(-11, "w")
    if sys.stderr is None:
        # This standard stream deliberately lives until the helper process exits.
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def store_key(store_id: str) -> str:
    return hashlib.sha256(("outlook-store\0" + store_id).encode("utf-8")).hexdigest()


def message_key(store_id: str, entry_id: str) -> str:
    return hashlib.sha256(("outlook-mail\0" + store_id + "\0" + entry_id).encode()).hexdigest()


def _candidate_from_message(message: MailMessage) -> MailCandidate | None:
    from smaxtec.adapters.mail.messages import candidate_from_message

    return candidate_from_message(message)


def _available_inboxes(namespace: Any) -> list[tuple[str, str, str, Any]]:
    folders = []
    seen = set()
    stores = namespace.Stores
    if stores.Count > 100:
        raise _error("outlook_folders")
    for index in range(1, stores.Count + 1):
        try:
            store = stores.Item(index)
            identity = str(store.StoreID)
            if not identity or identity in seen:
                continue
            inbox = store.GetDefaultFolder(6)
            if inbox is None:
                continue
            label = str(store.DisplayName).strip()[:500] or "Outlook mailbox"
            folders.append((store_key(identity), label + " · Inbox", identity, inbox))
            seen.add(identity)
        except CollectionError:
            raise
        except Exception:
            # A mounted archive or unavailable shared store need not have an Inbox.
            continue
    if not folders:
        raise _error("outlook_folders")
    return folders


def _sender(mail: Any) -> str:
    address = str(mail.SenderEmailAddress or "")
    if str(mail.SenderEmailType or "").upper() == "EX":
        try:
            exchange_user = mail.Sender.GetExchangeUser()
            if exchange_user and exchange_user.PrimarySmtpAddress:
                address = str(exchange_user.PrimarySmtpAddress)
        except Exception:
            # Preserve the actual Exchange address, never guess a sender identity.
            pass
    return address[:500]


def _read_message(mail: Any, identity: str, received: datetime) -> MailMessage:
    entry_id = str(mail.EntryID or "")
    if not entry_id:
        raise ValueError("Missing stable identity")
    html = str(mail.HTMLBody or "")
    text = str(mail.Body or "")
    if len(html) + len(text) > MAX_BODY_CHARS:
        raise ValueError("Message exceeds safe input size")
    return MailMessage(
        key=message_key(identity, entry_id),
        subject=str(mail.Subject or "")[:500],
        sender=_sender(mail),
        received_at=received,
        html_body=html,
        text_body=text,
    )


def _scan(
    inbox: Any,
    identity: str,
    limit: int,
    days: int,
    emit: Callable[[dict], None],
    now: datetime,
) -> dict:
    try:
        items = inbox.Items
        items.Sort("[ReceivedTime]", True)
        initial_count = int(items.Count)
    except Exception:
        raise _error("outlook_order") from None
    cutoff = now - timedelta(days=days)
    candidates: list[dict] = []
    unreadable = scanned = 0
    reached_cutoff = False
    previous_received = None
    seen = set()
    for index in range(1, min(initial_count, MAX_SCANNED) + 1):
        scanned += 1
        if index == 1 or index % 25 == 0:
            emit({"type": "progress", "current": len(candidates), "total": limit})
        try:
            mail = items.Item(index)
            if mail.Class != 43:
                continue
        except Exception:
            unreadable += 1
            continue
        try:
            received = mail.ReceivedTime
            if not isinstance(received, datetime):
                raise ValueError
            # COM exposes local times; astimezone also handles naive local values.
            received = received.astimezone(UTC)
            if previous_received is not None and received > previous_received:
                raise ValueError
            previous_received = received
        except Exception:
            raise _error("outlook_order") from None
        if received < cutoff:
            reached_cutoff = True
            break
        if received > now:
            # Do not include email delivered after this scan began.
            continue
        try:
            message = _read_message(mail, identity, received)
            if message.key in seen:
                raise _error("outlook_changed")
            seen.add(message.key)
            candidate = _candidate_from_message(message)
        except CollectionError:
            raise
        except Exception:
            unreadable += 1
            continue
        if candidate is not None:
            record = asdict(candidate)
            record["received_at"] = candidate.received_at.isoformat()
            candidates.append(record)
            if len(candidates) == limit:
                break
    if int(items.Count) != initial_count:
        raise _error("outlook_changed")
    warnings = []
    if unreadable:
        warnings.append(
            f"{unreadable} inbox item(s) could not be read or were too large. "
            "The selection may be incomplete; check the preview and Outlook."
        )
    if len(candidates) < limit:
        warnings.append(
            f"Found {len(candidates)} matching email(s), fewer than the {limit} requested, "
            f"within the last {days} day(s)."
        )
        if scanned == MAX_SCANNED and not reached_cutoff and initial_count > MAX_SCANNED:
            warnings.append("The scan stopped at its 10,000-item safety limit.")
    emit({"type": "progress", "current": len(candidates), "total": limit})
    return {"candidates": candidates, "scanned": scanned, "warning": " ".join(warnings)}


def validate_request(request: Any) -> None:
    if not isinstance(request, dict) or request.get("action") not in {"list", "scan"}:
        raise _error("outlook_invalid")
    if request["action"] == "scan" and (
        type(request.get("limit")) is not int
        or not 1 <= request["limit"] <= 1000
        or type(request.get("days")) is not int
        or not 1 <= request["days"] <= 30
        or not isinstance(request.get("folder_key"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", request["folder_key"])
    ):
        raise _error("outlook_invalid")


def perform_request(
    namespace: Any,
    request: dict,
    emit: Callable[[dict], None],
    *,
    now: datetime | None = None,
) -> dict:
    """COM-shaped seam exercised with synthetic fakes, never with a real mailbox."""
    validate_request(request)
    folders = _available_inboxes(namespace)
    if request["action"] == "list":
        return {"folders": [{"key": key, "label": label} for key, label, _, _ in folders]}
    for key, _label, identity, inbox in folders:
        if key == request["folder_key"]:
            return _scan(
                inbox, identity, request["limit"], request["days"], emit, now or datetime.now(UTC)
            )
    raise _error("outlook_folder")


def _with_outlook(request: dict, emit: Callable[[dict], None]) -> dict:
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        raise _error("outlook_unavailable") from None
    pythoncom.CoInitialize()
    application = namespace = None
    try:
        try:
            application = win32com.client.Dispatch("Outlook.Application")
            namespace = application.GetNamespace("MAPI")
            if namespace.Accounts.Count < 1:
                raise _error("outlook_profile")
        except CollectionError:
            raise
        except Exception:
            raise _error("outlook_unavailable") from None
        return perform_request(namespace, request, emit)
    finally:
        namespace = application = None
        pythoncom.CoUninitialize()


def main() -> int:
    try:
        _ensure_protocol_streams()
    except (OSError, ImportError):
        return 2
    protocol = sys.stdout

    def emit(message: dict) -> None:
        protocol.write(json.dumps(message, ensure_ascii=True) + "\n")
        protocol.flush()

    try:
        line = sys.stdin.readline(4097)
        if len(line) > 4096:
            raise _error("outlook_invalid")
        try:
            request = json.loads(line)
        except (TypeError, ValueError):
            raise _error("outlook_invalid") from None
        validate_request(request)
        # Third-party output must never become protocol data or be shown to users.
        with contextlib.redirect_stdout(sys.stderr):
            result = _with_outlook(request, emit)
        emit({"type": "result", "data": result})
        return 0
    except CollectionError as error:
        emit({"type": "error", "code": error.code})
    except Exception:
        emit({"type": "error", "code": "outlook_scan"})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
