"""Classic Outlook access through a private, bounded helper process.

Only the helper uses COM. Termination never targets the user's Outlook process.
Neither mailbox contents nor download links are written to disk or command lines.
"""

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic
from typing import Any

from smaxtec.application.collection import (
    CollectionCancelled,
    CollectionError,
    CollectionProgress,
    MailCandidate,
    MailFolder,
    MailScan,
)

MAX_IPC_CHARS = 32 * 1024 * 1024
ERROR_MESSAGES = {
    "outlook_unavailable": (
        "Classic Outlook could not be connected. Open classic Outlook, sign in and try again. "
        "New Outlook does not provide this inbox connection; use saved-email import instead."
    ),
    "outlook_profile": "Open classic Outlook and sign in to a mail profile, then try again.",
    "outlook_folder": "That Outlook inbox is no longer available. Refresh the mailbox list.",
    "outlook_folders": "No accessible Outlook inboxes were found in the current profile.",
    "outlook_order": (
        "Outlook could not verify the newest-message order or a message's received time. "
        "Nothing was selected. Refresh Outlook and try again, or import saved emails."
    ),
    "outlook_changed": "The inbox changed during the scan. Please scan again before downloading.",
    "outlook_invalid": "The mailbox scan options are invalid. Choose 1–1000 emails and 1–30 days.",
    "outlook_timeout": (
        "Outlook did not respond in time. Check Outlook for a sign-in or access prompt, "
        "then try again. Your Outlook application has not been closed."
    ),
    "outlook_scan": (
        "Outlook could not read the selected inbox. Check that Outlook is online and that "
        "mailbox access is permitted, or import saved emails."
    ),
    "outlook_protocol": "The Outlook connection ended unexpectedly. Reconnect and try again.",
}


def _error(code: str) -> CollectionError:
    if code not in ERROR_MESSAGES:
        code = "outlook_protocol"
    return CollectionError(code, ERROR_MESSAGES[code])


def helper_command() -> list[str]:
    """The frozen executable dispatches this switch before importing/starting Qt."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--outlook-helper"]
    return [sys.executable, "-m", "smaxtec.adapters.mail.outlook_helper"]


def _read_lines(stream: Any, output: Queue) -> None:
    try:
        total = 0
        while line := stream.readline(MAX_IPC_CHARS + 1):
            total += len(line)
            if total > MAX_IPC_CHARS or not line.endswith("\n"):
                output.put(("invalid", None))
                return
            output.put(("line", line))
    except (OSError, ValueError):
        output.put(("invalid", None))
    finally:
        output.put(("eof", None))


def _close_helper(process: Any) -> None:
    """Close only our child, including when a COM prompt has blocked its thread."""
    try:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
    finally:
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()


class OutlookMailbox:
    def __init__(self, *, timeout_seconds: float = 120) -> None:
        self.timeout_seconds = timeout_seconds

    def list_inboxes(self, stop: Event) -> tuple[MailFolder, ...]:
        result = self._request({"action": "list"}, stop)
        try:
            folders = tuple(MailFolder(**item) for item in result["folders"])
            if not folders or len(folders) > 100:
                raise ValueError
            if any(
                not re.fullmatch(r"[a-f0-9]{64}", folder.key)
                or not isinstance(folder.label, str)
                or len(folder.label) > 600
                for folder in folders
            ):
                raise ValueError
            return folders
        except (KeyError, TypeError, ValueError):
            raise _error("outlook_protocol") from None

    def scan(
        self,
        folder: MailFolder,
        limit: int,
        lookback_days: int,
        stop: Event,
        progress: Callable[[CollectionProgress], None],
    ) -> MailScan:
        if (
            type(limit) is not int
            or not 1 <= limit <= 1000
            or type(lookback_days) is not int
            or not 1 <= lookback_days <= 30
            or not re.fullmatch(r"[a-f0-9]{64}", folder.key)
        ):
            raise _error("outlook_invalid")
        progress(CollectionProgress("Reading the chosen Outlook inbox…", 0, limit))
        result = self._request(
            {"action": "scan", "folder_key": folder.key, "limit": limit, "days": lookback_days},
            stop,
            progress,
        )
        try:
            candidates = []
            for raw in result["candidates"]:
                item = dict(raw)
                item["received_at"] = datetime.fromisoformat(item["received_at"])
                if item["received_at"].tzinfo is None:
                    raise ValueError
                candidates.append(MailCandidate(**item))
            scanned = result["scanned"]
            warning = result["warning"]
            if (
                len(candidates) > limit
                or type(scanned) is not int
                or not 0 <= scanned <= 10000
                or not isinstance(warning, str)
            ):
                raise ValueError
            return MailScan(tuple(candidates), scanned, warning)
        except (KeyError, TypeError, ValueError):
            raise _error("outlook_protocol") from None

    def _request(
        self,
        request: dict,
        stop: Event,
        progress: Callable[[CollectionProgress], None] | None = None,
    ) -> dict:
        if stop.is_set():
            raise CollectionCancelled
        options = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
            "encoding": "utf-8",
            "errors": "strict",
            "close_fds": True,
        }
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            process = subprocess.Popen(helper_command(), **options)
        except OSError:
            raise _error("outlook_unavailable") from None
        events: Queue = Queue()
        reader = Thread(target=_read_lines, args=(process.stdout, events), daemon=True)
        try:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.close()
            reader.start()
            deadline = monotonic() + self.timeout_seconds
            while True:
                if stop.is_set():
                    raise CollectionCancelled
                if monotonic() >= deadline:
                    raise _error("outlook_timeout")
                try:
                    kind, line = events.get(timeout=0.1)
                except Empty:
                    continue
                if kind != "line":
                    raise _error("outlook_protocol")
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError
                    if message.get("type") == "progress":
                        current = message["current"]
                        total = message["total"]
                        if type(current) is not int or type(total) is not int:
                            raise ValueError
                        if not 0 <= current <= total <= 1000:
                            raise ValueError
                        if progress:
                            progress(
                                CollectionProgress(
                                    "Finding the newest matching export emails…", current, total
                                )
                            )
                    elif message.get("type") == "error":
                        raise _error(message.get("code", "outlook_protocol"))
                    elif message.get("type") == "result" and isinstance(message.get("data"), dict):
                        return message["data"]
                    else:
                        raise ValueError
                except (ValueError, TypeError, KeyError):
                    raise _error("outlook_protocol") from None
        except (OSError, UnicodeError):
            raise _error("outlook_protocol") from None
        finally:
            _close_helper(process)
            if reader.is_alive():
                reader.join(timeout=1)
