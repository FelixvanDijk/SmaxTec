"""Bounded, read-only smaXtec Public API v2 access, apart from explicit sign-in.

The current public Swagger defines query parameters for reads. Authentication
uses a JSON body, verified against the live endpoint, so passwords never enter
request URLs. All response content stays inside the application data boundary.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from threading import Event
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from smaxtec.application.api_data import (
    ApiCancelled,
    ApiCatalog,
    ApiEntity,
    ApiError,
    ApiFarm,
    ApiLactation,
    ApiMetric,
)
from smaxtec.application.login import Credentials

API_BASE = "https://api.smaxtec.com/api/v2"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_CATALOG_ITEMS = 50000
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")
_MESSAGES = {
    "api_login": "smaXtec did not accept this sign-in. Check your account details and API access.",
    "api_terms": "Sign into smaXtec Web and review the account terms before connecting here.",
    "api_session": "Your smaXtec API session has ended. Connect again to continue.",
    "api_permission": "This smaXtec account does not have permission to read the selected data.",
    "api_throttled": "smaXtec temporarily limited requests. Wait a few minutes and try again.",
    "api_timeout": "smaXtec did not respond in time. Try again or select a smaller date range.",
    "api_unavailable": (
        "smaXtec could not be reached. Check your internet connection and try again."
    ),
    "api_response": "smaXtec returned an unsupported response. This operation could not complete.",
    "api_size": "This smaXtec response is too large. Select fewer targets or a shorter period.",
    "api_selection": "Choose a farm and target from your connected smaXtec account.",
    "api_parameters": (
        "smaXtec could not provide this selection. Check the period and measurements; "
        "the selected target may not have available data."
    ),
    "api_metrics": (
        "smaXtec could not list measurements for this target. It may not have available "
        "sensor data, or your account may not have access."
    ),
    "api_timezone": (
        "smaXtec returned an unknown farm timezone. Its dates cannot be interpreted safely."
    ),
}


def _error(code: str) -> ApiError:
    return ApiError(code, _MESSAGES[code])


def _check_stop(stop: Event) -> None:
    if stop.is_set():
        raise ApiCancelled


def _id(value: Any) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise _error("api_response")
    return value


def _text(value: Any, *, maximum: int = 1000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > maximum:
        raise _error("api_response")
    return "".join(character for character in value if character >= " " and character != "\x7f")


def _objects(value: Any, *, maximum: int = MAX_CATALOG_ITEMS) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise _error("api_response")
    if len(value) > maximum:
        raise _error("api_size")
    return value


def _utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise _error("api_parameters")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 100:
        raise _error("api_response")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _error("api_response") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error("api_response")
    return parsed.astimezone(UTC)


def _lactations(item: dict[str, Any]) -> tuple[ApiLactation, ...]:
    """Read usable lifecycle cycles without making optional metadata a farm blocker."""
    lifecycle = item.get("lifecycle")
    if not isinstance(lifecycle, dict):
        return ()
    cycles = lifecycle.get("cycles", [])
    if not isinstance(cycles, list) or len(cycles) > 1000:
        cycles = []
    candidates = [lifecycle, *cycles]
    result: dict[tuple[int, datetime], ApiLactation] = {}
    for cycle in candidates:
        if not isinstance(cycle, dict):
            continue
        number = cycle.get("lactation_number")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            continue
        try:
            calving = _optional_timestamp(cycle.get("last_calving_date"))
            dry_off = _optional_timestamp(cycle.get("dry_off_date"))
        except ApiError:
            continue
        if calving is None:
            continue
        if dry_off is not None and dry_off < calving:
            # A timestamp before this calving cannot close the current cycle.
            dry_off = None
        result[(number, calving)] = ApiLactation(number, calving, dry_off)
    return tuple(sorted(result.values(), key=lambda value: value.calving_utc))


@dataclass(frozen=True)
class _Session:
    token: str = field(repr=False)
    expires_at: float | None = None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class SmaxtecApiClient:
    """Use from one worker at a time; no credentials or token files are created."""

    def __init__(self, *, opener: Any = None, request_timeout_seconds: float = 45) -> None:
        self._opener = opener if opener is not None else build_opener(_NoRedirect())
        self.request_timeout_seconds = request_timeout_seconds
        self._session: _Session | None = None
        self._farms: tuple[ApiFarm, ...] = ()
        self._entities: dict[tuple[str, str, str], ApiEntity] = {}

    def disconnect(self) -> None:
        self._session = None
        self._farms = ()
        self._entities.clear()

    def _request(
        self,
        path: str,
        stop: Event,
        *,
        params: list[tuple[str, str | int]] | None = None,
        credentials: Credentials | None = None,
        metrics_request: bool = False,
    ) -> Any:
        _check_stop(stop)
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        payload = None
        if credentials is not None:
            if path != "/users/credentials" or params:
                raise _error("api_selection")
            headers["Content-Type"] = "application/json"
            payload = json.dumps(
                {"user": credentials.username, "password": credentials.password}
            ).encode("utf-8")
        else:
            session = self._session
            if session is None or (
                session.expires_at is not None and monotonic() >= session.expires_at
            ):
                self.disconnect()
                raise _error("api_session")
            headers["Authorization"] = "Bearer " + session.token
        url = API_BASE + path
        if params:
            url += "?" + urlencode(params)
        request = Request(url, data=payload, headers=headers, method="POST" if payload else "GET")
        deadline = monotonic() + max(90, self.request_timeout_seconds * 2)
        try:
            with self._opener.open(request, timeout=self.request_timeout_seconds) as response:
                if response.getcode() != 200:
                    self._http_error(response.getcode(), credentials is not None, metrics_request)
                content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0]
                encoding = str(response.headers.get("Content-Encoding", "identity")).lower()
                if content_type.lower() != "application/json" or encoding != "identity":
                    raise _error("api_response")
                length = response.headers.get("Content-Length")
                if length is not None:
                    try:
                        length = int(length)
                    except (TypeError, ValueError):
                        raise _error("api_response") from None
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise _error("api_size")
                raw = bytearray()
                while True:
                    _check_stop(stop)
                    if monotonic() >= deadline:
                        raise _error("api_timeout")
                    chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise _error("api_size")
        except HTTPError as error:
            status = error.code
            error.close()
            self._http_error(status, credentials is not None, metrics_request)
            raise AssertionError("unreachable") from None
        except TimeoutError:
            raise _error("api_timeout") from None
        except URLError as error:
            code = "api_timeout" if isinstance(error.reason, TimeoutError) else "api_unavailable"
            raise _error(code) from None
        except OSError:
            raise _error("api_unavailable") from None
        _check_stop(stop)
        try:
            return json.loads(raw.decode("utf-8-sig"))
        except (UnicodeError, ValueError, RecursionError):
            raise _error("api_response") from None

    def _http_error(self, status: int, signing_in: bool, metrics_request: bool) -> None:
        if status == 401:
            self.disconnect()
            raise _error("api_login" if signing_in else "api_session")
        if status == 403:
            raise _error("api_permission")
        if status == 429:
            raise _error("api_throttled")
        if status in {408, 504}:
            raise _error("api_timeout")
        if status in {400, 404, 422}:
            raise _error(
                "api_login"
                if signing_in
                else "api_metrics"
                if metrics_request
                else "api_parameters"
            )
        raise _error("api_unavailable" if status >= 500 else "api_response")

    def connect(self, credentials: Credentials, stop: Event) -> tuple[ApiFarm, ...]:
        self.disconnect()
        try:
            result = self._request("/users/credentials", stop, credentials=credentials)
            if not isinstance(result, dict):
                raise _error("api_response")
            if result.get("terms_accepted") is False:
                raise _error("api_terms")
            token = result.get("api_token")
            if (
                not isinstance(token, str)
                or not 1 <= len(token) <= 32768
                or any(character.isspace() or ord(character) < 33 for character in token)
            ):
                raise _error("api_login")
            user_id = _id(result.get("user_id"))
            expiry = result.get("expires_in")
            if expiry is not None and (type(expiry) is not int or expiry <= 0):
                raise _error("api_response")
            self._session = _Session(token, monotonic() + expiry if expiry is not None else None)
            profile = self._request(f"/users/{user_id}", stop)
            if not isinstance(profile, dict) or _id(profile.get("_id")) != user_id:
                raise _error("api_response")
            if profile.get("terms_accepted") is False:
                raise _error("api_terms")
            if profile.get("active") is False:
                raise _error("api_permission")
            farms: list[ApiFarm] = []
            seen: set[str] = set()
            for item in _objects(profile.get("user_organisations"), maximum=5000):
                farm_id = _id(item.get("organisation_id"))
                if farm_id in seen:
                    raise _error("api_response")
                seen.add(farm_id)
                timezone = _text(item.get("timezone"), maximum=100)
                try:
                    ZoneInfo(timezone)
                except (ValueError, ZoneInfoNotFoundError):
                    raise _error("api_timezone") from None
                farms.append(ApiFarm(farm_id, _text(item.get("name")) or farm_id, timezone))
            _check_stop(stop)
            self._farms = tuple(farms)
            return self._farms
        except Exception:
            self.disconnect()
            raise

    def _farm(self, farm: ApiFarm) -> None:
        if farm not in self._farms:
            raise _error("api_session" if self._session is None else "api_selection")

    def _entity(self, entity: ApiEntity) -> None:
        self._farm(entity.farm)
        if self._entities.get((entity.farm.id, entity.kind, entity.id)) != entity:
            raise _error("api_selection")

    def catalog(self, farm: ApiFarm, archived: bool, stop: Event) -> ApiCatalog:
        self._farm(farm)
        organisation = self._request(f"/organisations/{farm.id}", stop)
        if not isinstance(organisation, dict) or _id(organisation.get("_id")) != farm.id:
            raise _error("api_response")
        if organisation.get("timezone") != farm.timezone:
            raise _error("api_timezone")
        raw_animals = self._request(
            f"/organisations/{farm.id}/animals",
            stop,
            params=[("archived", "true" if archived else "false")],
        )
        animals: list[ApiEntity] = []
        groups: list[ApiEntity] = []
        devices: list[ApiEntity] = []
        for item in _objects(raw_animals):
            if item.get("organisation_id") != farm.id:
                raise _error("api_response")
            if type(item.get("archived", False)) is not bool:
                raise _error("api_response")
            animals.append(
                ApiEntity(
                    _id(item.get("_id")),
                    "animals",
                    farm,
                    _text(item.get("mark")),
                    _text(item.get("name")),
                    _text(item.get("official_id")),
                    _text(item.get("location") or item.get("group_id")),
                    item.get("archived", False),
                    _lactations(item),
                )
            )
        for item in _objects(organisation.get("animal_groups", [])):
            groups.append(
                ApiEntity(
                    _id(item.get("_id")),
                    "groups",
                    farm,
                    "",
                    _text(item.get("name")),
                    group=_text(item.get("location")),
                )
            )
        device_ids = organisation.get("devices", [])
        if not isinstance(device_ids, list) or len(device_ids) > MAX_CATALOG_ITEMS:
            raise _error("api_response")
        for device_id in device_ids:
            device_id = _id(device_id)
            devices.append(ApiEntity(device_id, "devices", farm, device_id, ""))
        discovered: dict[tuple[str, str, str], ApiEntity] = {}
        for entity in [*animals, *groups, *devices]:
            key = (farm.id, entity.kind, entity.id)
            if key in discovered:
                raise _error("api_response")
            discovered[key] = entity
        _check_stop(stop)
        self._entities.update(discovered)
        return ApiCatalog(
            farm,
            tuple(animals),
            tuple(groups),
            tuple(devices),
            {"organisation": organisation, "animals": raw_animals},
        )

    def metrics(self, entity: ApiEntity, stop: Event) -> tuple[ApiMetric, ...]:
        self._entity(entity)
        values = self._request(
            f"/data/{entity.kind}/{entity.id}/metrics", stop, metrics_request=True
        )
        metrics: list[ApiMetric] = []
        seen: set[str] = set()
        for value in _objects(values, maximum=1000):
            code = _text(value.get("metric"), maximum=200)
            units = value.get("available_units", [])
            if not code or code in seen or not isinstance(units, list) or len(units) > 100:
                raise _error("api_response")
            seen.add(code)
            metrics.append(ApiMetric(code, tuple(_text(unit, maximum=100) for unit in units)))
        return tuple(metrics)

    def data(
        self,
        entity: ApiEntity,
        metrics: tuple[str, ...],
        start: datetime,
        end: datetime,
        aggregation: str,
        stop: Event,
    ) -> list[dict[str, Any]]:
        self._entity(entity)
        from_date, to_date = _utc(start), _utc(end)
        if (
            start >= end
            or not metrics
            or len(metrics) > 1000
            or any(not isinstance(metric, str) or not 1 <= len(metric) <= 200 for metric in metrics)
            or len(set(metrics)) != len(metrics)
            or aggregation not in {"native", "10minutes", "hourly", "daily"}
        ):
            raise _error("api_parameters")
        params: list[tuple[str, str | int]] = [
            ("from_date", from_date),
            ("to_date", to_date),
            ("timestamp_format", "iso"),
            ("tz_mode", "utc"),
            ("timezone", "UTC"),
            *(("metrics", metric) for metric in metrics),
        ]
        if aggregation != "native":
            params.append(("aggregation_period", aggregation))
        return _objects(self._request(f"/data/{entity.kind}/{entity.id}.json", stop, params=params))

    def health_index(self, farm: ApiFarm, start: date, end: date, stop: Event) -> Any:
        self._farm(farm)
        if type(start) is not date or type(end) is not date or start > end:
            raise _error("api_parameters")
        return _objects(
            self._request(
                f"/kpis/organisations/{farm.id}/health_index",
                stop,
                params=[("start", start.isoformat()), ("end", end.isoformat())],
            )
        )
