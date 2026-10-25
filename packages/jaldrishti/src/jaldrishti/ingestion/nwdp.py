"""Normalizer for the NWDP Assam hourly river-level CKAN resource.

The public resource is useful for proving ingestion, but it is not yet a
statewide operational feed.  In particular, it omits a stable station ID,
timezone, datum, warning level, danger level, river, and basin.  This adapter
preserves those absences instead of filling them with assumptions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

NWDP_DATASET_URL = (
    "https://nwdp.nwic.gov.in/dataset/river-water-level-telemetry-hourly-assam-department"
)
NWDP_RESOURCE_ID = "847f5630-f231-46c0-922d-0f2f379a5cb8"
NWDP_DATASTORE_URL = (
    f"https://nwdp.nwic.gov.in/api/3/action/datastore_search?resource_id={NWDP_RESOURCE_ID}"
)
NWDP_SOURCE = "Assam WRD / National Water Data Portal"
WATER_LEVEL_FIELD = "River Water Level Telemetry Hourly (meter)"
SOURCE_TIME_FIELD = "Data Acquisition Time"

PILOT_CAVEATS = (
    "The public resource currently exposes incomplete statewide station coverage.",
    "The source does not publish a stable station identifier.",
    "Observation timestamps do not include a timezone.",
    "Warning level, danger level, and gauge datum are not published.",
    "River and basin fields may be absent.",
)


@dataclass(frozen=True, slots=True)
class NWDPStation:
    id: str
    source_record_id: str
    name: str
    longitude: float
    latitude: float
    district_name: str | None
    district_lgd_code: str | None
    river_name: str | None
    basin_name: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NWDPObservation:
    id: str
    station_id: str
    source_record_id: str
    source_observed_at: str
    source_observed_at_local: datetime
    water_level_m: float
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NWDPBatch:
    resource_id: str
    source_version: str
    fetched_at: datetime
    raw_sha256: str
    source_total: int
    stations: tuple[NWDPStation, ...]
    observations: tuple[NWDPObservation, ...]
    caveats: tuple[str, ...] = PILOT_CAVEATS


def _present_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text == "-" else text


def _required_text(row: dict[str, Any], field: str) -> str:
    value = _present_text(row.get(field))
    if value is None:
        raise ValueError(f"NWDP row is missing {field!r}")
    return value


def _number(row: dict[str, Any], field: str) -> float:
    raw = _required_text(row, field)
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"NWDP field {field!r} is not numeric: {raw!r}") from exc
    if not (-100_000 < value < 100_000):
        raise ValueError(f"NWDP field {field!r} is outside a defensible numeric range")
    return value


def _station_identity(name: str, longitude: float, latitude: float) -> tuple[str, str]:
    basis = f"{name.casefold().strip()}|{longitude:.6f}|{latitude:.6f}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:34] or "station"
    return f"nwdp-{slug}-{digest}", f"derived:{digest}"


def _observation_identity(station_id: str, source_observed_at: str) -> str:
    basis = f"{station_id}|{source_observed_at}"
    return f"nwdp-rwl-{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:20]}"


def _source_version(resource_last_modified: datetime | None) -> str:
    if resource_last_modified is None:
        return f"nwdp-resource-{NWDP_RESOURCE_ID}"
    return f"nwdp-{NWDP_RESOURCE_ID[:8]}@{resource_last_modified.isoformat()}"


def normalize_nwdp_payload(
    payload: dict[str, Any],
    *,
    fetched_at: datetime,
    resource_last_modified: datetime | None = None,
) -> NWDPBatch:
    """Validate and normalize one CKAN datastore response."""

    if payload.get("success") is not True:
        raise ValueError("NWDP CKAN response did not report success")
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("records"), list):
        raise ValueError("NWDP CKAN response has no result.records list")
    if result.get("resource_id") != NWDP_RESOURCE_ID:
        raise ValueError("NWDP CKAN response came from an unexpected resource")

    stations: dict[str, NWDPStation] = {}
    observations: dict[str, NWDPObservation] = {}
    for raw_row in result["records"]:
        if not isinstance(raw_row, dict):
            raise ValueError("NWDP record is not an object")
        row = raw_row
        state_code = _required_text(row, "State LGD Code")
        if state_code != "18":
            raise ValueError(f"NWDP Assam resource returned state LGD code {state_code!r}")

        name = _required_text(row, "Station")
        latitude = _number(row, "Latitude")
        longitude = _number(row, "Longitude")
        if not (24 <= latitude <= 29 and 89 <= longitude <= 97):
            raise ValueError(f"NWDP station {name!r} is outside the Assam validation envelope")

        station_id, derived_source_id = _station_identity(name, longitude, latitude)
        station = NWDPStation(
            id=station_id,
            source_record_id=derived_source_id,
            name=name,
            longitude=longitude,
            latitude=latitude,
            district_name=_present_text(row.get("District")),
            district_lgd_code=_present_text(row.get("District LGD Code")),
            river_name=_present_text(row.get("River")),
            basin_name=_present_text(row.get("Basin")),
            metadata={
                "identity_basis": "derived_from_station_name_and_coordinates",
                "agency": _present_text(row.get("Agency")),
                "discharge_available": _present_text(row.get("Is_DischargeDataAvailable")),
                "raw_zero_gauge": _present_text(row.get("RL_of_zeroGauge")),
                "raw_mean_sea_level": _present_text(row.get("MeanSeaLevel")),
            },
        )
        existing_station = stations.get(station_id)
        if existing_station is not None and existing_station != station:
            raise ValueError(f"NWDP station identity collision for {name!r}")
        stations[station_id] = station

        source_observed_at = _required_text(row, SOURCE_TIME_FIELD)
        try:
            source_observed_at_local = datetime.strptime(source_observed_at, "%d-%m-%Y %H:%M")
        except ValueError as exc:
            raise ValueError(
                f"NWDP observation timestamp has an unexpected format: {source_observed_at!r}"
            ) from exc
        water_level_m = _number(row, WATER_LEVEL_FIELD)
        observation_id = _observation_identity(station_id, source_observed_at)
        observation = NWDPObservation(
            id=observation_id,
            station_id=station_id,
            source_record_id=observation_id,
            source_observed_at=source_observed_at,
            source_observed_at_local=source_observed_at_local,
            water_level_m=water_level_m,
            metadata={
                "ckan_row_id": row.get("_id"),
                "source_serial_number": _present_text(row.get("SlNo")),
                "time_interpretation": "source_local_time_timezone_unverified",
            },
        )
        existing_observation = observations.get(observation_id)
        if existing_observation is not None and existing_observation != observation:
            raise ValueError(f"Conflicting duplicate NWDP observation {observation_id}")
        observations[observation_id] = observation

    canonical_payload = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    source_total = result.get("total")
    if not isinstance(source_total, int) or source_total < len(observations):
        source_total = len(observations)
    return NWDPBatch(
        resource_id=NWDP_RESOURCE_ID,
        source_version=_source_version(resource_last_modified),
        fetched_at=fetched_at,
        raw_sha256=hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest(),
        source_total=source_total,
        stations=tuple(sorted(stations.values(), key=lambda item: item.id)),
        observations=tuple(
            sorted(observations.values(), key=lambda item: item.source_observed_at_local)
        ),
    )
