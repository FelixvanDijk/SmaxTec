"""Downloader regressions are entirely synthetic: no live DNS, email or HTTP access."""

import hashlib
import io
import socket
from email.message import Message
from http.client import BadStatusLine, IncompleteRead, RemoteDisconnected
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from zipfile import ZipFile

import pytest

from smaxtec.adapters.mail import downloads
from smaxtec.application.collection import CollectionCancelled, CollectionError

OBJECT = "export-synthetic-a.xlsx"
API = "https://api.smaxtec.com/api/v2/data/downloads/" + OBJECT
STORAGE = "https://storage.googleapis.com/anthilldata_excel_exports/" + OBJECT
SAFE_ROOT = "https://eur01.safelinks.protection.outlook.com/"


def protected(url=API):
    return SAFE_ROOT + "?" + urlencode({"url": url, "data": "synthetic-private-token"})


@pytest.fixture
def workbook_bytes():
    archive = io.BytesIO()
    with ZipFile(archive, "w") as package:
        package.writestr("[Content_Types].xml", "<Types>synthetic</Types>")
    return archive.getvalue()


class FakeResponse:
    def __init__(self, chunks=(), *, status=200, headers=None, on_read=None):
        self.code = status
        self.headers = headers or {}
        self.chunks = iter(chunks)
        self.closed = Event()
        self.on_read = on_read
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.closed.set()

    def read1(self, maximum):
        self.reads += 1
        if self.on_read:
            self.on_read(self.reads)
        value = next(self.chunks, b"")
        if isinstance(value, Exception):
            raise value
        assert len(value) <= maximum
        return value


class FakeOpener:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def downloader(*responses, **kwargs):
    opener = FakeOpener(*responses)
    resolved = []
    client = downloads.ExportDownloader(opener=opener, resolve_host=resolved.append, **kwargs)
    return client, opener, resolved


def test_safe_links_classification_preserves_target_and_redacts_repr():
    target = downloads.target_from_link(API)
    assert downloads.target_from_link(protected()) == target
    assert target.fingerprint == hashlib.sha256(OBJECT.encode()).hexdigest()
    assert OBJECT not in repr(target)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.smaxtec.com/api/v2/data/downloads/" + OBJECT,
        "file:///private.xlsx",
        "ftp://api.smaxtec.com/export.xlsx",
        API + "#fragment",
        API + "?unverified=1",
        API.replace("api.smaxtec.com", "user:password@api.smaxtec.com"),
        API.replace("api.smaxtec.com", "api.smaxtec.com:444"),
        API.replace("api.smaxtec.com", "api.smaxtec.com.evil.invalid"),
        API.replace("api.smaxtec.com", "127.0.0.1"),
        API.replace("api.smaxtec.com", "[::1]"),
        API.replace("api.smaxtec.com", "localhost"),
        API.replace(OBJECT, "%2e%2e%2fprivate.xlsx"),
        API.replace(OBJECT, "../" + OBJECT),
        API.replace(OBJECT, "export-a.xlsm"),
        API.replace(OBJECT, "export-a.xlsx/other"),
        API + "\n",
        API + "\x7f",
        API + "\\evil",
        STORAGE,
        SAFE_ROOT + "?url=",
        SAFE_ROOT + "?" + urlencode([("url", API), ("url", API)]),
        SAFE_ROOT + "?" + urlencode([("url", API), ("url", "")]),
        protected().replace("eur01.safelinks.protection.outlook.com", "safelinks.evil.invalid"),
        protected("https://untrusted.invalid/export.xlsx"),
        "https://[malformed/",
        "https://api.smaxtec.com:invalid/",
        "https://api.smaxtec.com/" + "x" * 17000,
    ],
)
def test_unverified_targets_are_curated_and_never_opened(url, tmp_path):
    client, opener, resolved = downloader()
    with pytest.raises(CollectionError) as error:
        client.download(url, tmp_path / "staging.part", Event())
    assert error.value.code == "unsafe_link"
    assert "synthetic-private-token" not in str(error.value)
    assert not opener.calls and not resolved
    assert not list(tmp_path.iterdir())


def test_safe_links_field_limit_raises_only_curated_error():
    url = SAFE_ROOT + "?" + urlencode([("url", API)] + [(f"x{i}", "v") for i in range(21)])
    with pytest.raises(CollectionError) as error:
        downloads.target_from_link(url)
    assert error.value.code == "unsafe_link"


def test_safe_links_nesting_is_bounded():
    url = API
    for _ in range(4):
        url = protected(url)
    assert downloads.target_from_link(url) == downloads.target_from_link(API)
    with pytest.raises(CollectionError):
        downloads.target_from_link(protected(url))


