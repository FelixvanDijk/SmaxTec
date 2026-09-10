"""Offline collection state tests. No Outlook, network or real export links."""

import hashlib
import json
from datetime import UTC, datetime
from threading import Event

import pytest

from smaxtec.adapters.mail.downloads import target_from_link
from smaxtec.adapters.workbooks import WorkbookIdentity
from smaxtec.application.collection import CollectionCancelled, CollectionError, MailCandidate
from smaxtec.application.collection_service import CollectionService
from smaxtec.application.collection_store import CollectionStore, collection_lock


def candidate(key="message-1", export="synthetic-one", *, issue=""):
    url = f"https://api.smaxtec.com/api/v2/data/downloads/export-{export}.xlsx"
    return MailCandidate(
        key,
        "Synthetic Excel export file",
        "synthetic@example.invalid",
        datetime(2026, 9, 9, tzinfo=UTC),
        "forwarded",
        url,
        target_from_link(url).fingerprint,
        issue,
    )


class Downloader:
    def __init__(self, payloads=None):
        self.calls = []
        self.payloads = payloads or [b"203 (new girl)"]

    def download(self, url, destination, stop):
        self.calls.append(url)
        payload = self.payloads[min(len(self.calls) - 1, len(self.payloads) - 1)]
        if isinstance(payload, Exception):
            raise payload
        destination.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()


def inspect(path):
    value = path.read_text()
    return WorkbookIdentity(value.split(" ")[0], value)


def service(tmp_path, downloader=None, inspector=inspect):
    return CollectionService(
        tmp_path / "state" / "journal.db",
        downloader=downloader or Downloader(),
        inspector=inspector,
    )


def collect(app, tmp_path, selection, *, stop=None, resume=None, progress=lambda _: None):
    return app.download(
        selection, tmp_path / "collections", stop or Event(), progress, resume_folder=resume
    )


def test_each_b3_controls_filename_and_same_cow_periods_do_not_overwrite(tmp_path):
    download = Downloader([b"203 (new girl)", b"0047", b"203"])
    selection = tuple(candidate(str(i), f"synthetic-{i}") for i in range(3))
    result = collect(service(tmp_path, download), tmp_path, selection)
    assert [row.filename for row in result.files] == [
        "cow-203.xlsx",
        "cow-0047.xlsx",
        "cow-203__02.xlsx",
    ]
    assert [row.status for row in result.files] == ["saved"] * 3
    assert (result.folder / "cow-203.xlsx").read_bytes() == b"203 (new girl)"
    assert (result.folder / "cow-203__02.xlsx").read_bytes() == b"203"
    assert not list(result.folder.glob("*.part"))
    manifest = json.loads((result.folder / "collection.json").read_text())
    assert manifest["items"][0]["original_b3"] == "203 (new girl)"
    assert manifest["items"][0]["sha256"] == hashlib.sha256(b"203 (new girl)").hexdigest()


def test_duplicate_emails_count_but_only_download_one_file(tmp_path):
    downloader = Downloader()
    result = collect(service(tmp_path, downloader), tmp_path, (candidate("eml"), candidate("msg")))
    assert [row.status for row in result.files] == ["saved", "duplicate"]
    assert len(downloader.calls) == 1
    assert result.files[0].filename == result.files[1].filename


def test_new_collections_are_unique_and_keep_old_files(tmp_path):
    app = service(tmp_path)
    a = collect(app, tmp_path, (candidate(),))
    b = collect(app, tmp_path, (candidate(),))
    assert a.folder != b.folder
    assert (a.folder / a.files[0].filename).is_file()


def test_duplicate_of_failed_export_does_not_implicitly_retry_the_link(tmp_path):
    downloader = Downloader([CollectionError("network", "Synthetic unavailable.")])
    result = collect(service(tmp_path, downloader), tmp_path, (candidate("eml"), candidate("msg")))
    assert [row.status for row in result.files] == ["failed", "failed"]
    assert len(downloader.calls) == 1
    assert "not automatically" in result.files[1].detail


