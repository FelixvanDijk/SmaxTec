"""Inspect cow identity in untrusted XLSX packages without Excel or file rewrites."""

import posixpath
import re
import stat
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import Element
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile
from zlib import error as ZlibError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from smaxtec.application.collection import CollectionError

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_XML_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 10_000
MAX_COMPRESSION_RATIO = 1_000

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
_IDENTITY = re.compile(r"([0-9]{1,64})(?:\s+\([^()\r\n]+\))?", re.ASCII)
_NUMERIC = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", re.ASCII)


@dataclass(frozen=True)
class WorkbookIdentity:
    cow_number: str
    original_name: str


def _invalid() -> CollectionError:
    return CollectionError(
        "workbook_invalid",
        "The download is not a supported, intact XLSX workbook. Request a fresh export.",
    )


def _unsafe() -> CollectionError:
    return CollectionError(
        "workbook_unsafe",
        "The workbook contains protected or unsupported active/external content. "
        "Ask your organisation to provide a standard, approved XLSX export.",
    )


def _too_large() -> CollectionError:
    return CollectionError(
        "workbook_too_large",
        "The workbook exceeds the safe inspection limits. Try a shorter export period.",
    )


def _identity_error() -> CollectionError:
    return CollectionError(
        "workbook_identity",
        "The animal number in cell B3 is missing, ambiguous or inconsistent across data sheets. "
        "Check the export before using it for analysis.",
    )


def _safe_part(name: str) -> bool:
    return bool(name) and not (
        name.startswith("/")
        or "\\" in name
        or any(ord(char) < 32 for char in name)
        or any(char in name for char in ":?#%")
        or any(piece in ("", ".", "..") for piece in name.split("/"))
    )


def _validate_archive(archive: ZipFile) -> set[str]:
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise _too_large()
    names: set[str] = set()
    folded_names: set[str] = set()
    total = 0
    for info in infos:
        # ZipInfo normalizes backslashes on Windows and truncates NULs. Reject
        # altered spellings instead of allowing the parser to hide unsafe names.
        if info.orig_filename != info.filename:
            raise _invalid()
        name = info.filename.rstrip("/") if info.is_dir() else info.filename
        if not _safe_part(name) or name.casefold() in folded_names:
            raise _invalid()
        names.add(info.filename)
        folded_names.add(name.casefold())
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise _too_large()
        if info.file_size > max(1, info.compress_size) * MAX_COMPRESSION_RATIO:
            raise _too_large()
        if name.lower().endswith((".xml", ".rels")) and info.file_size > MAX_XML_BYTES:
            raise _too_large()
        if (
            info.flag_bits & 1
            or info.compress_type not in (ZIP_STORED, ZIP_DEFLATED)
            or stat.S_ISLNK(info.external_attr >> 16)
            or any(
                token in name.lower()
                for token in (
                    "vbaproject",
                    "vbasignature",
                    "externallinks/",
                    "activex/",
                    "embeddings/",
                )
            )
        ):
            raise _unsafe()
    # CRC checks are bounded by the member sizes above; nothing is extracted to disk.
    if archive.testzip() is not None:
        raise _invalid()
    return names


def _xml(archive: ZipFile, name: str) -> Element:
    info = archive.getinfo(name)
    if info.file_size > MAX_XML_BYTES:
        raise _too_large()
    return ElementTree.fromstring(
        archive.read(info), forbid_dtd=True, forbid_entities=True, forbid_external=True
    )


def _relationship_source(name: str) -> str:
    if name == "_rels/.rels":
        return ""
    parent, filename = posixpath.split(name)
    if posixpath.basename(parent) != "_rels" or not filename.endswith(".rels"):
        raise _invalid()
    return posixpath.join(posixpath.dirname(parent), filename[:-5])


