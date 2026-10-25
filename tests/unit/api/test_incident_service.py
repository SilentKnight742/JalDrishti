from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from jaldrishti.domain.events import FloodEventRecord
from jaldrishti.domain.incidents import (
    IncidentCreateInput,
    IncidentMediaInput,
    IncidentReportRecord,
)
from jaldrishti_api.config import Settings
from jaldrishti_api.dependencies import get_incident_service
from jaldrishti_api.incident_security import (
    FernetContactCipher,
    InvalidIncidentImage,
    normalize_incident_image,
)
from jaldrishti_api.main import create_app
from jaldrishti_api.schemas import IncidentReceipt, IncidentSubmissionRequest
from jaldrishti_api.services import (
    IncidentOutsideCoverage,
    IncidentService,
    IncidentSubmissionConflict,
)
from PIL import Image

NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)
SUBMISSION_ID = UUID("86882750-67a3-4f95-87cf-59c5b00cdb40")


class Events:
    async def get(self, event_id: str):
        if event_id != "event-darrang":
            return None
        return FloodEventRecord(
            id=event_id,
            region_id="assam",
            primary_district_id="darrang",
            name="Darrang flood watch",
            geometry={"type": "MultiPolygon", "coordinates": []},
            started_at=NOW,
            last_updated_at=NOW,
            state_changed_at=NOW,
            ended_at=None,
            state="watch",
            trigger_summary="Test",
            rainfall_status="supporting",
            river_status="not_available",
            warning_status="yellow",
            satellite_status="not_available",
            created_by="auto",
            rule_version="test-v1",
            rationale=[],
        )


def _record(value: IncidentCreateInput) -> IncidentReportRecord:
    return IncidentReportRecord(
        id=value.id,
        submission_id=value.submission_id,
        public_reference=value.public_reference,
        request_fingerprint=value.request_fingerprint,
        event_id=value.event_id,
        incident_type=value.incident_type,
        people_affected=value.people_affected,
        people_count_approximate=value.people_count_approximate,
        public_summary=value.public_summary,
        reported_at=value.reported_at,
        verification_state="unverified",
        status="received",
        location_method=value.location_method,
        location_accuracy_m=value.location_accuracy_m,
        public_geometry={
            "type": "Point",
            "coordinates": [value.public_longitude, value.public_latitude],
        },
        media_count=1 if value.media else 0,
        source="JalDrishti public incident report",
        source_record_id=value.public_reference,
        source_version="0.1.0",
        quality="unverified_report",
        ingested_at=value.reported_at,
        metadata=value.metadata,
    )


class Incidents:
    def __init__(self, *, in_region: bool = True) -> None:
        self.in_region = in_region
        self.values: dict[str, tuple[IncidentCreateInput, IncidentReportRecord]] = {}

    async def get_by_submission_id(self, submission_id: str):
        found = self.values.get(submission_id)
        return None if found is None else found[1]

    async def find_matching_open_event(self, longitude: float, latitude: float):
        return "event-darrang"

    async def point_in_region(self, longitude: float, latitude: float, *, region_id: str):
        return self.in_region and region_id == "assam"

    async def create(self, value: IncidentCreateInput):
        existing = self.values.get(value.submission_id)
        if existing is not None:
            return existing[1], False
        record = _record(value)
        self.values[value.submission_id] = (value, record)
        return record, True

    async def list_public(self, event_id: str):
        return [record for _, record in self.values.values() if record.event_id == event_id]


class Limiter:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls = 0

    async def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        self.calls += 1
        return self.allowed


class Cipher:
    key_id = "test-key"

    def encrypt(self, value: str) -> bytes:
        return f"encrypted:{value}".encode()


class MediaStore:
    def __init__(self) -> None:
        self.stored: list[IncidentMediaInput] = []
        self.discarded: list[IncidentMediaInput] = []

    def store(self, *, report_id: str, media_id: str, content: bytes):
        media = IncidentMediaInput(
            id=media_id,
            private_uri=f"/private/{report_id}/{media_id}.jpg",
            mime_type="image/jpeg",
            size_bytes=len(content),
            sha256="a" * 64,
            normalization_status="content_normalized_metadata_removed",
        )
        self.stored.append(media)
        return media

    def discard(self, media: IncidentMediaInput) -> None:
        self.discarded.append(media)


def _submission(**changes: Any) -> IncidentSubmissionRequest:
    values: dict[str, Any] = {
        "submission_id": SUBMISSION_ID,
        "incident_type": "stranded_people",
        "people_affected": 4,
        "people_count_approximate": True,
        "description": "Four people are waiting on a raised platform near the road.",
        "latitude": 26.50831,
        "longitude": 92.11638,
        "location_accuracy_m": 18,
        "location_method": "gps",
        "contact": "+91 90000 00000",
        "privacy_consent": True,
    }
    values.update(changes)
    return IncidentSubmissionRequest(**values)


