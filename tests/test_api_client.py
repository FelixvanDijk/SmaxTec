"""Synthetic HTTP tests for the read-only smaXtec Public API adapter."""

import io
import json
from datetime import UTC, datetime
from threading import Event
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from smaxtec.adapters.smaxtec.api import SmaxtecApiClient
from smaxtec.application.api_data import ApiError
from smaxtec.application.login import Credentials

USER_ID = "user-synthetic-001"
FARM_ID = "farm-synthetic-001"
ANIMAL_ID = "animal-synthetic-001"
TOKEN = "synthetic-api-token"


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())
        self.headers = {"Content-Type": "application/json", "Content-Encoding": "identity"}

    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def connected_client(*extra_responses):
    opener = Opener(
        Response(
            {
                "api_token": TOKEN,
                "user_id": USER_ID,
                "expires_in": 3600,
                "terms_accepted": True,
            }
        ),
        Response(
            {
                "_id": USER_ID,
                "active": True,
                "terms_accepted": True,
                "user_organisations": [
                    {
                        "organisation_id": FARM_ID,
                        "name": "Synthetic Farm",
                        "timezone": "Europe/London",
                    }
                ],
            }
        ),
        *extra_responses,
    )
    client = SmaxtecApiClient(opener=opener, request_timeout_seconds=7)
    farms = client.connect(Credentials("analyst@example.test", "synthetic-password"), Event())
    return client, farms[0], opener


def test_sign_in_uses_json_body_and_never_places_credentials_in_url_or_repr():
    client, farm, opener = connected_client()
    request, timeout = opener.calls[0]
    assert request.full_url.endswith("/users/credentials")
    assert "analyst" not in request.full_url
    assert "password" not in request.full_url
    assert json.loads(request.data) == {
        "user": "analyst@example.test",
        "password": "synthetic-password",
    }
    assert timeout == 7
    assert TOKEN not in repr(client)
    assert TOKEN not in repr(client._session)
    assert farm.name == "Synthetic Farm"


def test_catalog_and_measurement_request_preserve_exact_entity_identity_and_query_shape():
    client, farm, opener = connected_client(
        Response(
            {
                "_id": FARM_ID,
                "name": "Synthetic Farm",
                "timezone": "Europe/London",
                "devices": ["device-synthetic-001"],
                "animal_groups": [{"_id": "group-synthetic-001", "name": "Milking"}],
            }
        ),
        Response(
            [
                {
                    "_id": ANIMAL_ID,
                    "organisation_id": FARM_ID,
                    "mark": "57",
                    "name": "57",
                    "official_id": "UK000000000057",
                    "archived": False,
                    "lifecycle": {
                        "lactation_number": 3,
                        "last_calving_date": "2026-08-31T23:00:00Z",
                        "dry_off_date": None,
                        "cycles": [
                            {
                                "lactation_number": 2,
                                "last_calving_date": "2025-09-02T08:00:00+00:00",
                                "dry_off_date": "2026-07-01T08:00:00+00:00",
                            }
                        ],
                    },
                },
                {
                    "_id": "animal-synthetic-657",
                    "organisation_id": FARM_ID,
                    "mark": "657",
                    "name": "New girl",
                    "official_id": "UK000000000657",
                    "archived": False,
                },
            ]
        ),
        Response([{"metric": "temp", "available_units": ["celsius"]}]),
        Response([{"_id": ANIMAL_ID, "metric": "temp", "unit": "celsius", "data": []}]),
    )
    catalog = client.catalog(farm, False, Event())
    assert [animal.number for animal in catalog.animals] == ["57", "657"]
    animal = catalog.animals[0]
    assert [cycle.number for cycle in animal.lactations] == [2, 3]
    assert animal.lactations[-1].calving_utc == datetime(2026, 8, 31, 23, tzinfo=UTC)
    assert animal.lactations[-1].dry_off_utc is None
    assert client.metrics(animal, Event())[0].code == "temp"
    result = client.data(
        animal,
        ("temp", "act"),
        datetime(2026, 9, 1, tzinfo=UTC),
        datetime(2026, 9, 2, tzinfo=UTC),
        "hourly",
        Event(),
    )
    assert result[0]["metric"] == "temp"
    query = parse_qs(urlsplit(opener.calls[-1][0].full_url).query)
    assert query["metrics"] == ["temp", "act"]
    assert query["aggregation_period"] == ["hourly"]
    assert query["timezone"] == ["UTC"]
    assert query["tz_mode"] == ["utc"]
    assert opener.calls[-1][0].headers["Authorization"] == "Bearer " + TOKEN


def test_metric_400_is_target_specific_and_session_is_retained():
    error = HTTPError("https://api.smaxtec.com", 400, "bad", {}, None)
    client, farm, _opener = connected_client(
        Response(
            {
                "_id": FARM_ID,
                "timezone": "Europe/London",
                "devices": [],
                "animal_groups": [],
            }
        ),
        Response(
            [
                {
                    "_id": ANIMAL_ID,
                    "organisation_id": FARM_ID,
                    "mark": "57",
                    "archived": False,
                }
            ]
        ),
        error,
    )
    animal = client.catalog(farm, False, Event()).animals[0]
    with pytest.raises(ApiError) as captured:
        client.metrics(animal, Event())
    assert captured.value.code == "api_metrics"
    assert client._session is not None
    assert "400" not in str(captured.value)


def test_optional_lifecycle_variants_never_block_farm_catalogue():
    client, farm, _opener = connected_client(
        Response(
            {
                "_id": FARM_ID,
                "timezone": "Europe/London",
                "devices": [],
                "animal_groups": [],
            }
        ),
        Response(
            [
                {
                    "_id": ANIMAL_ID,
                    "organisation_id": FARM_ID,
                    "mark": "57",
                    "archived": False,
                    "lifecycle": {
                        "lactation_number": 3,
                        "last_calving_date": "2026-08-31T23:00:00Z",
                        "cycles": [
                            None,
                            {
                                "lactation_number": "2",
                                "last_calving_date": "2025-01-01T00:00:00Z",
                            },
                            {
                                "lactation_number": 2,
                                "last_calving_date": "not-a-date",
                            },
                            {
                                "lactation_number": 1,
                                "last_calving_date": "2024-01-01T00:00:00Z",
                                "dry_off_date": {"unexpected": "shape"},
                            },
                        ],
                    },
                },
                {
                    "_id": "animal-synthetic-657",
                    "organisation_id": FARM_ID,
                    "mark": "657",
                    "archived": False,
                    "lifecycle": ["unexpected", "shape"],
                },
            ]
        ),
    )

    catalog = client.catalog(farm, False, Event())

    assert [animal.number for animal in catalog.animals] == ["57", "657"]
    assert [cycle.number for cycle in catalog.animals[0].lactations] == [3]
    assert catalog.animals[1].lactations == ()


def test_cancelled_request_never_opens_network_connection():
    opener = Opener()
    client = SmaxtecApiClient(opener=opener)
    stop = Event()
    stop.set()
    with pytest.raises(Exception) as captured:
        client.connect(Credentials("analyst@example.test", "secret"), stop)
    assert captured.value.__class__.__name__ == "ApiCancelled"
    assert opener.calls == []
