from datetime import date, timedelta

import pytest

from smaxtec.application.exports import (
    ExportRequest,
    Farm,
    parse_cow_numbers,
    parse_user_date,
)


def test_cow_numbers_preserve_order_leading_zeroes_and_remove_duplicates():
    assert parse_cow_numbers("057, 57\n057; 608") == ("057", "57", "608")


@pytest.mark.parametrize("value", ["", "  \n , ; "])
def test_cow_numbers_are_required(value):
    with pytest.raises(ValueError, match="at least one"):
        parse_cow_numbers(value)


def test_request_formats_site_dates_and_normalizes_duplicates():
    request = ExportRequest(
        Farm("  Maes   Gwyrdd LTD "),
        ("57", "57", "257"),
        date(2026, 8, 31),
        date(2026, 9, 7),
    )
    assert request.farm.name == "Maes Gwyrdd LTD"
    assert request.cow_numbers == ("57", "257")
    assert request.site_start_date == "31/08/2026"
    assert request.site_end_date == "07/09/2026"


def test_request_rejects_reversed_dates():
    with pytest.raises(ValueError, match="start date"):
        ExportRequest(Farm("A Farm"), ("57",), date(2026, 9, 7), date(2026, 9, 6))


def test_user_date_is_parsed_as_day_month_year_without_year_mutation():
    assert parse_user_date("01/09/2026", "start date") == date(2026, 9, 1)


@pytest.mark.parametrize("value", ["1/9/2026", "01-09-2026", "31/02/2026", "__/09/2026"])
def test_user_date_requires_an_exact_real_dd_mm_yyyy_value(value):
    with pytest.raises(ValueError):
        parse_user_date(value, "start date")


def test_request_rejects_future_end_date():
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="future"):
        ExportRequest(Farm("A Farm"), ("57",), date.today(), tomorrow)
