"""User-reviewed download orchestration, journaled before publishing any workbook."""

import hashlib
import os
import re
import sqlite3
from pathlib import Path
from threading import Event
from uuid import uuid4

from smaxtec.adapters.mail.downloads import MAX_DOWNLOAD_BYTES, ExportDownloader, target_from_link
from smaxtec.adapters.workbooks import inspect_workbook
from smaxtec.application.collection import (
    CollectedFile,
    CollectionCancelled,
    CollectionError,
    CollectionProgress,
    CollectionResult,
    MailCandidate,
)
from smaxtec.application.collection_store import CollectionStore, collection_lock

_FILENAME = re.compile(r"cow-[0-9]{1,64}(?:__[0-9]{2,5})?\.xlsx", re.ASCII)


def _file_hash(path: Path, stop: Event) -> str:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if stop.is_set():
                raise CollectionCancelled()
            size += len(chunk)
            if size > MAX_DOWNLOAD_BYTES:
                return ""  # A changed file must not cause an unbounded verification read.
            digest.update(chunk)
    return digest.hexdigest()


def _published_file(folder: Path, filename: str) -> Path:
    if not _FILENAME.fullmatch(filename):
        raise CollectionError(
            "collection_changed",
            "The collection's file metadata is invalid. Create a new collection.",
        )
    result = folder / filename
    if result.is_symlink() or result.resolve().parent != folder.resolve():
        raise CollectionError(
            "collection_changed",
            "A collection file points outside its folder. Create a new collection.",
        )
    return result


