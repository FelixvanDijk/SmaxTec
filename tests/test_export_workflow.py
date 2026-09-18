from datetime import date
from threading import Event

import pytest

from smaxtec.application.exports import (
    CowExport,
    ExportError,
    ExportFailureCode,
    ExportRequest,
    ExportStage,
    Farm,
)
from smaxtec.application.lifecycle import LifecycleTarget
from smaxtec.application.login import Credentials, LoginCancelled

SYNTHETIC_CREDENTIALS = Credentials("analyst@example.test", "synthetic-password")


def connect_and_discover(session):
    session.connect(SYNTHETIC_CREDENTIALS, lambda _event: None, Event())
    progress = []
    farms = session.discover_farms(progress.append, Event())
    return farms, progress


def request(*cows):
    return ExportRequest.for_cows(
        Farm("Maes Gwyrdd LTD"), cows, date(2026, 8, 31), date(2026, 9, 7)
    )


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
    assert result.requested == request("57", "257").entries
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


def test_site_date_mutation_is_detected_before_export_submission(session, website):
    connect_and_discover(session)
    website.mode = "mutate-start-date"
    with pytest.raises(ExportError) as caught:
        session.request_exports(request("57"), lambda _event: None, Event())
    assert caught.value.code == ExportFailureCode.EXPORT_REJECTED
    assert "did not accept" in str(caught.value)
    assert website.exports == []


def test_partial_search_never_selects_a_different_cow(session, website):
    connect_and_discover(session)
    result = session.request_exports(request("57"), lambda _event: None, Event())
    assert result.requested == request("57").entries
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
    bad_request = ExportRequest(Farm("Missing Farm"), request("57").entries)
    with pytest.raises(ExportError) as caught:
        session.request_exports(bad_request, lambda _event: None, Event())
    assert caught.value.code == ExportFailureCode.FARM_NOT_FOUND
    assert website.exports == []


def test_completed_requests_are_not_repeated_in_same_session(session, website):
    connect_and_discover(session)
    first = session.request_exports(request("57"), lambda _event: None, Event())
    second = session.request_exports(request("57"), lambda _event: None, Event())
    assert first.requested == request("57").entries
    assert second.requested == ()
    assert second.skipped_as_already_attempted == request("57").entries
    assert len(website.exports) == 1


def test_lact_dim_uses_exact_cow_diagrams_and_returns_to_search(session, website):
    connect_and_discover(session)
    targets = (
        LifecycleTarget("Maes Gwyrdd LTD", "57"),
        LifecycleTarget("Maes Gwyrdd LTD", "657"),
    )
    progress = []

    readings = session.read_lact_dim(targets, progress.append, Event())

    assert [(item.target.cow, item.lactation, item.dim) for item in readings] == [
        ("57", 7, 216),
        ("657", 2, 88),
    ]
    assert progress[-1].current == 2
    assert website.exports == []


def test_lact_dim_skips_a_disabled_diagram_and_continues(session, website):
    connect_and_discover(session)
    website.mode = "diagram-disabled"
    targets = (
        LifecycleTarget("Maes Gwyrdd LTD", "257"),
        LifecycleTarget("Maes Gwyrdd LTD", "357"),
    )

    readings = session.read_lact_dim(targets, lambda _event: None, Event())

    assert not readings[0].available
    assert "unavailable" in readings[0].detail
    assert (readings[1].lactation, readings[1].dim) == (3, 42)
    assert website.exports == []


def test_partial_failure_reports_completed_and_does_not_retry_attempts(session, website):
    connect_and_discover(session)
    website.mode = "reject-cow-257"
    with pytest.raises(ExportError) as caught:
        session.request_exports(request("57", "257"), lambda _event: None, Event())
    assert caught.value.code == ExportFailureCode.EXPORT_REJECTED
    assert caught.value.completed == request("57").entries
    assert caught.value.attempted == request("57", "257").entries
    assert [item["cow"] for item in website.exports] == ["57"]

    result = session.request_exports(request("57", "257"), lambda _event: None, Event())
    assert result.requested == ()
    assert result.skipped_as_already_attempted == request("57", "257").entries
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


def test_individual_dates_are_sent_for_each_cow_including_repeated_cow_with_new_period(
    session, website
):
    connect_and_discover(session)
    entries = (
        CowExport("57", date(2026, 9, 1), date(2026, 9, 3)),
        CowExport("257", date(2026, 8, 4), date(2026, 8, 12)),
        CowExport("57", date(2026, 7, 13), date(2026, 7, 13)),
    )
    result = session.request_exports(
        ExportRequest(Farm("Maes Gwyrdd LTD"), entries), lambda _event: None, Event()
    )
    assert result.requested == entries
    assert [(item["cow"], item["from"], item["to"]) for item in website.exports] == [
        ("57", "01/09/2026", "03/09/2026"),
        ("257", "04/08/2026", "12/08/2026"),
        ("57", "13/07/2026", "13/07/2026"),
    ]
