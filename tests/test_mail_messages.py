"""Synthetic saved-email and candidate tests; never fetch links or access mailboxes."""

from datetime import UTC, datetime
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from struct import pack
from threading import Event
from urllib.parse import quote

import pytest

from smaxtec.adapters.mail import messages
from smaxtec.adapters.mail.messages import (
    candidate_from_message,
    import_emails,
    read_saved_email,
    safe_text,
)
from smaxtec.application.collection import CollectionCancelled, CollectionError, MailMessage

LINK = "https://api.smaxtec.com/api/v2/data/downloads/export-synthetic-first.xlsx"
OTHER_LINK = "https://api.smaxtec.com/api/v2/data/downloads/export-synthetic-second.xlsx"
TIME = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
MSG_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def protected(url=LINK):
    return "https://eur01.safelinks.protection.outlook.com/?url=" + quote(url, safe="")


def markup(*links):
    return "<p>smaXtec Excel export file successfully created</p>" + "".join(
        f'<a href="{link}">Download</a>' for link in links
    )


def message(
    *links, sender="smaXtec Web <noreply@smaxtec.com>", text="", subject="Excel export file"
):
    return MailMessage("synthetic", subject, sender, TIME, markup(*links), text)


def eml_file(tmp_path: Path, *, html=None, sender="noreply@smaxtec.com", name="source.eml"):
    mail = EmailMessage()
    mail["From"] = sender
    mail["Subject"] = "Excel export file successfully created"
    mail["Date"] = "Wed, 09 Sep 2026 13:00:00 +0100"
    mail.set_content("smaXtec Excel export file successfully created " + LINK)
    if html is not None:
        mail.add_alternative(html, subtype="html")
    path = tmp_path / name
    path.write_bytes(mail.as_bytes())
    return path, mail


def test_direct_sender_recognized_and_plain_text_parsed(tmp_path):
    path, _mail = eml_file(tmp_path)
    parsed = read_saved_email(path)
    result = candidate_from_message(parsed)
    assert result.kind == "direct"
    assert result.download_url == LINK
    assert result.received_at == TIME
    assert parsed.key.startswith("saved:")


def test_forwarded_html_link_recognized_without_trusting_outer_sender():
    candidate = candidate_from_message(message(LINK, sender="Person <person@example.test>"))
    assert candidate.kind == "forwarded"
    assert candidate.sender == "person@example.test"
    assert candidate.download_url == LINK


def test_sender_must_match_exactly_to_claim_direct():
    candidate = candidate_from_message(message(LINK, sender="noreply@smaxtec.com.attacker.test"))
    assert candidate.kind == "forwarded"
    candidate = candidate_from_message(
        MailMessage("k", "Excel export file", "noreply@smaxtec.com.attacker.test", TIME)
    )
    assert candidate is None


@pytest.mark.parametrize("links", [(LINK, protected()), (protected(), LINK)])
def test_same_export_duplicate_hrefs_always_preserve_safe_links_wrapper(links):
    candidate = candidate_from_message(message(*links))
    assert candidate.download_url == protected()
    assert not candidate.issue
    assert candidate.link_fingerprint == candidate_from_message(message(LINK)).link_fingerprint


def test_nested_safe_links_wrapper_is_not_unwrapped_for_download():
    outer = protected(protected())
    candidate = candidate_from_message(message(LINK, protected(), outer))
    assert candidate.download_url == outer


def test_invalid_protected_companion_does_not_allow_raw_link_fallback():
    malformed = protected() + "&url=" + quote(LINK, safe="")
    result = candidate_from_message(message(LINK, malformed))
    assert "protected" in result.issue
    assert not result.download_url
    assert not result.link_fingerprint


def test_unrelated_protected_footer_does_not_block_export():
    candidate = candidate_from_message(message(LINK, protected("https://www.example.test/help")))
    assert candidate.download_url == LINK
    assert not candidate.issue


