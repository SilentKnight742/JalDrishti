from datetime import UTC, datetime

import pytest
from jaldrishti.ingestion.open_meteo import (
    DistrictForecastLocation,
    normalize_open_meteo_payload,
)

LOCATION = DistrictForecastLocation(
    district_id="assam-district-325",
    district_name="Darrang",
    longitude=92.03,
    latitude=26.45,
)


def _payload() -> dict:
    return {
        "latitude": 26.5,
        "longitude": 92.0,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "elevation": 63.0,
        "hourly": {
            "time": ["2026-09-24T14:00", "2026-09-24T15:00"],
            "precipitation": [0.4, 1.2],
            "precipitation_probability": [45, 70],
        },
    }


def test_normalizes_model_guidance_without_calling_it_observed() -> None:
    batch = normalize_open_meteo_payload(
        _payload(),
        locations=[LOCATION],
        fetched_at=datetime(2026, 9, 24, 13, 30, tzinfo=UTC),
    )

    assert len(batch.forecasts) == 2
    first = batch.forecasts[0]
    assert first.district_id == LOCATION.district_id
    assert first.valid_at.isoformat() == "2026-09-24T14:00:00+00:00"
    assert first.lead_hours == 0
    assert first.precipitation_mm == 0.4
    assert first.precipitation_probability_pct == 45
    assert first.metadata["source_grid_longitude"] == 92.0


def test_rejects_location_count_mismatch() -> None:
    with pytest.raises(ValueError, match="count"):
        normalize_open_meteo_payload(
            [_payload(), _payload()],
            locations=[LOCATION],
            fetched_at=datetime(2026, 9, 24, 13, 30, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("precipitation", [-1, 0]), ("precipitation_probability", [101, 20])],
)
def test_rejects_invalid_hourly_values(field: str, value: list[int]) -> None:
    payload = _payload()
    payload["hourly"][field] = value
    with pytest.raises(ValueError):
        normalize_open_meteo_payload(
            payload,
            locations=[LOCATION],
            fetched_at=datetime(2026, 9, 24, 13, 30, tzinfo=UTC),
        )
