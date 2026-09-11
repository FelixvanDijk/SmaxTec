"""Read-only Microsoft 365 Inbox access using delegated Microsoft sign-in.

This connector is independent of installed Outlook editions. Access tokens and
message bodies are memory-only and are deliberately excluded from repr output.
"""

import hashlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from importlib import resources
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from smaxtec.adapters.mail.messages import candidate_from_message, safe_text
from smaxtec.application.collection import (
    CollectionCancelled,
    CollectionError,
    CollectionProgress,
    MailCandidate,
    MailFolder,
    MailMessage,
    MailScan,
)

GRAPH_HOST = "graph.microsoft.com"
GRAPH_MESSAGES_PATH = "/v1.0/me/mailFolders/inbox/messages"
GRAPH_MESSAGES_URL = f"https://{GRAPH_HOST}{GRAPH_MESSAGES_PATH}"
GRAPH_SCOPE = "Mail.Read"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_BODY_CHARS = 4 * 1024 * 1024
MAX_SCANNED = 10000
PAGE_SIZE = 25

# Backward-compatible source fallback. Production builds instead receive their
# approved non-secret application ID through the generated package resource.
# The environment override exists only for source-mode development/tenant trials.
EMBEDDED_MICROSOFT_CLIENT_ID = ""
MICROSOFT_CONFIG_RESOURCE = "microsoft365.json"


ERROR_MESSAGES = {
    "graph_config": (
        "Microsoft 365 sign-in is not configured in this preview. The application "
        "administrator must provide an approved Microsoft application registration."
    ),
    "graph_login": (
        "Microsoft sign-in could not be completed. Close any old sign-in page and try again, "
        "or ask your IT administrator whether this application is approved."
    ),
    "graph_login_cancelled": "Microsoft sign-in was cancelled. No mailbox was connected.",
    "graph_session": "The Microsoft 365 session ended. Reconnect and try the Inbox scan again.",
    "graph_permission": (
        "Microsoft 365 did not allow this application to read the Inbox. Ask your IT "
        "administrator to approve delegated Mail.Read access, or import saved emails."
    ),
    "graph_throttled": (
        "Microsoft 365 temporarily limited mailbox access. Wait a few minutes, then scan again."
    ),
    "graph_unavailable": (
        "Microsoft 365 could not be reached. Check the internet connection and try again."
    ),
    "graph_timeout": "Microsoft 365 did not respond in time. Reconnect and try again.",
    "graph_response": (
        "Microsoft 365 returned an unexpected mailbox response. Nothing was selected; "
        "reconnect and try again."
    ),
    "graph_invalid": "The mailbox scan options are invalid. Choose 1-1000 emails and 1-30 days.",
}


def _error(code: str) -> CollectionError:
    if code not in ERROR_MESSAGES:
        code = "graph_response"
    return CollectionError(code, ERROR_MESSAGES[code])


def packaged_client_id() -> str:
    """Read the build-generated public-client ID without exposing its contents."""
    if not getattr(sys, "frozen", False):
        return ""
    try:
        raw = resources.files("smaxtec").joinpath(MICROSOFT_CONFIG_RESOURCE).read_text("utf-8")
        payload = json.loads(raw)
        value = payload.get("microsoft_client_id", "") if isinstance(payload, dict) else ""
        return value if isinstance(value, str) else ""
    except (FileNotFoundError, ModuleNotFoundError, OSError, TypeError, json.JSONDecodeError):
        return ""


def configured_client_id(explicit: str | None = None) -> str:
    if getattr(sys, "frozen", False):
        # End-user bundles use only their build-time registration. A process
        # environment variable must not silently substitute a different OAuth app.
        value = explicit or packaged_client_id()
    else:
        value = (
            explicit or EMBEDDED_MICROSOFT_CLIENT_ID or os.getenv("SMAXTEC_MICROSOFT_CLIENT_ID", "")
        )
    try:
        return str(UUID(value.strip()))
    except (AttributeError, ValueError):
        raise _error("graph_config") from None


@dataclass(frozen=True)
class _Session:
    folder_key: str
    label: str
    access_token: str = field(repr=False)


class _Authenticator(Protocol):
    def sign_in(self, stop: Event) -> _Session: ...

    def disconnect(self) -> None: ...