def test_ambiguous_duplicate_href_attributes_fail_closed():
    email = MailMessage(
        "k",
        "Excel export file",
        "noreply@smaxtec.com",
        TIME,
        f'<a href="{protected()}" href="{LINK}">Download</a>',
    )
    with pytest.raises(CollectionError, match="ambiguous"):
        candidate_from_message(email)


def test_html_is_authoritative_not_unwrapped_plaintext_alternative(tmp_path):
    path, _mail = eml_file(tmp_path, html=markup(protected()))
    assert candidate_from_message(read_saved_email(path)).download_url == protected()
    path, _mail = eml_file(tmp_path, html="<p>smaXtec Excel export file: check Outlook</p>")
    result = candidate_from_message(read_saved_email(path))
    assert result.download_url == ""
    assert result.issue


def test_multiple_distinct_exports_are_ambiguous_not_arbitrarily_chosen():
    result = candidate_from_message(message(LINK, OTHER_LINK))
    assert "Multiple" in result.issue
    assert not result.download_url
    assert not result.link_fingerprint


@pytest.mark.parametrize(
    "unsafe",
    [
        "http://api.smaxtec.com/api/v2/data/downloads/export-synthetic.xlsx",
        "https://localhost/export-synthetic.xlsx",
        "https://api.smaxtec.com.attacker.test/api/v2/data/downloads/export-synthetic.xlsx",
        "javascript:alert('private')",
        "file:///private.xlsx",
        "https://api.smaxtec.com/api/v2/data/downloads/export-synthetic.xlsx?unexpected=secret",
    ],
)
def test_unsafe_links_fail_without_exposing_the_address(unsafe):
    result = candidate_from_message(message(unsafe))
    assert result.issue
    assert result.download_url == ""
    assert unsafe not in repr(result)


def test_unrelated_email_is_not_selected_and_html_is_not_rendered():
    email = MailMessage(
        "k",
        "Unrelated",
        "person@example.test",
        TIME,
        '<img src="https://private.test/track"><script>smaXtec Excel export file</script>',
    )
    assert candidate_from_message(email) is None


def test_nested_attachment_content_never_becomes_outer_message_body(tmp_path):
    path, outer = eml_file(tmp_path, html=markup(LINK))
    attached = EmailMessage()
    attached["From"] = "noreply@smaxtec.com"
    attached["Subject"] = "Excel export file"
    attached.set_content(markup(OTHER_LINK), subtype="html")
    outer.add_attachment(attached, filename="forwarded.eml")
    path.write_bytes(outer.as_bytes())
    parsed = read_saved_email(path)
    assert OTHER_LINK not in parsed.html_body
    assert candidate_from_message(parsed).download_url == LINK


def test_attached_html_is_not_treated_as_visible_body(tmp_path):
    path, outer = eml_file(tmp_path, html=markup(LINK))
    outer.add_attachment(markup(OTHER_LINK), subtype="html", filename="extra.html")
    path.write_bytes(outer.as_bytes())
    assert candidate_from_message(read_saved_email(path)).download_url == LINK


def test_bearer_links_and_remote_object_names_redacted_from_preview_fields():
    result = candidate_from_message(message(LINK, subject="Private " + LINK))
    assert LINK not in repr(result)
    assert "export-synthetic-first.xlsx" not in repr(result)
    assert safe_text("Name export-synthetic-first.xlsx") == "Name [export hidden]"
    assert safe_text(" one\r\n two \t ", limit=7) == "one two"


def test_import_preserves_selected_order_and_duplicate_messages_without_top_up(tmp_path):
    first, _mail = eml_file(tmp_path, name="first.eml")
    second, _mail = eml_file(tmp_path, html=markup(OTHER_LINK), name="second.eml")
    scan = import_emails((second, first, first), Event())
    assert [candidate.download_url for candidate in scan.candidates] == [OTHER_LINK, LINK, LINK]
    assert scan.candidates[1].key == scan.candidates[2].key
    assert scan.scanned == 3
    assert "not the newest Inbox" in scan.warning