def _target_part(source: str, target: str) -> str:
    """Resolve an internal OPC URI without ever traversing above the package root.

    Relationship targets are relative to their source part, not the .rels file.
    Normal ../comments and ../drawings references must not be confused with ZIP
    member traversal: member names still pass the unchanged strict _safe_part.
    """
    if (
        not target
        or target.startswith("//")
        or "\\" in target
        or any(ord(char) < 32 or ord(char) == 127 for char in target)
    ):
        raise _unsafe()
    try:
        parsed = urlsplit(target)
        decoded = unquote(parsed.path, errors="strict")
    except ValueError:
        raise _unsafe() from None
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or not decoded
        or decoded.startswith("//")
        or "\\" in decoded
        or any(char in decoded for char in ":%")
        or any(ord(char) < 32 or ord(char) == 127 for char in decoded)
    ):
        raise _unsafe()
    if decoded.startswith("/"):
        pieces: list[str] = []
        relative = decoded[1:]
    else:
        directory = posixpath.dirname(source)
        pieces = directory.split("/") if directory else []
        relative = decoded
    segments = relative.split("/")
    if segments[-1] in ("", ".", ".."):
        raise _invalid()
    for segment in segments:
        if segment == ".":
            continue
        if segment == "..":
            if not pieces:
                # normpath alone would hide attempts to escape an absolute root.
                raise _unsafe()
            pieces.pop()
        elif not segment:
            raise _invalid()
        else:
            pieces.append(segment)
    resolved = "/".join(pieces)
    if not _safe_part(resolved):
        raise _invalid()
    return resolved


def _relationships(archive: ZipFile, names: set[str]) -> dict[str, dict[str, tuple[str, str]]]:
    by_source: dict[str, dict[str, tuple[str, str]]] = {}
    for name in sorted(names):
        if not name.endswith(".rels"):
            continue
        source = _relationship_source(name)
        if source and source not in names:
            raise _invalid()
        root = _xml(archive, name)
        if root.tag != f"{{{_REL}}}Relationships":
            raise _invalid()
        relationships: dict[str, tuple[str, str]] = {}
        for item in root:
            identifier = item.get("Id", "")
            relationship_type = item.get("Type", "")
            if item.tag != f"{{{_REL}}}Relationship" or not identifier or not relationship_type:
                raise _invalid()
            if identifier in relationships:
                raise _invalid()
            if item.get("TargetMode", "Internal") != "Internal" or any(
                token in relationship_type.lower()
                for token in ("externallink", "vbaproject", "vbasignature", "activex", "oleobject")
            ):
                raise _unsafe()
            if relationship_type == f"{_DOC_REL}/package":
                raise _unsafe()
            target = _target_part(source, item.get("Target", ""))
            if target not in names or target.endswith("/"):
                raise _invalid()
            relationships[identifier] = (relationship_type, target)
        by_source[source] = relationships
    return by_source


def _validate_content_types(archive: ZipFile) -> None:
    root = _xml(archive, "[Content_Types].xml")
    if root.tag != f"{{{_CONTENT}}}Types":
        raise _invalid()
    for item in root:
        content_type = item.get("ContentType", "").lower()
        if (
            item.tag not in (f"{{{_CONTENT}}}Default", f"{{{_CONTENT}}}Override")
            or not content_type
        ):
            raise _invalid()
        if any(token in content_type for token in ("macroenabled", "vba", "activex", "oleobject")):
            raise _unsafe()


def _text(element: Element) -> str:
    """Read plain or rich text, excluding phonetic guides and arbitrary nested tags."""
    pieces = []
    for child in element:
        if child.tag == f"{{{_MAIN}}}t":
            pieces.append(child.text or "")
        elif child.tag == f"{{{_MAIN}}}r":
            pieces.extend(text.text or "" for text in child.findall(f"{{{_MAIN}}}t"))
    return "".join(pieces)


def _shared_strings(archive: ZipFile, relationships: dict[str, tuple[str, str]]) -> list[str]:
    parts = [
        target for kind, target in relationships.values() if kind == f"{_DOC_REL}/sharedStrings"
    ]
    if not parts:
        return []
    if len(parts) != 1:
        raise _invalid()
    root = _xml(archive, parts[0])
    if root.tag != f"{{{_MAIN}}}sst":
        raise _invalid()
    return [_text(item) for item in root.findall(f"{{{_MAIN}}}si")]


