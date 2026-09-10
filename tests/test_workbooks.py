"""Synthetic workbook packages only: no client exports or Office installation."""

from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path
from struct import pack_into, unpack_from
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from smaxtec.adapters import workbooks
from smaxtec.adapters.workbooks import WorkbookIdentity, inspect_workbook
from smaxtec.application.collection import CollectionError

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"


def inline(value: str) -> str:
    return f'<c r="B3" t="inlineStr"><is><t>{escape(value)}</t></is></c>'


def package(
    cells: tuple[str, ...] = (inline("203"),),
    *,
    shared: str | None = None,
    states: tuple[str, ...] = (),
) -> dict[str, str | bytes]:
    """Use nonstandard but valid part names to verify relationship resolution."""
    sheet_nodes = []
    sheet_relations = []
    parts: dict[str, str | bytes] = {}
    for index, cell in enumerate(cells):
        state = states[index] if states else "visible"
        sheet_nodes.append(
            f'<sheet name="Data {index}" sheetId="{index + 1}" r:id="s{index}" state="{state}"/>'
        )
        sheet_relations.append(
            f'<Relationship Id="s{index}" Type="{DOC_REL}/worksheet" '
            f'Target="sheets/data-{index}.xml"/>'
        )
        parts[f"custom/sheets/data-{index}.xml"] = (
            f'<worksheet xmlns="{MAIN}"><sheetData><row r="3">{cell}</row></sheetData></worksheet>'
        )
    if shared is not None:
        parts["custom/text.xml"] = f'<sst xmlns="{MAIN}">{shared}</sst>'
        sheet_relations.append(
            f'<Relationship Id="strings" Type="{DOC_REL}/sharedStrings" Target="text.xml"/>'
        )
    parts["custom/book.xml"] = (
        f'<workbook xmlns="{MAIN}" xmlns:r="{DOC_REL}"><sheets>'
        + "".join(sheet_nodes)
        + "</sheets></workbook>"
    )
    parts["custom/_rels/book.xml.rels"] = (
        f'<Relationships xmlns="{REL}">' + "".join(sheet_relations) + "</Relationships>"
    )
    parts["_rels/.rels"] = (
        f'<Relationships xmlns="{REL}"><Relationship Id="book" '
        f'Type="{DOC_REL}/officeDocument" Target="custom/book.xml"/></Relationships>'
    )
    parts["[Content_Types].xml"] = (
        f'<Types xmlns="{CONTENT}"><Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/custom/book.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        "</Types>"
    )
    return parts


def write_package(tmp_path: Path, parts: dict[str, str | bytes], filename="unrelated-999.xlsx"):
    path = tmp_path / filename
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            # Preserve deliberately hostile backslashes instead of allowing
            # Windows ZipInfo to normalize them on construction.
            info = ZipInfo("placeholder")
            info.filename = name
            info.orig_filename = name
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, value)
    return path


def assert_rejected(path: Path, code: str | None = None):
    with pytest.raises(CollectionError) as failure:
        inspect_workbook(path)
    if code is not None:
        assert failure.value.code == code
    assert str(path) not in str(failure.value)
    assert path.name not in str(failure.value)
    return failure.value


def test_reads_actual_relationships_not_filename_active_sheet_or_conventional_paths(tmp_path):
    path = write_package(tmp_path, package((inline("203"), inline("203 (new girl)"))))
    assert inspect_workbook(path) == WorkbookIdentity("203", "203")


@pytest.mark.parametrize("value, expected", [("00203", "00203"), ("203 (new girl)", "203")])
def test_text_identity_preserves_zeroes_and_ignores_parenthesized_annotation(
    tmp_path, value, expected
):
    path = write_package(tmp_path, package((inline(value),)))
    assert inspect_workbook(path) == WorkbookIdentity(expected, value)


def test_preserves_original_cell_text_for_provenance(tmp_path):
    name = "  00203 (new girl)  "
    path = write_package(tmp_path, package((inline(name),)))
    assert inspect_workbook(path) == WorkbookIdentity("00203", name)


def test_reads_rich_shared_strings(tmp_path):
    shared = "<si><t>unused</t></si><si><r><t>00203</t></r><r><t> (new girl)</t></r></si>"
    path = write_package(tmp_path, package(('<c r="B3" t="s"><v>1</v></c>',), shared=shared))
    assert inspect_workbook(path) == WorkbookIdentity("00203", "00203 (new girl)")


