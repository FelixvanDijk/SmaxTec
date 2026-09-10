"""Strict export-link policy and bounded HTTPS downloads without browser credentials."""

import hashlib
import ipaddress
import os
import re
import socket
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from functools import partial
from http.client import HTTPException
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from smaxtec.application.collection import CollectionCancelled, CollectionError

API_HOST = "api.smaxtec.com"
API_PREFIX = "/api/v2/data/downloads/"
STORAGE_HOST = "storage.googleapis.com"
STORAGE_PREFIX = "/anthilldata_excel_exports/"
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
_OBJECT = re.compile(r"export-[a-zA-Z0-9_.-]{1,180}\.xlsx", re.ASCII)
_SAFE_HOST = re.compile(r"[a-z0-9-]+\.safelinks\.protection\.outlook\.com", re.ASCII)


def _unsafe() -> CollectionError:
    return CollectionError(
        "unsafe_link", "This email's download address is not a verified smaXtec export link."
    )


def _parts(url: str):
    if not isinstance(url, str) or len(url) > 16_384 or re.search(r"[\s\\\x00-\x1f\x7f]", url):
        raise _unsafe()
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.username is not None
            or parts.password is not None
            or parts.port not in (None, 443)
            or parts.fragment
            or not parts.hostname
        ):
            raise _unsafe()
    except ValueError:
        raise _unsafe() from None
    return parts


@dataclass(frozen=True)
class DownloadTarget:
    # Even the object name is a bearer capability for this API, not log metadata.
    object_name: str = field(repr=False)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.object_name.encode("ascii")).hexdigest()


def target_from_link(url: str, depth: int = 0) -> DownloadTarget:
    """Classify wrappers without bypassing them: downloads still fetch the original URL."""
    if depth > 4:
        raise _unsafe()
    parts = _parts(url)
    if _SAFE_HOST.fullmatch(parts.hostname) and parts.path in ("", "/"):
        try:
            embedded = parse_qs(parts.query, max_num_fields=20, keep_blank_values=True).get(
                "url", []
            )
        except ValueError:
            raise _unsafe() from None
        if len(embedded) != 1:
            raise _unsafe()
        return target_from_link(embedded[0], depth + 1)
    if parts.hostname == API_HOST and not parts.query and parts.path.startswith(API_PREFIX):
        name = parts.path.removeprefix(API_PREFIX)
        if _OBJECT.fullmatch(name):
            return DownloadTarget(name)
    raise _unsafe()


def validate_hop(url: str, target: DownloadTarget, *, storage_allowed: bool) -> None:
    parts = _parts(url)
    if parts.hostname == STORAGE_HOST:
        if (
            storage_allowed
            and not parts.query
            and parts.path == STORAGE_PREFIX + target.object_name
        ):
            return
        raise _unsafe()
    if target_from_link(url) != target:
        raise _unsafe()


