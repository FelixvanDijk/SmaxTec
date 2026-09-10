"""Read saved emails/Outlook message values as data; never render HTML or fetch images."""

import hashlib
import re
from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE
from datetime import UTC, datetime
from email import policy
from email.message import Message
from email.parser import BytesParser, Parser
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from struct import unpack_from
from threading import Event
from urllib.parse import parse_qs, unquote, urlsplit

from smaxtec.adapters.mail.downloads import API_HOST, API_PREFIX, target_from_link
from smaxtec.application.collection import (
    CollectionCancelled,
    CollectionError,
    MailCandidate,
    MailMessage,
    MailScan,
)

MAX_EMAIL_BYTES = 15 * 1024 * 1024
MAX_BODY_CHARS = 4 * 1024 * 1024
MAX_MIME_PARTS = 200
MAX_HTML_LINKS = 2000


def safe_text(value: str, limit: int = 200) -> str:
    # Subjects are untrusted too: don't propagate bearer links through UI/diagnostics.
    text = re.sub(r"https?://\S+", "[link hidden]", str(value), flags=re.I)
    text = re.sub(r"export-[a-zA-Z0-9_.-]{1,180}\.xlsx", "[export hidden]", text, flags=re.I)
    return " ".join(text.split())[:limit]


class _EmailHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.words: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._ignored += 1
        if self._ignored:
            return
        if tag == "a":
            hrefs = [value for name, value in attrs if name == "href"]
            if len(set(hrefs)) > 1:
                raise CollectionError(
                    "message_complex",
                    "This email has an ambiguous link. Save it again from Outlook.",
                )
            href = hrefs[0] if hrefs else None
            if href:
                if len(self.links) >= MAX_HTML_LINKS:
                    raise CollectionError(
                        "message_complex", "This email contains too many links to inspect safely."
                    )
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._ignored:
            self._ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.words.append(data)


def _wrapper_depth(url: str) -> int:
    """Only called after target_from_link validated the complete wrapper chain."""
    for depth in range(6):
        parts = urlsplit(url)
        if not (parts.hostname or "").endswith(".safelinks.protection.outlook.com"):
            return depth
        url = parse_qs(parts.query, max_num_fields=20)["url"][0]
    return 6