def test_import_reports_unrecognized_files(tmp_path):
    path, mail = eml_file(tmp_path)
    mail.replace_header("Subject", "Unrelated")
    mail.set_content("Meeting tomorrow")
    path.write_bytes(mail.as_bytes())
    scan = import_emails((path,), Event())
    assert not scan.candidates
    assert "1 selected file(s) were not recognized" in scan.warning


def test_cancel_and_selection_limits_stop_before_reading():
    stop = Event()
    stop.set()
    with pytest.raises(CollectionCancelled):
        import_emails((Path("missing.eml"),), stop)
    with pytest.raises(CollectionError, match="1,000"):
        import_emails((), Event())


@pytest.mark.parametrize("limit", ["MAX_EMAIL_BYTES", "MAX_BODY_CHARS", "MAX_MIME_PARTS"])
def test_saved_email_size_and_part_limits_are_curated(tmp_path, monkeypatch, limit):
    path, _mail = eml_file(tmp_path, html=markup(LINK))
    monkeypatch.setattr(messages, limit, 1)
    with pytest.raises(CollectionError) as error:
        read_saved_email(path)
    assert str(path) not in str(error.value)
    assert LINK not in str(error.value)


def test_html_link_limit_fails_instead_of_silently_ignoring_ambiguous_tail(monkeypatch):
    monkeypatch.setattr(messages, "MAX_HTML_LINKS", 1)
    with pytest.raises(CollectionError, match="too many links"):
        candidate_from_message(message(LINK, OTHER_LINK))


def test_invalid_saved_format_and_missing_path_do_not_expose_private_details(tmp_path):
    path = tmp_path / "private-source.msg"
    path.write_bytes(b"not an Outlook container")
    for source in (path, tmp_path / "private-missing.eml"):
        with pytest.raises(CollectionError) as error:
            read_saved_email(source)
        assert source.name not in str(error.value)


class FakeOle:
    def __init__(self, html, *, codepage=None):
        self.closed = False
        self.streams = {
            "__substg1.0_10130102": html,
            "__substg1.0_007D001F": (
                "From: noreply@smaxtec.com\nDate: Wed, 09 Sep 2026 13:00:00 +0100\n"
            ).encode("utf-16-le"),
            "__substg1.0_0037001F": "Excel export file successfully created".encode("utf-16-le"),
            "__substg1.0_1000001F": ("smaXtec Excel export file " + LINK).encode("utf-16-le"),
        }
        if codepage is not None:
            self.streams["__properties_version1.0"] = b"\0" * 32 + pack(
                "<IIII", 0x3FDE0003, 0, codepage, 0
            )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def exists(self, path):
        assert len(path) == 1
        return path[0] in self.streams

    def get_size(self, path):
        assert len(path) == 1
        return len(self.streams[path[0]])

    def openstream(self, path):
        assert len(path) == 1
        return BytesIO(self.streams[path[0]])


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1252"])
def test_msg_html_encoding_is_respected_and_container_closed(tmp_path, monkeypatch, encoding):
    import olefile

    html = '<meta charset="' + encoding + '">' + markup(protected()) + "<p>café</p>"
    fake = FakeOle(html.encode(encoding))
    monkeypatch.setattr(olefile, "OleFileIO", lambda *_args, **_kwargs: fake)
    path = tmp_path / "synthetic.msg"
    path.write_bytes(MSG_MAGIC + b"synthetic placeholder")
    candidate = candidate_from_message(read_saved_email(path))
    assert candidate.download_url == protected()
    assert candidate.received_at == TIME
    assert fake.closed


def test_msg_internet_codepage_used_without_html_charset(tmp_path, monkeypatch):
    import olefile

    fake = FakeOle((markup(LINK) + "<p>café</p>").encode("cp1252"), codepage=1252)
    monkeypatch.setattr(olefile, "OleFileIO", lambda *_args, **_kwargs: fake)
    path = tmp_path / "synthetic.msg"
    path.write_bytes(MSG_MAGIC + b"synthetic placeholder")
    parsed = read_saved_email(path)
    assert "café" in parsed.html_body
    assert candidate_from_message(parsed).download_url == LINK