@pytest.mark.asyncio
async def test_multipart_route_parses_browser_consent_and_rejects_false() -> None:
    class RouteService:
        received: IncidentSubmissionRequest | None = None

        async def submit(
            self,
            request: IncidentSubmissionRequest,
            *,
            client_key: str,
            photo: bytes | None,
        ) -> IncidentReceipt:
            self.received = request
            assert client_key
            assert photo is None
            return IncidentReceipt(
                public_reference="JD-ROUTE-TEST",
                event_id="event-darrang",
                status="received",
                verification_state="unverified",
                reported_at=NOW,
                public_location_precision="approximately 1 km; exact location withheld",
                duplicate=False,
                message="Report received for review.",
            )

    service = RouteService()
    application = create_app(Settings(cors_origins=[]))

    async def override() -> RouteService:
        return service

    application.dependency_overrides[get_incident_service] = override
    form = {
        "submission_id": str(SUBMISSION_ID),
        "incident_type": "road_flooded",
        "description": "Road water observed during browser form validation.",
        "latitude": "26.50831",
        "longitude": "92.11638",
        "location_method": "map",
        "privacy_consent": "true",
    }
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://testserver",
    ) as client:
        accepted = await client.post("/api/v1/incidents/report", data=form)
        rejected = await client.post(
            "/api/v1/incidents/report",
            data={**form, "privacy_consent": "false"},
        )

    assert accepted.status_code == 201
    assert service.received is not None
    assert service.received.privacy_consent is True
    assert rejected.status_code == 422
    assert rejected.json() == {"detail": "Privacy consent is required"}


@pytest.mark.asyncio
async def test_submission_separates_private_and_public_fields():
    incidents = Incidents()
    limiter = Limiter()
    service = IncidentService(
        events=Events(),
        incidents=incidents,
        limiter=limiter,
        cipher=Cipher(),
        media_store=MediaStore(),
        rate_limit_per_hour=10,
    )

    receipt = await service.submit(_submission(), client_key="127.0.0.1", photo=b"jpeg")
    stored, _ = incidents.values[str(SUBMISSION_ID)]
    public = await service.list_event_incidents("event-darrang")

    assert receipt.verification_state == "unverified"
    assert receipt.public_location_precision.startswith("approximately 1 km")
    assert stored.description_private.startswith("Four people")
    assert stored.encrypted_contact == b"encrypted:+91 90000 00000"
    assert stored.exact_longitude == 92.11638
    assert stored.public_longitude == 92.12
    assert public is not None
    payload = public.model_dump(mode="json")
    assert payload["features"][0]["geometry"]["coordinates"] == [92.12, 26.51]
    assert "Four people are waiting" not in str(payload)
    assert "+91" not in str(payload)
    assert limiter.calls == 1


@pytest.mark.asyncio
async def test_retry_is_idempotent_and_changed_reuse_conflicts():
    incidents = Incidents()
    limiter = Limiter()
    service = IncidentService(
        events=Events(),
        incidents=incidents,
        limiter=limiter,
        cipher=Cipher(),
        media_store=MediaStore(),
        rate_limit_per_hour=10,
    )
    first = await service.submit(_submission(), client_key="one", photo=None)
    retry = await service.submit(_submission(), client_key="one", photo=None)

    assert first.duplicate is False
    assert retry.duplicate is True
    assert limiter.calls == 1
    with pytest.raises(IncidentSubmissionConflict):
        await service.submit(
            _submission(description="Different incident details"),
            client_key="one",
            photo=None,
        )


@pytest.mark.asyncio
async def test_concurrent_losing_upload_cannot_delete_winning_media() -> None:
    class ConcurrentIncidents(Incidents):
        async def get_by_submission_id(self, submission_id: str):
            return None

        async def create(self, value: IncidentCreateInput):
            return _record(value), False

    media_store = MediaStore()
    service = IncidentService(
        events=Events(),
        incidents=ConcurrentIncidents(),
        limiter=Limiter(),
        cipher=Cipher(),
        media_store=media_store,
        rate_limit_per_hour=10,
    )

    await service.submit(_submission(), client_key="one", photo=b"same-photo")
    await service.submit(_submission(), client_key="one", photo=b"same-photo")

    assert len(media_store.stored) == 2
    assert media_store.stored[0].private_uri != media_store.stored[1].private_uri
    assert media_store.discarded == media_store.stored


@pytest.mark.asyncio
async def test_location_must_be_inside_official_assam_geometry():
    service = IncidentService(
        events=Events(),
        incidents=Incidents(in_region=False),
        limiter=Limiter(),
        cipher=Cipher(),
        media_store=MediaStore(),
        rate_limit_per_hour=10,
    )
    with pytest.raises(IncidentOutsideCoverage):
        await service.submit(_submission(), client_key="one", photo=None)


def test_image_normalization_reencodes_and_removes_metadata():
    source = Image.new("RGB", (32, 24), "red")
    exif = Image.Exif()
    exif[0x010E] = "private description"
    raw = io.BytesIO()
    source.save(raw, format="JPEG", exif=exif)

    normalized = normalize_incident_image(raw.getvalue(), maximum_bytes=100_000)
    with Image.open(io.BytesIO(normalized.content)) as result:
        assert result.format == "JPEG"
        assert len(result.getexif()) == 0


def test_contact_cipher_does_not_emit_plaintext():
    cipher = FernetContactCipher("AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=", "test")
    encrypted = cipher.encrypt("test@example.com")

    assert b"test@example.com" not in encrypted


def test_invalid_image_is_rejected():
    with pytest.raises(InvalidIncidentImage):
        normalize_incident_image(b"not-an-image", maximum_bytes=100_000)


def test_production_refuses_the_development_contact_key():
    with pytest.raises(ValueError, match="replace the development"):
        Settings(environment="production")