class _MsalAuthenticator:
    """Run MSAL's localhost browser flow behind a cancellable worker boundary."""

    def __init__(self, client_id: str, *, timeout_seconds: float = 180) -> None:
        self.client_id = client_id
        self.timeout_seconds = timeout_seconds
        self._application: Any = None

    def sign_in(self, stop: Event) -> _Session:
        events: Queue[tuple[str, Any]] = Queue(maxsize=1)

        def acquire() -> None:
            try:
                import msal

                application = msal.PublicClientApplication(
                    self.client_id,
                    authority="https://login.microsoftonline.com/organizations",
                    token_cache=msal.TokenCache(),
                )
                result = application.acquire_token_interactive(
                    scopes=[GRAPH_SCOPE],
                    timeout=int(self.timeout_seconds),
                    prompt="select_account",
                )
                events.put(("result", (application, result)))
            except Exception:
                events.put(("error", None))

        Thread(target=acquire, name="microsoft-sign-in", daemon=True).start()
        deadline = monotonic() + self.timeout_seconds
        while True:
            if stop.is_set():
                raise CollectionCancelled
            if monotonic() >= deadline:
                raise _error("graph_timeout")
            try:
                kind, payload = events.get(timeout=0.1)
            except Empty:
                continue
            if kind != "result":
                raise _error("graph_login")
            application, result = payload
            if not isinstance(result, dict) or not isinstance(result.get("access_token"), str):
                if isinstance(result, dict) and result.get("error") in {
                    "access_denied",
                    "user_cancelled",
                }:
                    raise _error("graph_login_cancelled")
                raise _error("graph_login")
            claims = result.get("id_token_claims")
            if not isinstance(claims, dict):
                raise _error("graph_login")
            object_id = claims.get("oid") or claims.get("sub")
            tenant_id = claims.get("tid")
            if not isinstance(object_id, str) or not isinstance(tenant_id, str):
                raise _error("graph_login")
            account_label = claims.get("preferred_username") or claims.get("name")
            if not isinstance(account_label, str) or not account_label.strip():
                account_label = "Signed-in work account"
            self._application = application
            folder_key = hashlib.sha256(
                ("graph-inbox\0" + tenant_id + "\0" + object_id).encode("utf-8")
            ).hexdigest()
            return _Session(
                folder_key,
                safe_text(account_label, 200) + " - Microsoft 365 Inbox",
                result["access_token"],
            )

    def disconnect(self) -> None:
        # TokenCache is memory-only. Releasing the application drops this app's
        # local token cache without signing the user out of Microsoft globally.
        self._application = None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _message_key(message_id: str) -> str:
    return hashlib.sha256(("graph-mail\0" + message_id).encode("utf-8")).hexdigest()