def _cell_identity(cell: Element, shared: list[str]) -> WorkbookIdentity:
    if cell.find(f"{{{_MAIN}}}f") is not None:
        raise _identity_error()
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        nodes = cell.findall(f"{{{_MAIN}}}is")
        if len(nodes) != 1:
            raise _identity_error()
        value = _text(nodes[0])
    elif kind in ("s", "n"):
        nodes = cell.findall(f"{{{_MAIN}}}v")
        if len(nodes) != 1:
            raise _identity_error()
        value = nodes[0].text or ""
        if kind == "s":
            value = value.strip()
            if not re.fullmatch(r"[0-9]{1,10}", value, re.ASCII):
                raise _identity_error()
            index = int(value)
            if index >= len(shared):
                raise _identity_error()
            value = shared[index]
    else:
        raise _identity_error()
    original_name = value
    value = value.strip()
    if not value or len(original_name) > 512 or any(ord(char) < 32 for char in value):
        raise _identity_error()
    if kind == "n":
        if len(value) > 128 or not _NUMERIC.fullmatch(value):
            raise _identity_error()
        numeric = Decimal(value)
        if (
            not numeric.is_finite()
            or numeric.adjusted() >= 64
            or numeric != numeric.to_integral_value()
        ):
            raise _identity_error()
        return WorkbookIdentity(str(int(numeric)), original_name)
    match = _IDENTITY.fullmatch(value)
    if match is None:
        raise _identity_error()
    return WorkbookIdentity(match[1], original_name)


def _inspect(archive: ZipFile) -> WorkbookIdentity:
    names = _validate_archive(archive)
    _validate_content_types(archive)
    all_relationships = _relationships(archive, names)
    roots = [
        target
        for kind, target in all_relationships.get("", {}).values()
        if kind == f"{_DOC_REL}/officeDocument"
    ]
    if len(roots) != 1:
        raise _invalid()
    workbook_part = roots[0]
    root = _xml(archive, workbook_part)
    if root.tag != f"{{{_MAIN}}}workbook":
        raise _invalid()
    workbook_relationships = all_relationships.get(workbook_part, {})
    shared = _shared_strings(archive, workbook_relationships)
    identities: list[WorkbookIdentity] = []
    seen_parts: set[str] = set()
    for sheet in root.findall(f"{{{_MAIN}}}sheets/{{{_MAIN}}}sheet"):
        relationship_id = sheet.get(f"{{{_DOC_REL}}}id", "")
        kind, part = workbook_relationships.get(relationship_id, ("", ""))
        if kind != f"{_DOC_REL}/worksheet" or part in seen_parts:
            raise _invalid()
        seen_parts.add(part)
        state = sheet.get("state", "visible")
        if state not in ("visible", "hidden", "veryHidden"):
            raise _invalid()
        sheet_root = _xml(archive, part)
        if sheet_root.tag != f"{{{_MAIN}}}worksheet":
            raise _invalid()
        if state != "visible":
            continue
        cells = sheet_root.findall(f"{{{_MAIN}}}sheetData/{{{_MAIN}}}row/{{{_MAIN}}}c[@r='B3']")
        if len(cells) != 1:
            raise _identity_error()
        identities.append(_cell_identity(cells[0], shared))
    if not identities or len({identity.cow_number for identity in identities}) != 1:
        raise _identity_error()
    return identities[0]


def inspect_workbook(path: Path) -> WorkbookIdentity:
    """Validate and read visible data-sheet B3 cells; leave all source bytes untouched."""
    try:
        if path.stat().st_size > MAX_DOWNLOAD_BYTES:
            raise _too_large()
        with path.open("rb") as source:
            if source.read(4) != b"PK\x03\x04":
                raise _invalid()
            source.seek(0)
            with ZipFile(source) as archive:
                return _inspect(archive)
    except CollectionError:
        raise
    except (
        OSError,
        BadZipFile,
        KeyError,
        ValueError,
        RuntimeError,
        InvalidOperation,
        ZlibError,
        EOFError,
    ):
        raise _invalid() from None
    except (ElementTree.ParseError, DefusedXmlException):
        raise _invalid() from None
