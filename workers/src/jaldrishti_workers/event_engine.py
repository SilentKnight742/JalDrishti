"""Scheduled transparent FloodEvent evaluation for the Assam adapter."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jaldrishti.domain.provenance import ProvenanceQuality
from jaldrishti.events.rules import (
    EventRulePolicy,
    FloodEventState,
    evaluate_official_warning,
)
from jaldrishti.persistence.models import (
    District,
    EventEvidence,
    EventTimelineEntry,
    FloodEvent,
    FloodEventDistrict,
    OfficialWarning,
    Station,
    WeatherForecast,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from jaldrishti_workers.celery_app import celery_app

DEFAULT_DATABASE_URL = "postgresql+asyncpg://jaldrishti:jaldrishti@postgres:5432/jaldrishti"
DEFAULT_POLICY_PATH = "/srv/jaldrishti/configs/event_rules.json"
EVENT_ENGINE_SOURCE = "JalDrishti transparent rule engine"


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"


def _load_policy() -> EventRulePolicy:
    path = Path(os.getenv("JALDRISHTI_EVENT_RULES_PATH", DEFAULT_POLICY_PATH))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Event rule policy must be a JSON object")
    return EventRulePolicy.from_mapping(payload)


def _latest_by_district(rows: list[Any]) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for row in rows:
        latest.setdefault(row.district_id, row)
    return latest


async def _upsert_evidence(
    session: AsyncSession,
    *,
    event: FloodEvent,
    evidence_id: str,
    evidence_type: str,
    title: str,
    summary: str,
    source: str,
    source_record_id: str,
    observed_at: datetime | None,
    published_at: datetime | None,
    ingested_at: datetime,
    source_url: str | None,
    source_version: str | None,
    quality: ProvenanceQuality | str,
    geometry: Any,
    metadata: dict[str, Any],
) -> EventEvidence:
    evidence = await session.get(EventEvidence, evidence_id)
    if evidence is None:
        evidence = EventEvidence(id=evidence_id, event_id=event.id)
        session.add(evidence)
    evidence.evidence_type = evidence_type
    evidence.title = title
    evidence.summary = summary
    evidence.source = source
    evidence.source_record_id = source_record_id
    evidence.observed_at = observed_at
    evidence.published_at = published_at
    evidence.ingested_at = ingested_at
    evidence.last_checked_at = ingested_at
    evidence.source_url = source_url
    evidence.source_version = source_version
    evidence.quality = quality
    evidence.geometry = geometry
    evidence.metadata_ = metadata
    return evidence


async def _add_timeline_once(
    session: AsyncSession,
    *,
    event_id: str,
    evidence_id: str | None,
    occurred_at: datetime,
    category: str,
    summary: str,
    state_from: str | None = None,
    state_to: str | None = None,
    discriminator: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    entry_id = _stable_id("timeline", event_id, category, discriminator)
    if await session.get(EventTimelineEntry, entry_id) is not None:
        return
    session.add(
        EventTimelineEntry(
            id=entry_id,
            event_id=event_id,
            evidence_id=evidence_id,
            occurred_at=occurred_at,
            category=category,
            state_from=state_from,
            state_to=state_to,
            summary=summary,
            metadata_=metadata or {},
        )
    )


async def _evaluate_assam_events(*, evaluated_at: datetime) -> dict[str, Any]:
    policy = _load_policy()
    engine = create_async_engine(
        os.getenv("JALDRISHTI_DATABASE_URL", DEFAULT_DATABASE_URL),
        pool_pre_ping=True,
    )
    counters = {
        "created": 0,
        "updated": 0,
        "transitioned": 0,
        "recovering": 0,
        "closed": 0,
        "active": 0,
    }
    try:
        async with (
            AsyncSession(engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "jaldrishti:event-engine:assam"},
            )
            warning_rows = list(
                (
                    await session.scalars(
                        select(OfficialWarning)
                        .where(
                            OfficialWarning.region_id == "assam",
                            OfficialWarning.day_index == 1,
                        )
                        .order_by(
                            OfficialWarning.district_id,
                            OfficialWarning.issue_at.desc(),
                            OfficialWarning.ingested_at.desc(),
                        )
                    )
                ).all()
            )
            warnings = _latest_by_district(warning_rows)
            districts = {
                row.id: row
                for row in (
                    await session.scalars(select(District).where(District.region_id == "assam"))
                ).all()
            }
            open_events = {
                row.primary_district_id: row
                for row in (
                    await session.scalars(
                        select(FloodEvent).where(
                            FloodEvent.region_id == "assam",
                            FloodEvent.ended_at.is_(None),
                        )
                    )
                ).all()
                if row.primary_district_id is not None
            }
            starts_at = evaluated_at.replace(minute=0, second=0, microsecond=0)
            forecast_rows = list(
                (
                    await session.scalars(
                        select(WeatherForecast)
                        .where(
                            WeatherForecast.region_id == "assam",
                            WeatherForecast.valid_at >= starts_at,
                            WeatherForecast.valid_at < starts_at + timedelta(hours=24),
                        )
                        .order_by(
                            WeatherForecast.district_id,
                            WeatherForecast.valid_at,
                        )
                    )
                ).all()
            )
            forecasts: dict[str, list[WeatherForecast]] = {}
            for forecast in forecast_rows:
                forecasts.setdefault(forecast.district_id, []).append(forecast)
            station_districts = set(
                (
                    await session.scalars(
                        select(Station.district_id).where(
                            Station.region_id == "assam",
                            Station.district_id.is_not(None),
                        )
                    )
                ).all()
            )

            for district_id, warning in warnings.items():
                district = districts.get(district_id)
                if district is None:
                    continue
                decision = evaluate_official_warning(
                    severity=warning.severity,
                    hazards=warning.hazards,
                    policy=policy,
                )
                event = open_events.get(district_id)

                if decision.state is None:
                    if event is None:
                        continue
                    warning_evidence_id = _stable_id(
                        "evidence", event.id, "official_warning", warning.id
                    )
                    await _upsert_evidence(
                        session,
                        event=event,
                        evidence_id=warning_evidence_id,
                        evidence_type="official_warning",
                        title=f"IMD green status for {district.name}",
                        summary=decision.trigger_summary,
                        source=warning.source,
                        source_record_id=warning.source_record_id or warning.id,
                        observed_at=warning.issue_at,
                        published_at=warning.published_at,
                        ingested_at=warning.ingested_at,
                        source_url=warning.source_url,
                        source_version=warning.source_version,
                        quality=warning.quality,
                        geometry=district.geometry,
                        metadata={
                            "severity": warning.severity,
                            "valid_date": warning.valid_date.isoformat(),
                            "rule_id": decision.rule_id,
                        },
                    )
                    if event.state != FloodEventState.RECOVERY.value:
                        previous_state = event.state
                        event.state = FloodEventState.RECOVERY.value
                        event.state_changed_at = evaluated_at
                        event.warning_status = "green"
                        event.last_updated_at = evaluated_at
                        event.trigger_summary = decision.trigger_summary
                        counters["recovering"] += 1
                        counters["transitioned"] += 1
                        await _add_timeline_once(
                            session,
                            event_id=event.id,
                            evidence_id=warning_evidence_id,
                            occurred_at=evaluated_at,
                            category="state_transition",
                            summary="Official warning returned to green; recovery monitoring began.",
                            state_from=previous_state,
                            state_to=FloodEventState.RECOVERY.value,
                            discriminator=f"recovery:{warning.id}",
                        )
                    elif evaluated_at - event.state_changed_at >= timedelta(
                        hours=policy.recovery_grace_hours
                    ):
                        event.ended_at = evaluated_at
                        event.last_updated_at = evaluated_at
                        counters["closed"] += 1
                        await _add_timeline_once(
                            session,
                            event_id=event.id,
                            evidence_id=warning_evidence_id,
                            occurred_at=evaluated_at,
                            category="event_closed",
                            summary=(
                                "Recovery grace period completed with an official green status."
                            ),
                            state_from=FloodEventState.RECOVERY.value,
                            discriminator=f"closed:{warning.id}",
                        )
                    continue

                is_new = event is None
                if is_new:
                    event = FloodEvent(
                        id=_stable_id(
                            "event",
                            "assam",
                            district_id,
                            warning.valid_date.isoformat(),
                        ),
                        region_id="assam",
                        primary_district_id=district_id,
                        name=f"{district.name} flood {decision.state.value}",
                        geometry=district.geometry,
                        started_at=warning.issue_at,
                        last_updated_at=evaluated_at,
                        state_changed_at=evaluated_at,
                        ended_at=None,
                        state=decision.state.value,
                        trigger_summary=decision.trigger_summary,
                        rainfall_status=(
                            "model_guidance_available"
                            if district_id in forecasts
                            else "not_available"
                        ),
                        river_status=(
                            "pilot_unverified"
                            if district_id in station_districts
                            else "not_available"
                        ),
                        warning_status=warning.severity,
                        satellite_status="not_requested",
                        created_by="auto",
                        rule_version=policy.version,
                        metadata_={
                            "rationale": list(decision.rationale),
                            "rule_id": decision.rule_id,
                        },
                    )
                    session.add(event)
                    session.add(
                        FloodEventDistrict(
                            event_id=event.id,
                            district_id=district_id,
                            role="primary",
                        )
                    )
                    open_events[district_id] = event
                    counters["created"] += 1
                else:
                    previous_state = event.state
                    event.name = f"{district.name} flood {decision.state.value}"
                    event.geometry = district.geometry
                    event.last_updated_at = evaluated_at
                    event.trigger_summary = decision.trigger_summary
                    event.rainfall_status = (
                        "model_guidance_available" if district_id in forecasts else "not_available"
                    )
                    event.river_status = (
                        "pilot_unverified" if district_id in station_districts else "not_available"
                    )
                    event.warning_status = warning.severity
                    event.rule_version = policy.version
                    event.metadata_ = {
                        "rationale": list(decision.rationale),
                        "rule_id": decision.rule_id,
                    }
                    if previous_state != decision.state.value:
                        event.state = decision.state.value
                        event.state_changed_at = evaluated_at
                        counters["transitioned"] += 1
                        await _add_timeline_once(
                            session,
                            event_id=event.id,
                            evidence_id=None,
                            occurred_at=evaluated_at,
                            category="state_transition",
                            summary=decision.trigger_summary,
                            state_from=previous_state,
                            state_to=decision.state.value,
                            discriminator=f"{warning.id}:{decision.state.value}",
                            metadata={"rule_id": decision.rule_id},
                        )
                    counters["updated"] += 1

                warning_evidence_id = _stable_id(
                    "evidence", event.id, "official_warning", warning.id
                )
                await _upsert_evidence(
                    session,
                    event=event,
                    evidence_id=warning_evidence_id,
                    evidence_type="official_warning",
                    title=f"IMD {warning.severity} warning for {district.name}",
                    summary=decision.trigger_summary,
                    source=warning.source,
                    source_record_id=warning.source_record_id or warning.id,
                    observed_at=warning.issue_at,
                    published_at=warning.published_at,
                    ingested_at=warning.ingested_at,
                    source_url=warning.source_url,
                    source_version=warning.source_version,
                    quality=warning.quality,
                    geometry=district.geometry,
                    metadata={
                        "severity": warning.severity,
                        "hazards": list(warning.hazards),
                        "valid_date": warning.valid_date.isoformat(),
                        "rule_id": decision.rule_id,
                    },
                )
                if is_new:
                    await _add_timeline_once(
                        session,
                        event_id=event.id,
                        evidence_id=warning_evidence_id,
                        occurred_at=warning.issue_at,
                        category="event_created",
                        summary=decision.trigger_summary,
                        state_to=decision.state.value,
                        discriminator=warning.id,
                        metadata={"rule_id": decision.rule_id},
                    )

                district_forecasts = forecasts.get(district_id, [])
                if district_forecasts:
                    rainfall_mm = round(
                        sum(item.precipitation_mm for item in district_forecasts), 2
                    )
                    probabilities = [
                        item.precipitation_probability_pct
                        for item in district_forecasts
                        if item.precipitation_probability_pct is not None
                    ]
                    latest = max(
                        district_forecasts,
                        key=lambda item: item.ingested_at,
                    )
                    forecast_key = (
                        f"{district_id}:{min(item.valid_at for item in district_forecasts).isoformat()}"
                        f":{max(item.valid_at for item in district_forecasts).isoformat()}"
                    )
                    await _upsert_evidence(
                        session,
                        event=event,
                        evidence_id=_stable_id(
                            "evidence", event.id, "rainfall_forecast", forecast_key
                        ),
                        evidence_type="rainfall_forecast",
                        title=f"24-hour rainfall guidance for {district.name}",
                        summary=(
                            f"{rainfall_mm:.1f} mm model-derived precipitation; "
                            f"maximum hourly probability "
                            f"{max(probabilities):.0f}%."
                            if probabilities
                            else (
                                f"{rainfall_mm:.1f} mm model-derived precipitation; "
                                "probability not available."
                            )
                        ),
                        source=latest.source,
                        source_record_id=forecast_key,
                        observed_at=None,
                        published_at=None,
                        ingested_at=latest.ingested_at,
                        source_url=latest.source_url,
                        source_version=latest.source_version,
                        quality=ProvenanceQuality.MODEL_DERIVED,
                        geometry=latest.geometry,
                        metadata={
                            "precipitation_24h_mm": rainfall_mm,
                            "maximum_probability_pct": (
                                max(probabilities) if probabilities else None
                            ),
                            "role": "supporting_only",
                        },
                    )
                counters["active"] += 1
        return {**counters, "policy_version": policy.version}
    finally:
        await engine.dispose()


@celery_app.task(name="jaldrishti.events.evaluate_assam")
def evaluate_assam_events() -> dict[str, Any]:
    """Evaluate the latest complete official-warning snapshot for Assam."""

    return asyncio.run(_evaluate_assam_events(evaluated_at=datetime.now(UTC)))