def _received(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 100:
        raise ValueError
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError
    return parsed.astimezone(UTC)


def _next_url(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 16000:
        raise _error("graph_response")
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or (parts.hostname or "").casefold() != GRAPH_HOST
            or parts.port not in (None, 443)
            or parts.username is not None
            or parts.password is not None
            or parts.path != GRAPH_MESSAGES_PATH
            or not parts.query
            or parts.fragment
        ):
            raise ValueError
    except ValueError:
        raise _error("graph_response") from None
    return value


class GraphMailbox:
    def __init__(
        self,
        client_id: str | None = None,
        *,
        authenticator: _Authenticator | None = None,
        opener: Any = None,
        clock: Callable[[], datetime] | None = None,
        request_timeout_seconds: float = 15,
        scan_timeout_seconds: float = 120,
    ) -> None:
        self._explicit_client_id = client_id
        self._authenticator = authenticator
        self._opener = opener if opener is not None else build_opener(_NoRedirect())
        self._clock = clock or (lambda: datetime.now(UTC))
        self.request_timeout_seconds = request_timeout_seconds
        self.scan_timeout_seconds = scan_timeout_seconds
        self._session: _Session | None = None

    def _auth(self) -> _Authenticator:
        if self._authenticator is None:
            self._authenticator = _MsalAuthenticator(configured_client_id(self._explicit_client_id))
        return self._authenticator

    def list_inboxes(self, stop: Event) -> tuple[MailFolder, ...]:
        if stop.is_set():
            raise CollectionCancelled
        self.disconnect()
        self._session = self._auth().sign_in(stop)
        return (MailFolder(self._session.folder_key, self._session.label),)

    def disconnect(self) -> None:
        self._session = None
        if self._authenticator is not None:
            self._authenticator.disconnect()

    def _get_json(self, url: str, stop: Event) -> dict[str, Any]:
        session = self._session
        if session is None:
            raise _error("graph_session")
        if stop.is_set():
            raise CollectionCancelled
        request = Request(
            url,
            headers={
                "Authorization": "Bearer " + session.access_token,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Prefer": 'outlook.body-content-type="html"',
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self.request_timeout_seconds) as response:
                if response.getcode() != 200:
                    raise _error("graph_response")
                content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0]
                if content_type.casefold() != "application/json" or response.headers.get(
                    "Content-Encoding"
                ):
                    raise _error("graph_response")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            if error.code == 401:
                self._session = None
                raise _error("graph_session") from None
            if error.code == 403:
                raise _error("graph_permission") from None
            if error.code == 429:
                raise _error("graph_throttled") from None
            if error.code in {408, 504}:
                raise _error("graph_timeout") from None
            raise _error("graph_unavailable" if error.code >= 500 else "graph_response") from None
        except (TimeoutError, URLError, OSError):
            raise _error("graph_unavailable") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise _error("graph_response")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise _error("graph_response") from None
        if not isinstance(result, dict):
            raise _error("graph_response")
        return result

    def scan(
        self,
        folder: MailFolder,
        limit: int,
        lookback_days: int,
        stop: Event,
        progress: Callable[[CollectionProgress], None],
    ) -> MailScan:
        session = self._session
        if (
            session is None
            or folder.key != session.folder_key
            or type(limit) is not int
            or not 1 <= limit <= 1000
            or type(lookback_days) is not int
            or not 1 <= lookback_days <= 30
        ):
            raise _error("graph_invalid" if session is not None else "graph_session")
        now = self._clock().astimezone(UTC)
        cutoff = now - timedelta(days=lookback_days)
        query = urlencode(
            {
                "$select": "id,subject,sender,receivedDateTime,body",
                "$filter": "receivedDateTime ge " + cutoff.isoformat().replace("+00:00", "Z"),
                "$orderby": "receivedDateTime desc",
                "$top": PAGE_SIZE,
            }
        )
        next_url: str | None = GRAPH_MESSAGES_URL + "?" + query
        candidates: list[MailCandidate] = []
        seen: set[str] = set()
        scanned = unreadable = 0
        previous_received: datetime | None = None
        deadline = monotonic() + self.scan_timeout_seconds
        while next_url is not None and scanned < MAX_SCANNED and len(candidates) < limit:
            if stop.is_set():
                raise CollectionCancelled
            if monotonic() >= deadline:
                raise _error("graph_timeout")
            progress(
                CollectionProgress("Finding Microsoft 365 export emails...", len(candidates), limit)
            )
            page = self._get_json(next_url, stop)
            values = page.get("value")
            if not isinstance(values, list) or len(values) > PAGE_SIZE:
                raise _error("graph_response")
            for raw in values:
                if scanned >= MAX_SCANNED or len(candidates) >= limit:
                    break
                scanned += 1
                try:
                    if not isinstance(raw, dict):
                        raise ValueError
                    message_id = raw.get("id")
                    if not isinstance(message_id, str) or not 1 <= len(message_id) <= 4096:
                        raise ValueError
                    key = _message_key(message_id)
                    if key in seen:
                        raise _error("graph_response")
                    seen.add(key)
                    received = _received(raw.get("receivedDateTime"))
                    if previous_received is not None and received > previous_received:
                        raise _error("graph_response")
                    previous_received = received
                    if received < cutoff or received > now:
                        raise ValueError
                    body = raw.get("body")
                    sender = raw.get("sender") or {}
                    address = sender.get("emailAddress") if isinstance(sender, dict) else {}
                    sender_text = address.get("address", "") if isinstance(address, dict) else ""
                    content = body.get("content", "") if isinstance(body, dict) else ""
                    content_type = body.get("contentType", "") if isinstance(body, dict) else ""
                    if (
                        not isinstance(content, str)
                        or len(content) > MAX_BODY_CHARS
                        or not isinstance(sender_text, str)
                        or not isinstance(raw.get("subject", ""), str)
                    ):
                        raise ValueError
                    message = MailMessage(
                        key=key,
                        subject=raw.get("subject", "")[:500],
                        sender=sender_text[:500],
                        received_at=received,
                        html_body=content if str(content_type).casefold() == "html" else "",
                        text_body=content if str(content_type).casefold() == "text" else "",
                    )
                    candidate = candidate_from_message(message)
                except CollectionError:
                    raise
                except (AttributeError, TypeError, ValueError):
                    unreadable += 1
                    continue
                if candidate is not None:
                    candidates.append(candidate)
            next_url = _next_url(page.get("@odata.nextLink"))
        warnings = []
        if unreadable:
            warnings.append(
                f"{unreadable} inbox item(s) could not be read or were too large. "
                "The selection may be incomplete; check the preview."
            )
        if len(candidates) < limit:
            warnings.append(
                f"Found {len(candidates)} matching email(s), fewer than the {limit} requested, "
                f"within the last {lookback_days} day(s)."
            )
        if scanned == MAX_SCANNED and next_url is not None:
            warnings.append("The scan stopped at its 10,000-item safety limit.")
        progress(CollectionProgress("Microsoft 365 Inbox review ready.", len(candidates), limit))
        return MailScan(tuple(candidates), scanned, " ".join(warnings))