def test_journal_and_manifest_never_persist_bearer_object_or_message_subject(tmp_path):
    selection = (candidate(),)
    result = collect(service(tmp_path), tmp_path, selection)
    for path in (tmp_path / "state" / "journal.db", result.folder / "collection.json"):
        raw = path.read_bytes()
        for forbidden in (
            selection[0].download_url,
            "export-synthetic-one.xlsx",
            selection[0].subject,
            selection[0].sender,
        ):
            assert forbidden.encode() not in raw


def test_partial_failure_keeps_success_and_retry_uses_same_frozen_selection(tmp_path):
    downloader = Downloader([b"203", CollectionError("network", "Synthetic unavailable.")])
    app = service(tmp_path, downloader)
    selection = (candidate(), candidate("message-2", "synthetic-two"))
    first = collect(app, tmp_path, selection)
    assert [row.status for row in first.files] == ["saved", "failed"]
    retry_download = Downloader([b"47"])
    resumed = collect(service(tmp_path, retry_download), tmp_path, selection, resume=first.folder)
    assert len(retry_download.calls) == 1
    assert [row.filename for row in resumed.files] == ["cow-203.xlsx", "cow-47.xlsx"]


def test_resume_rejects_changed_selection_without_network(tmp_path):
    original = collect(service(tmp_path), tmp_path, (candidate(),))
    downloader = Downloader()
    with pytest.raises(CollectionError, match="not the same reviewed emails"):
        collect(
            service(tmp_path, downloader), tmp_path, (candidate("new"),), resume=original.folder
        )
    assert not downloader.calls


@pytest.mark.parametrize("change", ["delete", "alter"])
def test_completed_files_missing_or_altered_are_never_overwritten(tmp_path, change):
    original = collect(service(tmp_path), tmp_path, (candidate(),))
    path = original.folder / original.files[0].filename
    if change == "delete":
        path.unlink()
    else:
        path.write_bytes(b"User edit")
    downloader = Downloader()
    with pytest.raises(CollectionError) as error:
        collect(service(tmp_path, downloader), tmp_path, (candidate(),), resume=original.folder)
    assert error.value.code == "file_changed"
    assert not downloader.calls
    if change == "alter":
        assert path.read_bytes() == b"User edit"


