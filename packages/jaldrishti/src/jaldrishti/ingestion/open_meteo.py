"""Normalisation for explicitly model-derived Open-Meteo rainfall guidance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_SOURCE = "Open-Meteo / ECMWF IFS 0.25° model guidance"
OPEN_METEO_MODEL = "ecmwf_ifs025"


@dataclass(frozen=True, slots=True)
class DistrictForecastLocation:
    district_id: str
    district_name: str
    longitude: float
    latitude: float


@dataclass(frozen=True, slots=True)
class RainfallForecast:
    id: str
    district_id: str
    district_name: str
    longitude: float
    latitude: float
    model: str
    valid_at: datetime
    lead_hours: int
    precipitation_mm: float
    precipitation_probability_pct: float | None
    source_record_id: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RainfallForecastBatch:
    forecasts: tuple[RainfallForecast, ...]
    fetched_at: datetime
    source_version: str
    raw_sha256: str


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _number(value: Any, *, field: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    parsed = float(value)
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return parsed


def normalize_open_meteo_payload(
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    locations: list[DistrictForecastLocation],
    fetched_at: datetime,
    model: str = OPEN_METEO_MODEL,
) -> RainfallForecastBatch:
    """Validate a UTC, multi-location hourly forecast response."""

    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware")
    responses = payload if isinstance(payload, list) else [payload]
    if len(responses) != len(locations):
        raise ValueError("Open-Meteo response count does not match requested locations")

    raw_sha256 = _canonical_hash(payload)
    fetched_utc = fetched_at.astimezone(UTC)
    forecasts: list[RainfallForecast] = []
    for location, response in zip(locations, responses, strict=True):
        if not isinstance(response, dict):
            raise ValueError("Open-Meteo location response must be an object")
        if response.get("utc_offset_seconds") != 0:
            raise ValueError("Open-Meteo response must use UTC")
        hourly = response.get("hourly")
        if not isinstance(hourly, dict):
            raise ValueError("Open-Meteo response has no hourly object")
        times = hourly.get("time")
        precipitation = hourly.get("precipitation")
        probability = hourly.get("precipitation_probability")
        if not isinstance(times, list) or not isinstance(precipitation, list):
            raise ValueError("Open-Meteo hourly time and precipitation must be arrays")
        if len(times) != len(precipitation):
            raise ValueError("Open-Meteo hourly arrays have different lengths")
        if probability is not None and (
            not isinstance(probability, list) or len(probability) != len(times)
        ):
            raise ValueError("Open-Meteo probability array has a different length")

        source_grid_latitude = _number(response.get("latitude"), field="latitude")
        source_grid_longitude = _number(response.get("longitude"), field="longitude")
        for index, (raw_time, raw_precipitation) in enumerate(
            zip(times, precipitation, strict=True)
        ):
            if not isinstance(raw_time, str):
                raise ValueError("Open-Meteo forecast time must be a string")
            valid_at = datetime.fromisoformat(raw_time).replace(tzinfo=UTC)
            precipitation_mm = _number(raw_precipitation, field="precipitation", minimum=0)
            probability_value = None
            if probability is not None and probability[index] is not None:
                probability_value = _number(
                    probability[index], field="precipitation_probability", minimum=0
                )
                if probability_value > 100:
                    raise ValueError("precipitation_probability cannot exceed 100")
            source_record_id = f"{location.district_id}/{model}/{valid_at.isoformat()}"
            forecasts.append(
                RainfallForecast(
                    id="weather-" + hashlib.sha256(source_record_id.encode()).hexdigest()[:32],
                    district_id=location.district_id,
                    district_name=location.district_name,
                    longitude=location.longitude,
                    latitude=location.latitude,
                    model=model,
                    valid_at=valid_at,
                    lead_hours=max(0, round((valid_at - fetched_utc).total_seconds() / 3600)),
                    precipitation_mm=precipitation_mm,
                    precipitation_probability_pct=probability_value,
                    source_record_id=source_record_id,
                    metadata={
                        "raw_sha256": raw_sha256,
                        "source_grid_latitude": source_grid_latitude,
                        "source_grid_longitude": source_grid_longitude,
                        "elevation_m": response.get("elevation"),
                    },
                )
            )

    if not forecasts:
        raise ValueError("Open-Meteo response contains no forecasts")
    return RainfallForecastBatch(
        forecasts=tuple(forecasts),
        fetched_at=fetched_utc,
        source_version=f"open-meteo-{model}@{fetched_utc.isoformat()}",
        raw_sha256=raw_sha256,
    )
