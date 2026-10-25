"""Strict normalisation for IMD's public district-warning WFS layer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

IMD_WARNING_WFS_URL = "https://reactjs.imd.gov.in/geoserver/wfs"
IMD_WARNING_PAGE_URL = "https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php"
IMD_WARNING_SOURCE = "India Meteorological Department district warnings"
IMD_DISTRICT_MAPPING_VERSION = "assam-35-2026-09-24"

# IMD Obj_id -> (LGD district code, current Survey of India district name).
# Names intentionally bridge source variants such as MORIGAON/MARIGAON,
# SIBSAGAR/SIVASAGAR, KARIMGANJ/SRIBHUMI, and KARBI ANALOG/KARBI ANGLONG.
IMD_ASSAM_DISTRICTS: dict[int, tuple[str, str]] = {
    814: ("771", "Bajali"),
    21: ("324", "Baksa"),
    27: ("303", "Barpeta"),
    630: ("734", "Biswanath"),
    26: ("319", "Bongaigaon"),
    360: ("316", "Cachar"),
    621: ("704", "Charaideo"),
    18: ("320", "Chirang"),
    16: ("325", "Darrang"),
    623: ("308", "Dhemaji"),
    9: ("301", "Dhubri"),
    475: ("310", "Dibrugarh"),
    393: ("315", "Dima Hasao"),
    12: ("302", "Goalpara"),
    446: ("313", "Golaghat"),
    337: ("318", "Hailakandi"),
    632: ("720", "Hojai"),
    456: ("312", "Jorhat"),
    15: ("321", "Kamrup"),
    10: ("322", "Kamrup Metropolitan"),
    8: ("314", "Karbi Anglong"),
    17: ("300", "Kokrajhar"),
    487: ("307", "Lakhimpur"),
    631: ("707", "Majuli"),
    14: ("304", "Marigaon"),
    19: ("305", "Nagaon"),
    13: ("323", "Nalbari"),
    462: ("311", "Sivasagar"),
    23: ("306", "Sonitpur"),
    633: ("664", "South Salmara-Mankachar"),
    340: ("317", "Sribhumi"),
    815: ("766", "Tamulpur"),
    494: ("309", "Tinsukia"),
    22: ("326", "Udalguri"),
    635: ("752", "West Karbi Anglong"),
}

WARNING_HAZARDS = {
    1: "No warning",
    2: "Heavy rain",
    3: "Heavy snow",
    4: "Thunderstorm, lightning or squall",
    5: "Hailstorm",
    6: "Dust storm",
    7: "Dust-raising winds",
    8: "Strong surface winds",
    9: "Heat wave",
    10: "Hot day",
    11: "Warm night",
    12: "Cold wave",
    13: "Cold day",
    14: "Ground frost",
    15: "Fog",
    16: "Very heavy rain",
    17: "Extremely heavy rain",
}

# IMD documentation: 1 red, 2 orange, 3 yellow, 4 green.
COLOR_SEVERITY = {1: "red", 2: "orange", 3: "yellow", 4: "green"}


@dataclass(frozen=True, slots=True)
class IMDWarning:
    id: str
    district_id: str
    district_name: str
    external_id: str
    source_district_name: str
    issue_at: datetime
    valid_date: date
    day_index: int
    severity: str
    color_code: int
    warning_codes: tuple[int, ...]
    hazards: tuple[str, ...]
    description: str | None
    source_record_id: str
    updated_at: datetime
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class IMDWarningBatch:
    warnings: tuple[IMDWarning, ...]
    fetched_at: datetime
    source_version: str
    raw_sha256: str
    mapped_districts: int
    expected_districts: int = 35


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _parse_utc(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty timestamp")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _warning_codes(value: Any, *, field: str) -> tuple[int, ...]:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a comma-separated string")
    try:
        codes = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError(f"{field} contains a non-numeric warning code") from exc
    if not codes or any(code not in WARNING_HAZARDS for code in codes):
        raise ValueError(f"{field} contains an unsupported warning code")
    return codes


def normalize_imd_warning_payload(
    payload: dict[str, Any], *, fetched_at: datetime
) -> IMDWarningBatch:
    """Normalise the Assam subset of a WFS GeoJSON FeatureCollection."""

    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("IMD WFS response must be a GeoJSON FeatureCollection")
    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware")

    raw_sha256 = _canonical_hash(payload)
    warnings: list[IMDWarning] = []
    mapped_ids: set[int] = set()
    latest_update: datetime | None = None

    for feature in payload["features"]:
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            continue
        properties = feature["properties"]
        obj_id = properties.get("Obj_id")
        if not isinstance(obj_id, int) or obj_id not in IMD_ASSAM_DISTRICTS:
            continue
        if obj_id in mapped_ids:
            raise ValueError(f"IMD response contains duplicate Assam Obj_id {obj_id}")
        mapped_ids.add(obj_id)

        lgd_code, district_name = IMD_ASSAM_DISTRICTS[obj_id]
        source_name = str(properties.get("District") or "").strip()
        if not source_name:
            raise ValueError(f"IMD district {obj_id} has no name")
        raw_date = properties.get("Date")
        if not isinstance(raw_date, str):
            raise ValueError(f"IMD district {obj_id} has no issue date")
        issue_date = date.fromisoformat(raw_date)
        utc_hour = properties.get("UTC")
        if not isinstance(utc_hour, int) or not 0 <= utc_hour <= 23:
            raise ValueError(f"IMD district {obj_id} has invalid UTC issue hour")
        issue_at = datetime.combine(issue_date, datetime.min.time(), tzinfo=UTC).replace(
            hour=utc_hour
        )
        updated_at = _parse_utc(properties.get("updated_at"), field="updated_at")
        latest_update = max(latest_update, updated_at) if latest_update else updated_at

        for day_index in range(1, 6):
            codes = _warning_codes(properties.get(f"Day_{day_index}"), field=f"Day_{day_index}")
            color = properties.get(f"Day{day_index}_Color")
            if not isinstance(color, int) or color not in COLOR_SEVERITY:
                raise ValueError(f"IMD district {obj_id} has invalid day {day_index} color")
            valid_date = issue_date + timedelta(days=day_index - 1)
            description_value = properties.get(f"Day{day_index}_text")
            description = (
                description_value.strip()
                if isinstance(description_value, str) and description_value.strip()
                else None
            )
            hazards = tuple(WARNING_HAZARDS[code] for code in codes if code != 1)
            external_id = str(obj_id)
            source_record_id = f"{external_id}/{valid_date.isoformat()}"
            warnings.append(
                IMDWarning(
                    id=f"imd-warning-{obj_id}-{valid_date.isoformat()}",
                    district_id=f"assam-district-{lgd_code}",
                    district_name=district_name,
                    external_id=external_id,
                    source_district_name=source_name,
                    issue_at=issue_at,
                    valid_date=valid_date,
                    day_index=day_index,
                    severity=COLOR_SEVERITY[color],
                    color_code=color,
                    warning_codes=codes,
                    hazards=hazards,
                    description=description,
                    source_record_id=source_record_id,
                    updated_at=updated_at,
                    metadata={
                        "mapping_version": IMD_DISTRICT_MAPPING_VERSION,
                        "raw_sha256": raw_sha256,
                        "source_feature_id": feature.get("id"),
                    },
                )
            )

    if not warnings:
        raise ValueError("IMD WFS response contains no mapped Assam warnings")
    version_time = latest_update.isoformat() if latest_update else fetched_at.isoformat()
    return IMDWarningBatch(
        warnings=tuple(warnings),
        fetched_at=fetched_at.astimezone(UTC),
        source_version=f"imd-wfs@{version_time}",
        raw_sha256=raw_sha256,
        mapped_districts=len(mapped_ids),
    )