@pytest.mark.parametrize("value, expected", [("203", "203"), ("203.0", "203"), ("2.03e2", "203")])
def test_numeric_integral_b3(tmp_path, value, expected):
    path = write_package(tmp_path, package((f'<c r="B3"><v>{value}</v></c>',)))
    assert inspect_workbook(path) == WorkbookIdentity(expected, value)


@pytest.mark.parametrize(
    "value",
    ["203/204", "cow 203", "20A3", "203-204", "203 (a) (b)", "２０３", "1" * 65, "", "  "],
)
def test_ambiguous_text_and_blank_identities_are_not_guessed(tmp_path, value):
    failure = assert_rejected(
        write_package(tmp_path, package((inline(value),))), "workbook_identity"
    )
    assert "20A3" not in str(failure)


@pytest.mark.parametrize("value", ["203.5", "NaN", "-203", "1e999999", "0.2", "203/204"])
def test_invalid_numeric_values(tmp_path, value):
    assert_rejected(write_package(tmp_path, package((f'<c r="B3"><v>{value}</v></c>',))))


@pytest.mark.parametrize(
    "cell",
    [
        '<c r="B3"><f>200+3</f><v>203</v></c>',
        '<c r="B3" t="b"><v>1</v></c>',
        '<c r="B3" t="e"><v>#VALUE!</v></c>',
        '<c r="B3" t="s"><v>0</v></c>',
        '<c r="B3"/>',
        '<c r="B4" t="inlineStr"><is><t>203</t></is></c>',
        inline("203") + inline("203"),
    ],
)
def test_formula_boolean_error_missing_duplicate_and_unknown_shared_b3(tmp_path, cell):
    assert_rejected(write_package(tmp_path, package((cell,))), "workbook_identity")


def test_conflicting_visible_sheets_reject_and_do_not_report_private_values(tmp_path):
    path = write_package(tmp_path, package((inline("203"), inline("87654321"))))
    error = assert_rejected(path, "workbook_identity")
    assert "87654321" not in str(error)


def test_hidden_sheets_are_not_data_identity_sources_but_at_least_one_visible_is_required(tmp_path):
    parts = package((inline("203"), inline("")), states=("visible", "hidden"))
    assert inspect_workbook(write_package(tmp_path, parts)).cow_number == "203"
    parts = package((inline("203"),), states=("hidden",))
    assert_rejected(write_package(tmp_path, parts), "workbook_identity")


def test_keeps_custom_sensitivity_metadata_and_every_byte_unchanged(tmp_path):
    parts = package()
    parts["docProps/custom.xml"] = (
        '<Properties><Property name="Sensitivity">synthetic</Property></Properties>'
    )
    path = write_package(tmp_path, parts)
    before = sha256(path.read_bytes()).digest()
    result = inspect_workbook(path)
    assert sha256(path.read_bytes()).digest() == before
    with ZipFile(path) as archive:
        assert archive.read("docProps/custom.xml").decode() == parts["docProps/custom.xml"]
    with pytest.raises(FrozenInstanceError):
        result.cow_number = "different"


@pytest.mark.parametrize(
    "target", ["https://example.test/file", "../../outside.xml", "%2e%2e/%2e%2e/out.xml"]
)
def test_unsafe_relationship_targets_are_never_followed(tmp_path, target):
    parts = package()
    parts["custom/_rels/book.xml.rels"] = str(parts["custom/_rels/book.xml.rels"]).replace(
        'Target="sheets/data-0.xml"', f'Target="{target}"'
    )
    assert_rejected(write_package(tmp_path, parts), "workbook_unsafe")


def test_standard_relative_comments_and_vml_relationships_are_valid_and_preserved(tmp_path):
    parts = package()
    parts["custom/sheets/_rels/data-0.xml.rels"] = (
        f'<Relationships xmlns="{REL}">'
        f'<Relationship Id="comments" Type="{DOC_REL}/comments" '
        'Target="../comments/comment1.xml"/>'
        f'<Relationship Id="drawing" Type="{DOC_REL}/vmlDrawing" '
        'Target="../drawings/commentsDrawing1.vml"/>'
        "</Relationships>"
    )
    parts["custom/comments/comment1.xml"] = (
        f'<comments xmlns="{MAIN}"><authors><author>Example</author></authors>'
        '<commentList><comment ref="B3" authorId="0"><text><t>Example note</t>'
        "</text></comment></commentList></comments>"
    )
    parts["custom/drawings/commentsDrawing1.vml"] = (
        '<xml xmlns:v="urn:schemas-microsoft-com:vml"><v:shape id="example"/></xml>'
    )
    parts["[Content_Types].xml"] = str(parts["[Content_Types].xml"]).replace(
        "</Types>",
        '<Default Extension="vml" '
        'ContentType="application/vnd.openxmlformats-officedocument.vmlDrawing"/></Types>',
    )
    path = write_package(tmp_path, parts)
    before = sha256(path.read_bytes()).digest()
    assert inspect_workbook(path).cow_number == "203"
    assert sha256(path.read_bytes()).digest() == before