class CollectionService:
    def __init__(self, journal_path: Path, *, downloader=None, inspector=None) -> None:
        self.journal_path = journal_path
        self._downloader = downloader or ExportDownloader()
        self._inspector = inspector or inspect_workbook

    def download(
        self,
        candidates: tuple[MailCandidate, ...],
        destination: Path,
        stop: Event,
        progress,
        resume_folder: Path | None = None,
    ) -> CollectionResult:
        candidates = tuple(candidates)
        if not 1 <= len(candidates) <= 1000:
            raise CollectionError(
                "selection_size", "Review between 1 and 1,000 export emails first."
            )
        if stop.is_set():
            raise CollectionCancelled()
        store = None
        try:
            store = CollectionStore(self.journal_path)
            collection_id, folder = store.open_collection(candidates, destination, resume_folder)
            with collection_lock(folder):
                return self._collect(store, collection_id, folder, candidates, stop, progress)
        except (OSError, sqlite3.Error):
            raise CollectionError(
                "storage",
                "Collection storage could not be updated. Check folder permissions and free space. "
                "Completed files are preserved; re-select the same emails "
                "and resume the collection.",
            ) from None
        finally:
            if store is not None:
                store.close()

    def _collect(self, store, collection_id, folder, candidates, stop, progress):
        rows = store.items(collection_id)
        completed = {}
        attempted = set()
        cancelled = False
        store.manifest(collection_id, folder)
        for index, candidate in enumerate(candidates):
            row = rows[index]
            if stop.is_set():
                cancelled = True
                break
            progress(
                CollectionProgress(
                    f"Collecting email {index + 1} of {len(candidates)}…", index, len(candidates)
                )
            )
            staging = folder / f".download-{uuid4().hex}.part"
            try:
                if row["filename"] and row["sha256"]:
                    previous = _published_file(folder, row["filename"])
                    unpublished = (
                        row["status"] not in ("saved", "duplicate") and not previous.exists()
                    )
                    if not unpublished and (
                        not previous.exists() or _file_hash(previous, stop) != row["sha256"]
                    ):
                        raise CollectionError(
                            "file_changed",
                            "A previously collected file is missing or changed. "
                            "It was not overwritten; create a new collection.",
                        )
                    if not unpublished:
                        final_status = "duplicate" if row["status"] == "duplicate" else "saved"
                        store.update(
                            collection_id,
                            index,
                            status=final_status,
                            detail="Previously saved file verified.",
                        )
                        completed[candidate.link_fingerprint] = dict(row)
                        continue
                if candidate.issue or not candidate.download_url:
                    raise CollectionError(
                        "message_ambiguous",
                        "No single verified export link is available for this email. "
                        "Check it in Outlook.",
                    )
                actual_target = target_from_link(candidate.download_url)
                if actual_target.fingerprint != candidate.link_fingerprint:
                    raise CollectionError(
                        "selection_changed",
                        "The reviewed export link changed. Find and review the emails again.",
                    )
                if candidate.link_fingerprint in completed:
                    original = completed[candidate.link_fingerprint]
                    store.update(
                        collection_id,
                        index,
                        status="duplicate",
                        filename=original["filename"],
                        sha256=original["sha256"],
                        cow=original["cow"],
                        original_b3=original["original_b3"],
                        detail="Same export link as an earlier reviewed email; file retained once.",
                    )
                    continue
                if candidate.link_fingerprint in attempted:
                    raise CollectionError(
                        "duplicate_incomplete",
                        "The same export failed earlier in this selection. "
                        "It was not automatically downloaded again; retry when ready.",
                    )
                attempted.add(candidate.link_fingerprint)
                digest = self._downloader.download(candidate.download_url, staging, stop)
                if row["filename"] and row["sha256"] and digest != row["sha256"]:
                    raise CollectionError(
                        "file_changed",
                        "The interrupted export's contents changed. Create a new collection; "
                        "existing files were preserved.",
                    )
                identity = self._inspector(staging)
                if not re.fullmatch(r"[0-9]{1,64}", identity.cow_number, re.ASCII):
                    raise CollectionError(
                        "cow_invalid", "The workbook does not have one usable cow number in B3."
                    )
                if stop.is_set():
                    raise CollectionCancelled()
                # Journal the expected hash/name BEFORE atomic publish, allowing crash recovery.
                for suffix in range(1, 10001):
                    tail = "" if suffix == 1 else f"__{suffix:02d}"
                    filename = f"cow-{identity.cow_number}{tail}.xlsx"
                    final = _published_file(folder, filename)
                    if final.exists():
                        continue
                    store.update(
                        collection_id,
                        index,
                        status="prepared",
                        filename=filename,
                        sha256=digest,
                        cow=identity.cow_number,
                        original_b3=identity.original_name,
                        detail="",
                    )
                    try:
                        if os.name == "nt":
                            os.rename(
                                staging, final
                            )  # Windows rename is atomic and never replaces.
                        else:
                            os.link(staging, final)  # POSIX rename would overwrite.
                            staging.unlink()
                        break
                    except FileExistsError:
                        continue
                else:
                    raise CollectionError(
                        "filename_conflict",
                        "Too many files have this cow number. Create a new collection.",
                    )
                store.update(
                    collection_id,
                    index,
                    status="saved",
                    detail="Original file preserved; label unchanged.",
                )
                completed[candidate.link_fingerprint] = {
                    "filename": filename,
                    "sha256": digest,
                    "cow": identity.cow_number,
                    "original_b3": identity.original_name,
                }
            except CollectionCancelled:
                # Cancelling while verifying a completed file must not erase its journal state.
                if row["status"] not in ("saved", "duplicate", "prepared"):
                    store.update(
                        collection_id,
                        index,
                        status="cancelled",
                        detail="Cancelled before completion.",
                    )
                cancelled = True
                break
            except CollectionError as error:
                # Do not erase the expected hash/status on a changed completed artifact.
                if error.code in ("file_changed", "collection_changed"):
                    raise
                store.update(collection_id, index, status="failed", detail=str(error))
            finally:
                staging.unlink(missing_ok=True)
                store.manifest(collection_id, folder)
        if cancelled:
            for row in store.items(collection_id):
                if row["status"] == "pending":
                    store.update(
                        collection_id,
                        row["position"],
                        status="cancelled",
                        detail="Not started; collection cancelled.",
                    )
        store.manifest(collection_id, folder)
        files = tuple(
            CollectedFile(
                row["source_key"], row["status"], row["filename"], row["cow"], row["detail"]
            )
            for row in store.items(collection_id)
        )
        progress(
            CollectionProgress(
                "Collection stopped." if cancelled else "Collection finished.",
                len(files),
                len(files),
            )
        )
        return CollectionResult(folder, files, cancelled)
