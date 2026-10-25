from datetime import UTC, datetime

import pytest
from jaldrishti.ingestion.imd import normalize_imd_warning_payload


def _feature(*, obj_id: int = 16, color: int = 3, codes: str = "2,4") -> dict:
    properties = {
        "Obj_id": obj_id,
        "Date": "2026-09-24",
        "UTC": 6,
        "District": "DARRANG",
        "updated_at": "2026-09-24T12:46:45Z",
    }
    for day in range(1, 6):
        properties[f"Day_{day}"] = codes if day == 1 else "1"
        properties[f"Day{day}_Color"] = color if day == 1 else 4
        properties[f"Day{day}_text"] = "Localized heavy rain" if day == 1 else None
    return {"type": "Feature", "id": "imd.16", "geometry": None, "properties": properties}


def test_normalizes_five_days_with_official_severity_and_lgd_mapping() -> None:
    batch = normalize_imd_warning_payload(
        {"type": "FeatureCollection", "features": [_feature()]},
        fetched_at=datetime(2026, 9, 24, 13, tzinfo=UTC),
    )

    assert len(batch.warnings) == 5
    assert batch.mapped_districts == 1
    first = batch.warnings[0]
    assert first.district_id == "assam-district-325"
    assert first.severity == "yellow"
    assert first.warning_codes == (2, 4)
    assert first.hazards == ("Heavy rain", "Thunderstorm, lightning or squall")
    assert first.issue_at.isoformat() == "2026-09-24T06:00:00+00:00"
    assert first.valid_date.isoformat() == "2026-09-24"
    assert batch.warnings[-1].valid_date.isoformat() == "2026-09-28"


@pytest.mark.parametrize(
    ("field", "value"),
    [("UTC", 29), ("Day_1", "unknown"), ("Day1_Color", 0)],
)
def test_rejects_invalid_source_fields(field: str, value: object) -> None:
    feature = _feature()
    feature["properties"][field] = value
    with pytest.raises(ValueError):
        normalize_imd_warning_payload(
            {"type": "FeatureCollection", "features": [feature]},
            fetched_at=datetime(2026, 9, 24, 13, tzinfo=UTC),
        )


def test_ignores_non_assam_features_but_rejects_empty_assam_result() -> None:
    with pytest.raises(ValueError, match="no mapped Assam"):
        normalize_imd_warning_payload(
            {"type": "FeatureCollection", "features": [_feature(obj_id=999)]},
            fetched_at=datetime(2026, 9, 24, 13, tzinfo=UTC),
        )