def test_fetches_safe_links_then_verified_api_then_exact_storage(workbook_bytes, tmp_path):
    first = FakeResponse(status=302, headers={"Location": API})
    second = FakeResponse(status=307, headers={"Location": STORAGE})
    third = FakeResponse(
        [workbook_bytes],
        headers={
            "Content-Length": str(len(workbook_bytes)),
            "Content-Disposition": 'attachment; filename="../../untrusted.xlsx"',
        },
    )
    client, opener, resolved = downloader(first, second, third)
    path = tmp_path / "staging.part"
    digest = client.download(protected(), path, Event())
    assert path.read_bytes() == workbook_bytes
    assert digest == hashlib.sha256(workbook_bytes).hexdigest()
    assert [request.full_url for request, _ in opener.calls] == [protected(), API, STORAGE]
    assert resolved == [
        "eur01.safelinks.protection.outlook.com",
        "api.smaxtec.com",
        "storage.googleapis.com",
    ]
    for request, timeout in opener.calls:
        assert request.get_method() == "GET"
        assert request.get_header("Authorization") is None
        assert request.get_header("Cookie") is None
        assert request.get_header("Referer") is None
        assert request.get_header("Accept-encoding") == "identity"
        assert 0 < timeout <= 5
    assert all(response.closed.is_set() for response in (first, second, third))
    assert [item.name for item in tmp_path.iterdir()] == ["staging.part"]


@pytest.mark.parametrize("first_chunk_size", [1, 2, 3, 4])
def test_partial_zip_signature_reads_are_accumulated(workbook_bytes, tmp_path, first_chunk_size):
    chunks = [workbook_bytes[:first_chunk_size]]
    chunks.extend(bytes([byte]) for byte in workbook_bytes[first_chunk_size:])
    response = FakeResponse(chunks)
    client, _, _ = downloader(response)
    path = tmp_path / "partial-signature.part"
    assert client.download(API, path, Event()) == hashlib.sha256(workbook_bytes).hexdigest()
    assert path.read_bytes() == workbook_bytes


@pytest.mark.parametrize("chunks", [[b""], [b"P"], [b"P", b"K"], [b"PK\x03"]])
def test_truncated_signature_is_incomplete_and_removed(tmp_path, chunks):
    client, _, _ = downloader(FakeResponse(chunks))
    path = tmp_path / "short.part"
    with pytest.raises(CollectionError) as error:
        client.download(API, path, Event())
    assert error.value.code == "incomplete_download"
    assert not path.exists()


@pytest.mark.parametrize("data", [b"<html>login</html>", b'{"error":1}', b"PKbad", b"PK\x05\x06"])
def test_non_xlsx_signature_is_rejected_without_type_header(tmp_path, data):
    client, _, _ = downloader(FakeResponse([data]))
    path = tmp_path / "invalid.part"
    with pytest.raises(CollectionError) as error:
        client.download(API, path, Event())
    assert error.value.code == "not_workbook"
    assert not path.exists()


@pytest.mark.parametrize(
    "media", ["text/html", "Text/HTML; charset=utf-8", "text/plain", "application/json"]
)
def test_webpage_response_rejected_before_creating_file(workbook_bytes, tmp_path, media):
    response = FakeResponse([workbook_bytes], headers={"Content-Type": media})
    client, _, _ = downloader(response)
    with pytest.raises(CollectionError) as error:
        client.download(API, tmp_path / "webpage.part", Event())
    assert error.value.code == "not_workbook"
    assert response.reads == 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("status", [401, 403, 404, 410, 429, 500, 503])
def test_unavailable_link_is_not_retried_or_assumed_expired(tmp_path, status):
    response = FakeResponse(status=status)
    client, opener, _ = downloader(response)
    with pytest.raises(CollectionError) as error:
        client.download(API, tmp_path / "failed.part", Event())
    assert error.value.code == "link_unavailable"
    assert "unavailable or access was denied" in str(error.value)
    assert len(opener.calls) == 1
    assert response.closed.is_set()
    assert not list(tmp_path.iterdir())


def test_safe_links_interstitial_is_never_bypassed(tmp_path):
    response = FakeResponse([b"<html>warning</html>"])
    client, opener, _ = downloader(response)
    with pytest.raises(CollectionError) as error:
        client.download(protected(), tmp_path / "protected.part", Event())
    assert error.value.code == "link_protection"
    assert [request.full_url for request, _ in opener.calls] == [protected()]
    assert response.reads == 0


