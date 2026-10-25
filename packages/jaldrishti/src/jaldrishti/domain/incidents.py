"""Privacy-safe public records and write inputs for community incident reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jaldrishti.domain.geography import GeoJSONMapping
from jaldrishti.domain.provenance import ProvenanceQuality


@dataclass(frozen=True, slots=True)
class IncidentMediaInput:
    id: str
    private_uri: str
    mime_type: str
    size_bytes: int
    sha256: str
    normalization_status: str


@dataclass(frozen=True, slots=True)
class IncidentCreateInput:
    id: str
    submission_id: str
    public_reference: str
    request_fingerprint: str
    event_id: str | None
    incident_type: str
    people_affected: int | None
    people_count_approximate: bool
    description_private: str
    public_summary: str
    reported_at: datetime
    location_method: str
    location_accuracy_m: float | None
    exact_longitude: float
    exact_latitude: float
    public_longitude: float
    public_latitude: float
    privacy_consent_at: datetime
    encrypted_contact: bytes | None
    encryption_key_id: str | None
    media: IncidentMediaInput | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class IncidentReportRecord:
    id: str
    submission_id: str
    public_reference: str
    request_fingerprint: str
    event_id: str | None
    incident_type: str
    people_affected: int | None
    people_count_approximate: bool
    public_summary: str
    reported_at: datetime
    verification_state: str
    status: str
    location_method: str
    location_accuracy_m: float | None
    public_geometry: GeoJSONMapping
    media_count: int
    source: str
    source_record_id: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    ingested_at: datetime
    metadata: dict[str, Any]