def _public_host(host: str) -> None:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise _unsafe()
    except (OSError, ValueError):
        raise CollectionError(
            "network", "Could not resolve the export service. Check your connection."
        ) from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class ExportDownloader:
    def __init__(self, *, opener=None, resolve_host=None, deadline_seconds: float = 90) -> None:
        self._opener = opener if opener is not None else build_opener(_NoRedirect())
        self._resolve_host = resolve_host if resolve_host is not None else _public_host
        self._deadline_seconds = deadline_seconds
        self._pending: Future | None = None

    def _network_call(self, operation: Callable[[], Any], stop: Event, deadline: float) -> Any:
        """Bound DNS/open waits, closing late responses and limiting outstanding work.

        System DNS calls cannot be forcibly cancelled by Python. At most one such
        call can remain outstanding per downloader; it never writes a staging file.
        """
        if self._pending is not None and not self._pending.done():
            raise CollectionError(
                "network_pending",
                "An earlier network operation is still finishing. "
                "Check the connection and retry later.",
            )
        self._checkpoint(stop, deadline)
        future: Future = Future()
        self._pending = future
        ready = Event()

        def run() -> None:
            try:
                future.set_result(operation())
            except Exception as error:
                future.set_exception(error)
            finally:
                ready.set()

        def discard_late_result(completed: Future) -> None:
            try:
                result = completed.result()
                if result is not None and hasattr(result, "close"):
                    result.close()
            except Exception:
                pass

        Thread(target=run, daemon=True).start()
        operation_deadline = min(deadline, monotonic() + 5)
        try:
            while not ready.wait(0.05):
                self._checkpoint(stop, operation_deadline)
            self._checkpoint(stop, operation_deadline)
            return future.result()
        except Exception:
            future.add_done_callback(discard_late_result)
            raise

    def _open(self, url: str, timeout: float):
        try:
            return self._opener.open(
                Request(
                    url,
                    headers={
                        "User-Agent": "SmaxTec-Workbench",
                        "Accept-Encoding": "identity",
                    },
                ),
                timeout=timeout,
            )
        except HTTPError as error:
            # Inspect redirects/statuses without following them automatically.
            return error

    def download(self, url: str, destination: Path, stop: Event) -> str:
        """Write a newly reserved staging file, returning its SHA-256; no automatic retries."""
        deadline = monotonic() + self._deadline_seconds
        storage_allowed = False
        created = False
        try:
            self._checkpoint(stop, deadline)
            target = target_from_link(url)
            for _hop in range(6):
                self._checkpoint(stop, deadline)
                validate_hop(url, target, storage_allowed=storage_allowed)
                parts = _parts(url)
                self._network_call(partial(self._resolve_host, parts.hostname), stop, deadline)
                self._checkpoint(stop, deadline)
                timeout = min(5, deadline - monotonic())
                response = self._network_call(partial(self._open, url, timeout), stop, deadline)
                with response:
                    status = response.code
                    if status in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise _unsafe()
                        storage_allowed = parts.hostname in (API_HOST, STORAGE_HOST)
                        url = urljoin(url, location)
                        continue
                    if status != 200:
                        raise CollectionError(
                            "link_unavailable",
                            "The export link is unavailable or access was denied. "
                            "Links expire after "
                            "24 hours; check the email or request a fresh export if necessary.",
                        )
                    # An interstitial is not a file. Never continue past a Safe Links warning.
                    if parts.hostname != STORAGE_HOST and parts.hostname != API_HOST:
                        raise CollectionError(
                            "link_protection",
                            "Microsoft link protection needs attention. Check the link in Outlook; "
                            "Workbench will not bypass a security warning.",
                        )
                    media = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    if media.startswith("text/") or media in (
                        "application/xhtml+xml",
                        "application/json",
                        "application/xml",
                    ):
                        raise CollectionError(
                            "not_workbook", "The link returned a web page, not an Excel export."
                        )
                    length_text = response.headers.get("Content-Length")
                    if length_text is not None and not re.fullmatch(r"[0-9]{1,12}", length_text):
                        raise CollectionError(
                            "download_headers", "The server returned invalid download metadata."
                        )
                    length = int(length_text) if length_text is not None else None
                    if length is not None and not 0 < length <= MAX_DOWNLOAD_BYTES:
                        raise CollectionError(
                            "download_size", "The export exceeds the 100 MiB download limit."
                        )
                    digest = hashlib.sha256()
                    size = 0
                    signature = bytearray()
                    expected_signature = b"PK\x03\x04"
                    with destination.open("xb") as output:
                        created = True
                        while True:
                            self._checkpoint(stop, deadline)
                            chunk = response.read1(64 * 1024)
                            self._checkpoint(stop, deadline)
                            if not chunk:
                                break
                            if len(signature) < len(expected_signature):
                                signature.extend(chunk[: len(expected_signature) - len(signature)])
                            if signature != expected_signature[: len(signature)]:
                                raise CollectionError(
                                    "not_workbook", "The link did not return an XLSX workbook."
                                )
                            size += len(chunk)
                            if size > MAX_DOWNLOAD_BYTES:
                                raise CollectionError(
                                    "download_size",
                                    "The export exceeds the 100 MiB download limit.",
                                )
                            output.write(chunk)
                            digest.update(chunk)
                        if len(signature) < 4 or (length is not None and size != length):
                            raise CollectionError(
                                "incomplete_download",
                                "The download was interrupted. Retry this collection.",
                            )
                        output.flush()
                        os.fsync(output.fileno())
                    self._checkpoint(stop, deadline)
                    return digest.hexdigest()
            raise CollectionError("redirect_limit", "The export link redirected too many times.")
        except (
            CollectionError,
            CollectionCancelled,
            OSError,
            URLError,
            ValueError,
            HTTPException,
        ) as error:
            if created:
                try:
                    destination.unlink(missing_ok=True)
                except OSError:
                    raise CollectionError(
                        "download_cleanup",
                        "The download failed and its incomplete staging file could not be removed. "
                        "It has not been accepted as a workbook; "
                        "check folder access before retrying.",
                    ) from None
            if isinstance(error, CollectionError | CollectionCancelled):
                raise
            raise CollectionError(
                "download_failed",
                "The download could not finish. "
                "Check your connection, folder access and available space.",
            ) from None

    @staticmethod
    def _checkpoint(stop: Event, deadline: float) -> None:
        if stop.is_set():
            raise CollectionCancelled()
        if monotonic() >= deadline:
            raise CollectionError(
                "download_timeout", "The download timed out. Retry this collection when ready."
            )
