from datetime import date
from threading import Event

import pytest

from smaxtec.application.exports import (
    ExportError,
    ExportFailureCode,
    ExportRequest,
    ExportStage,
    Farm,
)
from smaxtec.application.login import Credentials, LoginCancelled

SYNTHETIC_CREDENTIALS = Credentials("analyst@example.test", "synthetic-password")


def connect_and_discover(session):
    session.connect(SYNTHETIC_CREDENTIALS, lambda _event: None, Event())
    progress = []
    farms = session.discover_farms(progress.append, Event())
    return farms, progress


def request(*cows):
    return ExportRequest(Farm("Maes Gwyrdd LTD"), cows, date(2026, 8, 31), date(2026, 9, 7))


def test_farms_are_discovered_from_the_live_page_structure(session):
    farms, progress = connect_and_discover(session)
    assert farms == (Farm("Maes Gwyrdd LTD"), Farm("TYB Farms LTD"))
    assert [event.stage for event in progress] == [
        ExportStage.DISCOVERING_FARMS,
        ExportStage.FARMS_READY,
    ]


def test_multiple_exact_cows_each_submit_one_measured_data_export(session, website):
    connect_and_discover(session)
    progress = []
    result = session.request_exports(request("57", "257"), progress.append, Event())
    assert result.requested == ("57", "257")
    assert result.skipped_as_already_attempted == ()
    assert website.exports == [
        {"farm": "maes", "cow": "57", "from": "31/08/2026", "to": "07/09/2026", "kind": "measured"},
        {
            "farm": "maes",
            "cow": "257",
            "from": "31/08/2026",
            "to": "07/09/2026",
            "kind": "measured",
        },
    ]
    assert [event.stage for event in progress].count(ExportStage.COW_COMPLETE) == 2


def test_partial_search_never_selects_a_different_cow(session, website):
    connect_and_discover(session)
    result = session.request_exports(request("57"), lambda _event: None, Event())
    assert result.requested == ("57",)
    assert [item["cow"] for item in website.exports] == ["57"]


def test_missing_exact_cow_stops_before_any_export(session, website):
    connect_and_discover(session)
    with pytest.raises(ExportError) as caught:
        session.request_exports(request("999"), lambda _event: None, Event())
    assert caught.value.code == ExportFailureCode.COW_NOT_FOUND
    assert caught.value.completed == ()
    assert website.exports == []


def test_duplicate_exact_cow_stops_before_any_export(session, website):
    connect_and_discover(session)
    website.mode = "duplicate-cow"
    with pytest.raises(ExportError) as caught:
        session.request_exports(request("57"), lambda _event: None, Event())
    assert caught.value.code == ExportFailureCode.COW_AMBIGUOUS
    assert caught.value.completed == ()
    assert website.exports == []


def test_unknown_farm_stops_before_navigation_or_export(session, website):
    connect_and_discover(session)
    bad_request = ExportRequest(Farm("Missing Farm"), ("57",), date(2026, 8, 31), date(2026, 9, 7))
    with pytest.raises(ExportError) as caught:
        session.request_exports(bad_request, lambda _event: None, Event())
    assert caught.value.code == ExportFailureCode.FARM_NOT_FOUND
    assert website.exports == []


def test_completed_requests_are_not_repeated_in_same_session(session, website):
    connect_and_discover(session)
    first = session.request_exports(request("57"), lambda _event: None, Event())
    second = session.request_exports(request("57"), lambda _event: None, Event())
    assert first.requested == ("57",)
    assert second.requested == ()
    assert second.skipped_as_already_attempted == ("57",)
    assert len(website.exports) == 1


def test_partial_failure_reports_completed_and_does_not_retry_attempts(session, website):
    connect_and_discover(session)
    website.mode = "reject-cow-257"
    with pytest.raises(ExportError) as caught:
        session.request_exports(request("57", "257"), lambda _event: None, Event())
    assert caught.value.code == ExportFailureCode.EXPORT_REJECTED
    assert caught.value.completed == ("57",)
    assert caught.value.attempted == ("57", "257")
    assert [item["cow"] for item in website.exports] == ["57"]

    result = session.request_exports(request("57", "257"), lambda _event: None, Event())
    assert result.requested == ()
    assert result.skipped_as_already_attempted == ("57", "257")
    assert len(website.exports) == 1


def test_cancellation_between_cows_does_not_submit_the_next_one(session, website):
    connect_and_discover(session)
    stop = Event()

    def cancel_after_first(event):
        if event.stage == ExportStage.COW_COMPLETE:
            stop.set()

    with pytest.raises(LoginCancelled):
        session.request_exports(request("57", "257"), cancel_after_first, stop)
    assert [item["cow"] for item in website.exports] == ["57"]