@pytest.mark.parametrize(
    "target",
    [
        "./sheets/data-0.xml",
        "sheets/../sheets/data-0.xml",
        "../custom/sheets/data-0.xml",
        "%2e%2e/custom/sheets/data-0.xml",
        "/custom/./sheets/data-0.xml",
    ],
)
def test_normalized_internal_relationships_resolve_to_existing_members(tmp_path, target):
    parts = package()
    parts["custom/_rels/book.xml.rels"] = str(parts["custom/_rels/book.xml.rels"]).replace(
        'Target="sheets/data-0.xml"', f'Target="{target}"'
    )
    assert inspect_workbook(write_package(tmp_path, parts)).cow_number == "203"


@pytest.mark.parametrize(
    "target",
    [
        "../../custom/sheets/data-0.xml",
        ".././../custom/sheets/data-0.xml",
        "sheets/../../../custom/sheets/data-0.xml",
        "/../custom/sheets/data-0.xml",
        "%2e%2e/%2e%2e/custom/sheets/data-0.xml",
        "/%2e%2e/custom/sheets/data-0.xml",
        "%252e%252e/custom/sheets/data-0.xml",
        "..%5ccustom/sheets/data-0.xml",
        "//example.test/custom/sheets/data-0.xml",
        "///custom/sheets/data-0.xml",
        "%2f%2fexample.test/custom/sheets/data-0.xml",
        "file:///custom/sheets/data-0.xml",
        "C:/custom/sheets/data-0.xml",
        "sheets/data-0.xml?external=1",
        "sheets/data-0.xml#fragment",
    ],
)
def test_normalization_never_permits_escape_external_or_double_encoded_targets(tmp_path, target):
    parts = package()
    parts["custom/_rels/book.xml.rels"] = str(parts["custom/_rels/book.xml.rels"]).replace(
        'Target="sheets/data-0.xml"', f'Target="{target}"'
    )
    assert_rejected(write_package(tmp_path, parts), "workbook_unsafe")


def test_root_relationship_cannot_traverse_up_then_return_to_valid_part(tmp_path):
    parts = package()
    parts["_rels/.rels"] = str(parts["_rels/.rels"]).replace(
        'Target="custom/book.xml"', 'Target="../custom/book.xml"'
    )
    assert_rejected(write_package(tmp_path, parts), "workbook_unsafe")


def test_normalized_relationship_still_requires_real_target_member(tmp_path):
    parts = package()
    parts["custom/_rels/book.xml.rels"] = str(parts["custom/_rels/book.xml.rels"]).replace(
        'Target="sheets/data-0.xml"', 'Target="../missing/data-0.xml"'
    )
    assert_rejected(write_package(tmp_path, parts), "workbook_invalid")


@pytest.mark.parametrize(
    "replacement",
    [
        ('Id="s0"', 'Id="missing"'),
        ("/worksheet", "/unknown"),
        ('Target="sheets/data-0.xml"', 'Target="sheets/missing.xml"'),
    ],
)
def test_unknown_sheet_relationships_are_rejected(tmp_path, replacement):
    parts = package()
    parts["custom/_rels/book.xml.rels"] = str(parts["custom/_rels/book.xml.rels"]).replace(
        *replacement
    )
    assert_rejected(write_package(tmp_path, parts), "workbook_invalid")


def test_external_relationships_are_rejected_even_in_unrelated_parts(tmp_path):
    parts = package()
    parts["custom/sheets/_rels/data-0.xml.rels"] = (
        f'<Relationships xmlns="{REL}"><Relationship Id="link" Type="{DOC_REL}/hyperlink" '
        'TargetMode="External" Target="https://example.test/"/></Relationships>'
    )
    assert_rejected(write_package(tmp_path, parts), "workbook_unsafe")


@pytest.mark.parametrize("part", ["xl/vbaProject.bin", "xl/externalLinks/externalLink1.xml"])
def test_macro_and_external_link_parts_rejected(tmp_path, part):
    parts = package()
    parts[part] = b"synthetic"
    assert_rejected(write_package(tmp_path, parts), "workbook_unsafe")