def _unverified_protected_export(url: str) -> bool:
    """Do not fall back to a raw href when its protected companion is malformed."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return False
    if not re.fullmatch(r"[a-z0-9-]+\.safelinks\.protection\.outlook\.com", host, re.ASCII):
        return False
    value = url
    for _ in range(6):
        value = unquote(value)
    return API_HOST + API_PREFIX in value.casefold()


def candidate_from_message(message: MailMessage) -> MailCandidate | None:
    if len(message.html_body) + len(message.text_body) > MAX_BODY_CHARS:
        raise CollectionError("message_large", "An email body exceeded the safe parsing limit.")
    parser = _EmailHTML()
    parser.feed(message.html_body)
    parser.close()
    sender = parseaddr(message.sender)[1].casefold()
    text = " ".join((message.subject, message.text_body, *parser.words)).casefold()
    relevant = "excel export file" in text and (
        "smaxtec" in text or sender == "noreply@smaxtec.com"
    )
    if not relevant:
        return None
    # Prefer HTML hrefs: plain-text alternatives may expose the unwrapped destination.
    links = (
        parser.links
        if message.html_body
        else re.findall(r'https://[^\s<>"\x00-\x20]+', message.text_body)
    )
    found: dict[str, str] = {}
    unverified_protection = False
    for url in links:
        try:
            target = target_from_link(url)
        except (CollectionError, ValueError):
            unverified_protection |= _unverified_protected_export(url)
            continue
        previous = found.get(target.fingerprint)
        # Both direct and protected hrefs may occur in forwarded conversation
        # history. Never choose the direct version just because it appeared first.
        if previous is None or _wrapper_depth(url) > _wrapper_depth(previous):
            found[target.fingerprint] = url
    issue = ""
    fingerprint = url = ""
    if unverified_protection:
        issue = "A protected export link could not be verified. Check the email in Outlook."
    elif len(found) > 1:
        issue = "Multiple different export links: save a separate email for each export."
    elif not found:
        issue = "No supported download link found. Check the email or save it as EML."
    else:
        fingerprint, url = next(iter(found.items()))
    return MailCandidate(
        message.key,
        safe_text(message.subject),
        safe_text(parseaddr(message.sender)[1] or message.sender),
        message.received_at,
        "direct" if sender == "noreply@smaxtec.com" else "forwarded",
        url,
        fingerprint,
        issue,
    )


def _date(value, fallback: datetime) -> datetime:
    try:
        result = value if isinstance(value, datetime) else parsedate_to_datetime(str(value))
        return result.astimezone(UTC) if result.tzinfo else result.replace(tzinfo=UTC)
    except (ValueError, TypeError, OverflowError):
        return fallback


def _read_eml(raw: bytes, key: str, fallback: datetime) -> MailMessage:
    mail = BytesParser(policy=policy.default).parsebytes(raw)
    html_parts = []
    text_parts = []
    size = 0
    for part in _body_parts(mail):
        if part.get_content_type() == "text/html":
            body = part.get_content()
            html_parts.append(body)
        elif part.get_content_type() == "text/plain":
            body = part.get_content()
            text_parts.append(body)
        else:
            continue
        size += len(body)
        if size > MAX_BODY_CHARS:
            raise CollectionError("message_large", "An email body exceeded the safe parsing limit.")
    return MailMessage(
        key,
        str(mail.get("Subject", "")),
        str(mail.get("From", "")),
        _date(mail.get("Date"), fallback),
        "\n".join(html_parts),
        "\n".join(text_parts),
    )


def _body_parts(mail: Message):
    """Do not descend into attached/nested messages, unlike email.walk()."""
    pending = [mail]
    visited = 0
    while pending:
        part = pending.pop()
        visited += 1
        if visited > MAX_MIME_PARTS:
            raise CollectionError(
                "message_complex", "This saved email has too many parts to inspect safely."
            )
        if (
            part.get_content_disposition() == "attachment"
            or part.get_filename()
            or part.get_content_maintype() == "message"
        ):
            continue
        if part.is_multipart():
            pending.extend(reversed(part.get_payload()))
        else:
            yield part


def _codepage_encoding(value: int) -> str:
    known = {1200: "utf-16-le", 1201: "utf-16-be", 20127: "ascii", 65001: "utf-8"}
    if 28591 <= value <= 28599:
        return "iso-8859-" + str(value - 28590)
    return known.get(value, f"cp{value}")


class _MsgStreams:
    """Read known root message streams only, never attachment storages or RTF."""

    def __init__(self, container) -> None:
        self.container = container
        self.properties: dict[int, int] = {}
        properties = self.binary("__properties_version1.0")
        if properties:
            if len(properties) < 32 or (len(properties) - 32) % 16:
                raise ValueError("Unsupported root message properties")
            for offset in range(32, len(properties), 16):
                tag = unpack_from("<I", properties, offset)[0]
                if tag in (0x3FFD0003, 0x3FDE0003):
                    if tag in self.properties:
                        raise ValueError("Ambiguous root message codepage")
                    self.properties[tag] = unpack_from("<I", properties, offset + 8)[0]

    def binary(self, name: str, limit: int | None = None) -> bytes:
        if limit is None:
            limit = MAX_BODY_CHARS
        if not self.container.exists([name]):
            return b""
        if self.container.get_size([name]) > limit:
            raise CollectionError("message_large", "An email body exceeded the safe parsing limit.")
        with self.container.openstream([name]) as source:
            result = source.read(limit + 1)
        if len(result) > limit:
            raise CollectionError("message_large", "An email body exceeded the safe parsing limit.")
        return result

    def text(self, base: str) -> str:
        if self.container.exists([base + "001F"]):
            return self.binary(base + "001F", MAX_BODY_CHARS * 2).decode("utf-16-le").rstrip("\0")
        encoding = _codepage_encoding(self.properties.get(0x3FFD0003, 1252))
        return self.binary(base + "001E").decode(encoding).rstrip("\0")


def _decode_msg_html(raw: bytes, mail: _MsgStreams) -> str:
    if not raw:
        return ""
    if raw.startswith((BOM_UTF16_LE, BOM_UTF16_BE)):
        return raw.decode("utf-16")
    if raw.startswith(BOM_UTF8):
        return raw.decode("utf-8-sig")
    if raw.startswith(b"<\x00"):
        return raw.decode("utf-16-le")
    if raw.startswith(b"\x00<"):
        return raw.decode("utf-16-be")
    declared = re.search(rb'charset\s*=\s*["\']?([a-zA-Z0-9_-]+)', raw[:8192], re.I)
    if declared:
        encoding = declared[1].decode("ascii")
    elif codepage := mail.properties.get(0x3FDE0003):
        encoding = _codepage_encoding(codepage)
    else:
        encoding = "utf-8"
    # Decode strictly: a guessed/replaced URL could name a different resource.
    # read_saved_email converts unsupported encodings into its curated EML hint.
    return raw.decode(encoding)


def _read_msg(raw: bytes, key: str, fallback: datetime) -> MailMessage:
    import olefile

    with (
        BytesIO(raw) as source,
        olefile.OleFileIO(source, raise_defects=olefile.DEFECT_INCORRECT) as ole,
    ):
        mail = _MsgStreams(ole)
        # Read existing body streams, never generate HTML or de-encapsulate RTF.
        # Attachment forwards/RTF-only messages get an explicit unsupported-link result.
        html = mail.binary("__substg1.0_10130102")
        if len(html) > MAX_BODY_CHARS:
            raise CollectionError("message_large", "An email body exceeded the safe parsing limit.")
        header_text = mail.text("__substg1.0_007D")
        body = mail.text("__substg1.0_1000")
        if len(html) + len(body) > MAX_BODY_CHARS or len(header_text) > MAX_BODY_CHARS:
            raise CollectionError("message_large", "An email body exceeded the safe parsing limit.")
        headers = Parser(policy=policy.default).parsestr(header_text)
        sender = str(headers.get("From", "")) or mail.text("__substg1.0_5D01")
        return MailMessage(
            key,
            mail.text("__substg1.0_0037"),
            sender,
            _date(headers.get("Date"), fallback),
            _decode_msg_html(html, mail),
            body,
        )


def read_saved_email(path: Path) -> MailMessage:
    try:
        size = path.stat().st_size
        if not 0 < size <= MAX_EMAIL_BYTES:
            raise CollectionError("message_large", "Saved emails must be smaller than 15 MiB.")
        with path.open("rb") as source:
            raw = source.read(MAX_EMAIL_BYTES + 1)
        if len(raw) > MAX_EMAIL_BYTES:
            raise CollectionError("message_large", "Saved emails must be smaller than 15 MiB.")
        key = "saved:" + hashlib.sha256(raw).hexdigest()
        fallback = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if path.suffix.casefold() == ".eml":
            return _read_eml(raw, key, fallback)
        if path.suffix.casefold() == ".msg" and raw.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return _read_msg(raw, key, fallback)
        raise CollectionError("message_format", "Choose an Outlook email saved as EML or MSG.")
    except CollectionError:
        raise
    except Exception:
        raise CollectionError(
            "message_invalid", "A saved email could not be read. Try saving it as EML in Outlook."
        ) from None


def import_emails(paths: tuple[Path, ...], stop: Event) -> MailScan:
    if not 1 <= len(paths) <= 1000:
        raise CollectionError("selection_size", "Select between 1 and 1,000 saved emails.")
    candidates = []
    skipped = 0
    for path in paths:
        if stop.is_set():
            raise CollectionCancelled()
        candidate = candidate_from_message(read_saved_email(path))
        if candidate is None:
            skipped += 1
        else:
            candidates.append(candidate)
    warning = (
        "Manual file selection, not the newest Inbox messages. Dates are from the email header "
        "(file time if unavailable), not verified Inbox arrival times."
    )
    if skipped:
        warning += f" {skipped} selected file(s) were not recognized as export emails."
    return MailScan(tuple(candidates), len(paths), warning)