def prepared(tmp_path, payload=b"203"):
    store = CollectionStore(tmp_path / "state" / "journal.db")
    ident, folder = store.open_collection((candidate(),), tmp_path / "collections", None)
    store.update(
        ident,
        0,
        status="prepared",
        filename="cow-203.xlsx",
        cow="203",
        original_b3="203",
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    store.close()
    return folder


def test_crash_after_publish_verifies_file_without_redownload(tmp_path):
    folder = prepared(tmp_path)
    (folder / "cow-203.xlsx").write_bytes(b"203")
    downloader = Downloader()
    result = collect(service(tmp_path, downloader), tmp_path, (candidate(),), resume=folder)
    assert result.files[0].status == "saved"
    assert not downloader.calls


def test_crash_before_publish_can_refetch_and_verify_expected_bytes(tmp_path):
    folder = prepared(tmp_path)
    downloader = Downloader([b"203"])
    result = collect(service(tmp_path, downloader), tmp_path, (candidate(),), resume=folder)
    assert result.files[0].status == "saved"
    assert len(downloader.calls) == 1


def test_crash_retry_rejects_changed_remote_content(tmp_path):
    folder = prepared(tmp_path)
    with pytest.raises(CollectionError) as error:
        collect(service(tmp_path, Downloader([b"47"])), tmp_path, (candidate(),), resume=folder)
    assert error.value.code == "file_changed"
    assert not list(folder.glob("*.xlsx"))
    assert not list(folder.glob("*.part"))


def test_transient_resume_failure_does_not_forget_prepared_content_hash(tmp_path):
    folder = prepared(tmp_path)
    first = collect(
        service(tmp_path, Downloader([CollectionError("network", "Synthetic unavailable.")])),
        tmp_path,
        (candidate(),),
        resume=folder,
    )
    assert first.files[0].status == "failed"
    with pytest.raises(CollectionError) as error:
        collect(service(tmp_path, Downloader([b"47"])), tmp_path, (candidate(),), resume=folder)
    assert error.value.code == "file_changed"
    assert not list(folder.glob("*.xlsx"))


def test_cancel_before_start_creates_nothing(tmp_path):
    stop = Event()
    stop.set()
    with pytest.raises(CollectionCancelled):
        collect(service(tmp_path), tmp_path, (candidate(),), stop=stop)
    assert not (tmp_path / "state").exists()


def test_cancel_keeps_saved_and_marks_remaining_then_resumes(tmp_path):
    stop = Event()
    selection = (
        candidate(),
        candidate("second", "synthetic-two"),
        candidate("third", "synthetic-three"),
    )

    def progress(event):
        if event.current == 1:
            stop.set()

    class Cooperative(Downloader):
        def download(self, url, path, event):
            if event.is_set():
                raise CollectionCancelled()
            return super().download(url, path, event)

    first = collect(
        service(tmp_path, Cooperative()), tmp_path, selection, stop=stop, progress=progress
    )
    assert first.cancelled
    assert [row.status for row in first.files] == ["saved", "cancelled", "cancelled"]
    resumed = collect(service(tmp_path), tmp_path, selection, resume=first.folder)
    assert [row.status for row in resumed.files] == ["saved"] * 3


def test_cancellation_during_completed_file_verification_preserves_saved_state(
    tmp_path, monkeypatch
):
    original = collect(service(tmp_path), tmp_path, (candidate(),))

    def cancel(*_):
        raise CollectionCancelled()

    monkeypatch.setattr("smaxtec.application.collection_service._file_hash", cancel)
    result = collect(service(tmp_path), tmp_path, (candidate(),), resume=original.folder)
    assert result.cancelled and result.files[0].status == "saved"


def test_invalid_and_ambiguous_candidates_do_not_download(tmp_path):
    downloader = Downloader()
    result = collect(service(tmp_path, downloader), tmp_path, (candidate(issue="Ambiguous"),))
    assert result.files[0].status == "failed"
    assert not downloader.calls


def test_failed_identity_leaves_no_misnamed_or_staged_file(tmp_path):
    def bad(_):
        raise CollectionError("identity", "Synthetic invalid identity.")

    result = collect(service(tmp_path, inspector=bad), tmp_path, (candidate(),))
    assert result.files[0].status == "failed"
    assert not list(result.folder.glob("*.xlsx"))
    assert not list(result.folder.glob("*.part"))


def test_collection_lock_blocks_a_second_worker(tmp_path):
    with collection_lock(tmp_path):
        with pytest.raises(CollectionError) as error, collection_lock(tmp_path):
            pytest.fail("Acquired twice")
        assert error.value.code == "collection_busy"


def test_unknown_journal_schema_is_not_modified(tmp_path):
    import sqlite3

    path = tmp_path / "newer.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 500")
    with pytest.raises(CollectionError) as error:
        CollectionStore(path)
    assert error.value.code == "journal_version"


def test_unknown_resume_folder_does_not_adopt_user_files(tmp_path):
    with pytest.raises(CollectionError) as error:
        collect(service(tmp_path), tmp_path, (candidate(),), resume=tmp_path)
    assert error.value.code == "collection_unknown"


def test_real_workbook_inspector_is_used_by_default(tmp_path):
    from test_workbooks import inline, package, write_package

    source = write_package(tmp_path, package((inline("00203 (new girl)"),)))
    downloader = Downloader([source.read_bytes()])
    app = CollectionService(tmp_path / "state" / "journal.db", downloader=downloader)
    result = collect(app, tmp_path, (candidate(),))
    assert result.files[0].filename == "cow-00203.xlsx"
    assert (result.folder / result.files[0].filename).read_bytes() == source.read_bytes()


def test_filename_collision_does_not_replace_unrelated_file(tmp_path):
    folder = prepared(tmp_path, b"203")
    # This is not the journal's prepared name, so it is a separate existing cow export.
    (folder / "cow-203__02.xlsx").write_bytes(b"Leave me")
    result = collect(
        service(tmp_path, Downloader([b"203"])), tmp_path, (candidate(),), resume=folder
    )
    assert result.files[0].filename == "cow-203.xlsx"
    assert (folder / "cow-203__02.xlsx").read_bytes() == b"Leave me"