@pytest.mark.parametrize(
    "destination",
    [
        "http://storage.googleapis.com/anthilldata_excel_exports/" + OBJECT,
        STORAGE.replace(OBJECT, "export-synthetic-b.xlsx"),
        STORAGE.replace("anthilldata_excel_exports", "unverified_bucket"),
        STORAGE + "?signature=unverified",
        STORAGE.replace("storage.googleapis.com", "storage.googleapis.com.evil.invalid"),
        API.replace(OBJECT, "export-synthetic-b.xlsx"),
        "https://169.254.169.254/private",
        "https://127.0.0.1/private",
        "//untrusted.invalid/private",
        "file:///private.xlsx",
    ],
)
def test_every_redirect_is_validated_before_network(tmp_path, destination):
    response = FakeResponse(status=302, headers={"Location": destination})
    client, opener, resolved = downloader(response)
    with pytest.raises(CollectionError) as error:
        client.download(API, tmp_path / "redirect.part", Event())
    assert error.value.code == "unsafe_link"
    assert len(opener.calls) == 1
    assert resolved == ["api.smaxtec.com"]
    assert response.closed.is_set()


def test_safe_links_cannot_skip_api_to_storage(tmp_path):
    client, opener, _ = downloader(FakeResponse(status=302, headers={"Location": STORAGE}))
    with pytest.raises(CollectionError) as error:
        client.download(protected(), tmp_path / "skip.part", Event())
    assert error.value.code == "unsafe_link"
    assert len(opener.calls) == 1


def test_redirect_limit_has_no_retries(tmp_path):
    responses = [FakeResponse(status=302, headers={"Location": API}) for _ in range(6)]
    client, opener, _ = downloader(*responses)
    with pytest.raises(CollectionError) as error:
        client.download(API, tmp_path / "loop.part", Event())
    assert error.value.code == "redirect_limit"
    assert len(opener.calls) == 6
    assert all(response.closed.is_set() for response in responses)


def test_missing_redirect_location_is_curated(tmp_path):
    client, _, _ = downloader(FakeResponse(status=302))
    with pytest.raises(CollectionError) as error:
        client.download(API, tmp_path / "missing.part", Event())
    assert error.value.code == "unsafe_link"


def test_urllib_http_error_redirect_is_inspected(workbook_bytes, tmp_path):
    headers = Message()
    headers["Location"] = STORAGE
    error = HTTPError(API, 302, "synthetic private URL", headers, io.BytesIO())
    client, opener, _ = downloader(error, FakeResponse([workbook_bytes]))
    path = tmp_path / "http-error.part"
    client.download(API, path, Event())
    assert path.read_bytes() == workbook_bytes
    assert len(opener.calls) == 2


@pytest.mark.parametrize("value", ["invalid", "-1", "+100", "1, 2", "1.5", "", "9" * 30])
def test_malformed_length_is_sanitized_before_file_creation(tmp_path, value):
    client, _, _ = downloader(FakeResponse(headers={"Content-Length": value}))
    with pytest.raises(CollectionError) as error:
        client.download(API, tmp_path / "headers.part", Event())
    assert error.value.code == "download_headers"
    assert not list(tmp_path.iterdir())


def test_declared_oversize_rejected_before_read(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads, "MAX_DOWNLOAD_BYTES", 8)
    response = FakeResponse(headers={"Content-Length": "9"})
    client, _, _ = downloader(response)
    with pytest.raises(CollectionError) as error:
        client.download(API, tmp_path / "oversize.part", Event())
    assert error.value.code == "download_size"
    assert response.reads == 0


def test_undeclared_oversize_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads, "MAX_DOWNLOAD_BYTES", 8)
    client, _, _ = downloader(FakeResponse([b"PK\x03\x04", b"12345"]))
    path = tmp_path / "oversize.part"
    with pytest.raises(CollectionError) as error:
        client.download(API, path, Event())
    assert error.value.code == "download_size"
    assert not path.exists()


def test_content_length_mismatch_removed(workbook_bytes, tmp_path):
    response = FakeResponse(
        [workbook_bytes], headers={"Content-Length": str(len(workbook_bytes) + 1)}
    )
    client, _, _ = downloader(response)
    path = tmp_path / "mismatch.part"
    with pytest.raises(CollectionError) as error:
        client.download(API, path, Event())
    assert error.value.code == "incomplete_download"
    assert not path.exists()


@pytest.mark.parametrize(
    "failure",
    [
        BadStatusLine("secret URL"),
        IncompleteRead(b"secret"),
        RemoteDisconnected("secret"),
        URLError("secret"),
    ],
)
def test_network_and_http_protocol_errors_are_sanitized_without_retry(tmp_path, failure):
    response = FakeResponse([b"PK\x03\x04", failure])
    client, opener, _ = downloader(response)
    path = tmp_path / "broken.part"
    with pytest.raises(CollectionError) as error:
        client.download(API, path, Event())
    assert error.value.code == "download_failed"
    assert "secret" not in str(error.value)
    assert len(opener.calls) == 1
    assert response.closed.is_set()
    assert not path.exists()


def test_open_protocol_failure_is_sanitized(tmp_path):
    client, opener, _ = downloader(BadStatusLine("secret download address"))
    with pytest.raises(CollectionError) as error:
        client.download(API, tmp_path / "bad-status.part", Event())
    assert error.value.code == "download_failed"
    assert "secret" not in str(error.value)
    assert len(opener.calls) == 1