def test_macro_enabled_content_type_rejected(tmp_path):
    parts = package()
    parts["[Content_Types].xml"] = str(parts["[Content_Types].xml"]).replace(
        "spreadsheetml.sheet.main+xml", "ms-excel.sheet.macroEnabled.main+xml"
    )
    assert_rejected(write_package(tmp_path, parts), "workbook_unsafe")


def test_embedded_active_content_rejected(tmp_path):
    parts = package()
    parts["custom/embeddings/object.bin"] = b"synthetic embedded object"
    assert_rejected(write_package(tmp_path, parts), "workbook_unsafe")


def test_duplicate_relationship_ids_rejected(tmp_path):
    parts = package((inline("203"), inline("203")))
    parts["custom/_rels/book.xml.rels"] = str(parts["custom/_rels/book.xml.rels"]).replace(
        'Id="s1"', 'Id="s0"'
    )
    assert_rejected(write_package(tmp_path, parts), "workbook_invalid")


def test_encrypted_zip_flag_is_rejected_before_reading(tmp_path):
    path = write_package(tmp_path, package())
    content = bytearray(path.read_bytes())
    # Flag both central-directory and local entries as encrypted; no password,
    # decryption attempt or real protected export is involved in this fixture.
    for signature, offset in ((b"PK\x01\x02", 8), (b"PK\x03\x04", 6)):
        start = 0
        while (position := content.find(signature, start)) != -1:
            flags = unpack_from("<H", content, position + offset)[0]
            pack_into("<H", content, position + offset, flags | 1)
            start = position + len(signature)
    path.write_bytes(content)
    assert_rejected(path, "workbook_unsafe")


def test_corrupt_zip_payload_returns_only_curated_error(tmp_path):
    path = write_package(tmp_path, package())
    content = bytearray(path.read_bytes())
    name_length, extra_length = unpack_from("<HH", content, 26)
    data_start = 30 + name_length + extra_length
    content[data_start + 3] ^= 0xFF
    path.write_bytes(content)
    assert_rejected(path, "workbook_invalid")


@pytest.mark.parametrize("part", ["../escape.xml", "/root.xml", r"folder\file.xml", "a/./b.xml"])
def test_zip_path_traversal_is_rejected_without_extracting(tmp_path, part):
    parts = package()
    parts[part] = "<x/>"
    assert_rejected(write_package(tmp_path, parts), "workbook_invalid")
    assert not (tmp_path.parent / "escape.xml").exists()


def test_duplicate_casefolded_members_and_symlinks_rejected(tmp_path):
    parts = package()
    parts["CUSTOM/BOOK.XML"] = "<x/>"
    assert_rejected(write_package(tmp_path, parts), "workbook_invalid")
    path = write_package(tmp_path, package())
    link = ZipInfo("linked.xml")
    link.create_system = 3
    link.external_attr = 0o120777 << 16
    with ZipFile(path, "a") as archive:
        archive.writestr(link, "target.xml")
    assert_rejected(path, "workbook_unsafe")


@pytest.mark.parametrize(
    "payload",
    [
        '<!DOCTYPE workbook [<!ENTITY x "203">]><workbook>&x;</workbook>',
        '<!DOCTYPE workbook [<!ENTITY x SYSTEM "file:///private.txt">]><workbook>&x;</workbook>',
        "<workbook><broken>",
    ],
)
def test_malicious_or_malformed_xml_rejected(tmp_path, payload):
    parts = package()
    parts["custom/book.xml"] = payload
    assert_rejected(write_package(tmp_path, parts), "workbook_invalid")


@pytest.mark.parametrize(
    "limit, size",
    [
        ("MAX_DOWNLOAD_BYTES", 1),
        ("MAX_UNCOMPRESSED_BYTES", 1),
        ("MAX_XML_BYTES", 1),
        ("MAX_MEMBERS", 1),
        ("MAX_COMPRESSION_RATIO", 1),
    ],
)
def test_archive_resource_limits_are_enforced(tmp_path, monkeypatch, limit, size):
    path = write_package(tmp_path, package())
    monkeypatch.setattr(workbooks, limit, size)
    assert_rejected(path, "workbook_too_large")


@pytest.mark.parametrize(
    "payload", [b"<html>expired link</html>", b"\xd0\xcf\x11\xe0protected", b"PK\x03\x04broken"]
)
def test_html_encrypted_office_container_and_broken_zip_rejected(tmp_path, payload):
    path = tmp_path / "private-source.xlsx"
    path.write_bytes(payload)
    assert_rejected(path, "workbook_invalid")
