"""Contract tests for the deliberately degraded NWDP Assam adapter."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from jaldrishti.ingestion.nwdp import (
    NWDP_RESOURCE_ID,
    PILOT_CAVEATS,
    normalize_nwdp_payload,
)

FETCHED_AT = datetime(2026, 9, 24, 5, 0, tzinfo=UTC)


def _row(*, row_id: int = 818, timestamp: str = "22-09-2026 23:00") -> dict[str, object]:
    return {
        "_id": row_id,
        "SlNo": str(row_id),
        "Station": "NH15 Crossing Fakirpara Tangni",
        "Agency": "Assam",
        "State LGD Code": "18",
        "State": "Assam",
        "District LGD Code": "283",
        "District": "DARRANG",
        "River": "-",
        "Basin": "-",
        "Latitude": "26.50833333",
        "Longitude": "92.11638889",
        "Is_DischargeDataAvailable": "No",
        "RL_of_zeroGauge": "0",
        "MeanSeaLevel": "0",
        "Data Acquisition Time": timestamp,
        "River Water Level Telemetry Hourly (meter)": "61.083",
    }


def _payload(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "success": True,
        "result": {
            "resource_id": NWDP_RESOURCE_ID,
            "total": len(rows),
            "records": list(rows),
        },
    }


def test_normalizes_station_and_preserves_unknown_operational_fields() -> None:
    batch = normalize_nwdp_payload(
        _payload(_row()),
        fetched_at=FETCHED_AT,
        resource_last_modified=datetime(2026, 9, 24, 0, 17, 59, tzinfo=UTC),
    )

    assert len(batch.stations) == 1
    station = batch.stations[0]
    assert station.id.startswith("nwdp-nh15-crossing-fakirpara-tangni-")
    assert station.source_record_id.startswith("derived:")
    assert station.district_lgd_code == "283"
    assert station.river_name is None
    assert station.basin_name is None
    assert "stable station identifier" in " ".join(PILOT_CAVEATS)
    assert batch.source_version.startswith("nwdp-847f5630@")
    assert len(batch.raw_sha256) == 64


def test_preserves_source_local_time_without_inventing_timezone() -> None:
    batch = normalize_nwdp_payload(_payload(_row()), fetched_at=FETCHED_AT)

    observation = batch.observations[0]
    assert observation.source_observed_at == "22-09-2026 23:00"
    assert observation.source_observed_at_local == datetime(2026, 9, 22, 23, 0)
    assert observation.source_observed_at_local.tzinfo is None
    assert observation.water_level_m == pytest.approx(61.083)
    assert observation.metadata["time_interpretation"] == ("source_local_time_timezone_unverified")


def test_identity_is_stable_when_ckan_row_numbers_change() -> None:
    first = normalize_nwdp_payload(_payload(_row(row_id=818)), fetched_at=FETCHED_AT)
    replacement = normalize_nwdp_payload(_payload(_row(row_id=5000)), fetched_at=FETCHED_AT)

    assert first.stations[0].id == replacement.stations[0].id
    assert first.observations[0].id == replacement.observations[0].id


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("State LGD Code", "17", "state LGD code"),
        ("Data Acquisition Time", "2026-09-22T23:00:00Z", "unexpected format"),
        ("Latitude", "not-a-number", "not numeric"),
    ],
)
def test_rejects_rows_that_violate_the_source_contract(
    field: str,
    value: str,
    message: str,
) -> None:
    row = deepcopy(_row())
    row[field] = value

    with pytest.raises(ValueError, match=message):
        normalize_nwdp_payload(_payload(row), fetched_at=FETCHED_AT)