def test_existing_destination_is_never_changed_or_deleted(tmp_path, workbook_bytes):
    path = tmp_path / "existing.part"
    path.write_bytes(b"existing-user-data")
    client, _, _ = downloader(FakeResponse([workbook_bytes]))
    with pytest.raises(CollectionError):
        client.download(API, path, Event())
    assert path.read_bytes() == b"existing-user-data"


def test_cancel_before_download_does_no_network(tmp_path):
    stop = Event()
    stop.set()
    client, opener, resolved = downloader()
    with pytest.raises(CollectionCancelled):
        client.download(API, tmp_path / "cancel.part", stop)
    assert not opener.calls and not resolved


def test_cancel_during_read_removes_partial_and_closes_response(tmp_path):
    stop = Event()
    response = FakeResponse(
        [b"PK\x03\x04", b"more"], on_read=lambda n: stop.set() if n == 2 else None
    )
    client, _, _ = downloader(response)
    path = tmp_path / "cancel.part"
    with pytest.raises(CollectionCancelled):
        client.download(API, path, stop)
    assert not path.exists()
    assert response.closed.is_set()


def test_timeout_after_read_removes_partial(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(downloads, "monotonic", lambda: clock[0])
    response = FakeResponse([b"PK\x03\x04"], on_read=lambda _: clock.__setitem__(0, 100.0))
    client, _, _ = downloader(response)
    path = tmp_path / "timeout.part"
    with pytest.raises(CollectionError) as error:
        client.download(API, path, Event())
    assert error.value.code == "download_timeout"
    assert not path.exists()


def test_cancel_during_open_closes_late_response_and_prevents_new_requests(tmp_path):
    stop = Event()
    release = Event()
    response = FakeResponse()
    calls = []

    class BlockedOpener:
        def open(self, request, timeout):
            calls.append(request)
            stop.set()
            release.wait(2)
            return response

    client = downloads.ExportDownloader(opener=BlockedOpener(), resolve_host=lambda _: None)
    try:
        with pytest.raises(CollectionCancelled):
            client.download(API, tmp_path / "cancel-open.part", stop)
        with pytest.raises(CollectionError) as error:
            client.download(API, tmp_path / "next.part", Event())
        assert error.value.code == "network_pending"
        assert len(calls) == 1
    finally:
        release.set()
    assert response.closed.wait(1)
    assert not list(tmp_path.iterdir())


def test_stalled_dns_is_bounded_without_starting_http(tmp_path):
    release = Event()
    opener = FakeOpener()

    def blocked_resolver(_):
        release.wait(2)

    client = downloads.ExportDownloader(
        opener=opener, resolve_host=blocked_resolver, deadline_seconds=0.02
    )
    try:
        with pytest.raises(CollectionError) as error:
            client.download(API, tmp_path / "dns.part", Event())
        assert error.value.code == "download_timeout"
        assert not opener.calls
    finally:
        release.set()


def test_cleanup_failure_is_curated_and_partial_never_accepted(tmp_path, monkeypatch):
    client, _, _ = downloader(FakeResponse([b"PK\x03\x04", OSError("secret")]))
    path = tmp_path / "cleanup.part"
    original_unlink = type(path).unlink

    def fail_unlink(self, *args, **kwargs):
        if self == path:
            raise PermissionError("private path")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "unlink", fail_unlink)
    with pytest.raises(CollectionError) as error:
        client.download(API, path, Event())
    assert error.value.code == "download_cleanup"
    assert "private" not in str(error.value)
    assert path.exists()


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fe80::1", "0.0.0.0"]
)
def test_private_dns_answers_are_rejected(monkeypatch, address):
    monkeypatch.setattr(
        downloads.socket, "getaddrinfo", lambda *_args, **_kwargs: [(0, 0, 0, "", (address, 443))]
    )
    with pytest.raises(CollectionError) as error:
        downloads._public_host("api.smaxtec.com")
    assert error.value.code == "unsafe_link"


def test_mixed_public_private_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(
        downloads.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (0, 0, 0, "", ("8.8.8.8", 443)),
            (0, 0, 0, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(CollectionError):
        downloads._public_host("api.smaxtec.com")


def test_dns_failure_is_curated(monkeypatch):
    def failure(*_args, **_kwargs):
        raise socket.gaierror("private host resolution details")

    monkeypatch.setattr(downloads.socket, "getaddrinfo", failure)
    with pytest.raises(CollectionError) as error:
        downloads._public_host("api.smaxtec.com")
    assert error.value.code == "network"
    assert "private" not in str(error.value)


def test_default_redirect_handler_never_auto_follows():
    assert downloads._NoRedirect().redirect_request(None, None, None, None, None, None) is None