def test_msg_unknown_charset_returns_curated_error_and_closes_container(tmp_path, monkeypatch):
    import olefile

    fake = FakeOle(b'<meta charset="not-a-real-encoding">' + markup(LINK).encode())
    monkeypatch.setattr(olefile, "OleFileIO", lambda *_args, **_kwargs: fake)
    path = tmp_path / "private-source.msg"
    path.write_bytes(MSG_MAGIC + b"synthetic placeholder")
    with pytest.raises(CollectionError) as error:
        read_saved_email(path)
    assert error.value.code == "message_invalid"
    assert LINK not in str(error.value)
    assert path.name not in str(error.value)
    assert fake.closed


def test_msg_ansi_strings_use_message_codepage_and_sender_fallback(tmp_path, monkeypatch):
    import olefile

    fake = FakeOle(markup(LINK).encode())
    fake.streams.pop("__substg1.0_007D001F")
    fake.streams.pop("__substg1.0_0037001F")
    fake.streams["__substg1.0_0037001E"] = "Excel export file — café".encode("cp1252")
    fake.streams["__substg1.0_5D01001E"] = b"noreply@smaxtec.com"
    fake.streams["__properties_version1.0"] = b"\0" * 32 + pack("<IIII", 0x3FFD0003, 0, 1252, 0)
    monkeypatch.setattr(olefile, "OleFileIO", lambda *_args, **_kwargs: fake)
    path = tmp_path / "synthetic.msg"
    path.write_bytes(MSG_MAGIC + b"synthetic placeholder")
    parsed = read_saved_email(path)
    assert parsed.subject == "Excel export file — café"
    assert candidate_from_message(parsed).kind == "direct"
    assert fake.closed


@pytest.mark.parametrize(
    "properties",
    [
        b"too short",
        b"\0" * 33,
        b"\0" * 32 + pack("<IIII", 0x3FFD0003, 0, 1252, 0) * 2,
    ],
)
def test_malformed_or_ambiguous_msg_property_streams_fail_closed(tmp_path, monkeypatch, properties):
    import olefile

    fake = FakeOle(markup(LINK).encode())
    fake.streams["__properties_version1.0"] = properties
    monkeypatch.setattr(olefile, "OleFileIO", lambda *_args, **_kwargs: fake)
    path = tmp_path / "synthetic.msg"
    path.write_bytes(MSG_MAGIC + b"synthetic placeholder")
    with pytest.raises(CollectionError) as error:
        read_saved_email(path)
    assert error.value.code == "message_invalid"
    assert fake.closed


def test_msg_declared_stream_size_limit_checked_before_opening(tmp_path, monkeypatch):
    import olefile

    fake = FakeOle(markup(LINK).encode())
    monkeypatch.setattr(olefile, "OleFileIO", lambda *_args, **_kwargs: fake)
    monkeypatch.setattr(messages, "MAX_BODY_CHARS", 1)
    path = tmp_path / "synthetic.msg"
    path.write_bytes(MSG_MAGIC + b"synthetic placeholder")
    with pytest.raises(CollectionError) as error:
        read_saved_email(path)
    assert error.value.code == "message_large"
    assert fake.closed


def test_msg_rtf_only_or_attachment_forward_does_not_generate_or_read_hidden_html(
    tmp_path, monkeypatch
):
    import olefile

    fake = FakeOle(b"")
    fake.streams.pop("__substg1.0_1000001F")
    fake.streams["__substg1.0_10090102"] = markup(LINK).encode()
    fake.streams["__attach_version1.0_0/__substg1.0_10130102"] = markup(LINK).encode()
    monkeypatch.setattr(olefile, "OleFileIO", lambda *_args, **_kwargs: fake)
    path = tmp_path / "synthetic.msg"
    path.write_bytes(MSG_MAGIC + b"synthetic placeholder")
    candidate = candidate_from_message(read_saved_email(path))
    assert candidate.issue
    assert not candidate.download_url
    assert fake.closed
