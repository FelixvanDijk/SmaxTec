"""Durable collection metadata. No email bodies, remote filenames or bearer URLs."""

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from smaxtec import __version__
from smaxtec.application.collection import CollectionError, MailCandidate


def selection_digest(candidates: tuple[MailCandidate, ...]) -> str:
    values = [(row.key, row.link_fingerprint, row.issue) for row in candidates]
    return hashlib.sha256(json.dumps(values, ensure_ascii=True).encode()).hexdigest()


@contextmanager
def collection_lock(folder: Path):
    """OS lock releases on a crash; only Workbench's collection lock file is opened."""
    with (folder / ".collection.lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise CollectionError(
                "collection_busy", "This collection is in use by another Workbench window."
            ) from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class CollectionStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=2)
        self.connection.row_factory = sqlite3.Row
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.connection.close()
            raise CollectionError(
                "journal_version", "This collection history needs a newer Workbench version."
            )
        self.connection.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS collections (
                id TEXT PRIMARY KEY, folder TEXT UNIQUE NOT NULL, created TEXT NOT NULL,
                selection_hash TEXT NOT NULL, app_version TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS items (
                collection_id TEXT NOT NULL REFERENCES collections(id), position INTEGER NOT NULL,
                source_key TEXT NOT NULL, fingerprint TEXT NOT NULL, received TEXT NOT NULL,
                kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                filename TEXT NOT NULL DEFAULT '', sha256 TEXT NOT NULL DEFAULT '',
                cow TEXT NOT NULL DEFAULT '', original_b3 TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '', PRIMARY KEY(collection_id, position)
            );
            PRAGMA user_version = 1;
        """)

    def close(self) -> None:
        self.connection.close()

    def open_collection(self, candidates, destination: Path, resume_folder: Path | None):
        digest = selection_digest(candidates)
        if resume_folder is not None:
            folder = resume_folder.resolve()
            record = self.connection.execute(
                "SELECT * FROM collections WHERE folder = ?", (str(folder),)
            ).fetchone()
            if record is None or not folder.is_dir():
                raise CollectionError(
                    "collection_unknown",
                    "Choose a collection created by this Workbench user on this computer.",
                )
            if record["selection_hash"] != digest:
                raise CollectionError(
                    "selection_changed",
                    "These are not the same reviewed emails. "
                    "Re-select the original emails before resuming.",
                )
            return record["id"], folder
        collection_id = uuid4().hex
        created = datetime.now(UTC)
        destination = destination.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        folder = destination / f"{created.astimezone():%Y-%m-%d_%H-%M-%S}-{collection_id[:8]}"
        folder.mkdir(exist_ok=False)
        with self.connection:
            self.connection.execute(
                "INSERT INTO collections VALUES (?, ?, ?, ?, ?)",
                (
                    collection_id,
                    str(folder),
                    created.isoformat(),
                    digest,
                    __version__,
                ),
            )
            self.connection.executemany(
                "INSERT INTO items (collection_id, position, source_key, fingerprint, "
                "received, kind) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        collection_id,
                        index,
                        row.key,
                        row.link_fingerprint,
                        row.received_at.isoformat(),
                        row.kind,
                    )
                    for index, row in enumerate(candidates)
                ],
            )
        return collection_id, folder

    def items(self, collection_id: str):
        return self.connection.execute(
            "SELECT * FROM items WHERE collection_id = ? ORDER BY position", (collection_id,)
        ).fetchall()

    def update(self, collection_id: str, position: int, **values) -> None:
        allowed = {"status", "filename", "sha256", "cow", "original_b3", "detail"}
        if not values or not values.keys() <= allowed:
            raise ValueError("Unknown journal fields")
        with self.connection:
            self.connection.execute(
                f"UPDATE items SET {', '.join(key + ' = ?' for key in values)} "
                "WHERE collection_id = ? AND position = ?",
                (*values.values(), collection_id, position),
            )

    def manifest(self, collection_id: str, folder: Path) -> None:
        record = dict(
            self.connection.execute(
                "SELECT id, created, app_version FROM collections WHERE id = ?", (collection_id,)
            ).fetchone()
        )
        record["classification"] = (
            "Original workbook bytes preserved; labels not changed by Workbench."
        )
        record["correlation"] = (
            "B3 name only; farm, Animal number and requested period are not verified."
        )
        record["items"] = [
            {
                key: row[key]
                for key in (
                    "position",
                    "source_key",
                    "received",
                    "kind",
                    "status",
                    "filename",
                    "sha256",
                    "cow",
                    "original_b3",
                    "detail",
                )
            }
            for row in self.items(collection_id)
        ]
        # Replace only our own manifest, never raw workbooks.
        temporary = folder / f".manifest-{uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, indent=2)
            temporary.replace(folder / "collection.json")
        finally:
            temporary.unlink(missing_ok=True)
