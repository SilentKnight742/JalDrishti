"""Celery task for event-scoped OPERA Sentinel-1 RTC processing."""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from geoalchemy2.shape import from_shape, to_shape
from jaldrishti.domain.provenance import ProvenanceQuality
from jaldrishti.impact.snapshot import PointAsset, summarise_point_exposure
from jaldrishti.persistence.models import (
    AccessibilitySnapshot,
    EventEvidence,
    EventTimelineEntry,
    Facility,
    FloodEvent,
    FloodExtent,
    ImpactSnapshot,
    PotentialExposure,
    RoadDisruption,
    RoadSegment,
    SatelliteJob,
    SatelliteScene,
    Settlement,
    SettlementAccessibility,
)
from jaldrishti.provenance.artifacts import atomic_write_json, file_record
from jaldrishti.routing import RoadLine, SettlementPoint, analyse_accessibility
from jaldrishti.satellite.catalog import (
    CATALOG_SOURCE,
    SarAsset,
    SarScene,
    SarScenePair,
    search_opera_s1,
    select_scene_pairs,
)
from jaldrishti.satellite.processing import (
    NoChangeEvidence,
    SarRasterSet,
    process_opera_rtc_change,
)
from pyproj import Transformer
from shapely.ops import transform
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from jaldrishti_workers.celery_app import celery_app

DEFAULT_DATABASE_URL = "postgresql+asyncpg://jaldrishti:jaldrishti@postgres:5432/jaldrishti"
DEFAULT_PRODUCTS_DIR = "/var/lib/jaldrishti/products"
ALGORITHM_VERSION = "0.1.0"
IMPACT_ALGORITHM = "jaldrishti-point-intersection-exposure"
ACCESSIBILITY_ALGORITHM = "jaldrishti-road-reachability-screening"
EARTHDATA_MESSAGE = (
    "Matching OPERA scenes were found, but NASA Earthdata download credentials are not "
    "configured. Set EARTHDATA_TOKEN or EARTHDATA_USERNAME/EARTHDATA_PASSWORD and accept "
    "the ASF End-User License Agreement."
)


def _stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("\x1f".join(str(item) for item in parts).encode()).hexdigest()[:32]
    return f"{prefix}-{digest}"


def _credentials_configured() -> bool:
    if os.getenv("EARTHDATA_TOKEN"):
        return True
    if os.getenv("EARTHDATA_USERNAME") and os.getenv("EARTHDATA_PASSWORD"):
        return True
    netrc_path = Path(os.getenv("NETRC", "/srv/jaldrishti/.netrc"))
    return netrc_path.is_file()


def _earthdata_session() -> requests.Session:
    try:
        import earthaccess

        strategy = (
            "environment"
            if os.getenv("EARTHDATA_TOKEN")
            or (os.getenv("EARTHDATA_USERNAME") and os.getenv("EARTHDATA_PASSWORD"))
            else "netrc"
        )
        auth = earthaccess.login(strategy=strategy)
        if not getattr(auth, "authenticated", False):
            raise RuntimeError("Earthdata authentication was not accepted")
        return earthaccess.get_requests_https_session()
    except Exception as exc:
        raise RuntimeError(EARTHDATA_MESSAGE) from exc


def _download_asset(
    session: requests.Session,
    asset: SarAsset,
    target: Path,
) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and (
        asset.expected_bytes is None or target.stat().st_size == asset.expected_bytes
    ):
        return dict(file_record(target, target.parents[2]))
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with session.get(asset.url, stream=True, timeout=(30, 300)) as response:
            if response.status_code in {401, 403}:
                raise RuntimeError(EARTHDATA_MESSAGE)
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        if asset.expected_bytes is not None and temporary.stat().st_size != asset.expected_bytes:
            raise RuntimeError(
                f"download size mismatch for {asset.name}: expected "
                f"{asset.expected_bytes}, got {temporary.stat().st_size}"
            )
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return dict(file_record(target, target.parents[2]))


def _asset_payload(scene: SarScene) -> dict[str, Any]:
    return {
        key: {
            "name": asset.name,
            "url": asset.url,
            "expected_bytes": asset.expected_bytes,
        }
        for key, asset in scene.assets.items()
    }


async def _record_selected_scenes(
    session: AsyncSession,
    *,
    job: SatelliteJob,
    pairs: list[SarScenePair],
) -> None:
    selected: dict[tuple[str, str], SarScene] = {}
    for pair in pairs:
        selected[("before", pair.before.product_id)] = pair.before
        selected[("after", pair.after.product_id)] = pair.after
    for (role, product_id), scene in selected.items():
        scene_id = _stable_id("scene", job.id, role, product_id)
        row = await session.get(SatelliteScene, scene_id)
        if row is None:
            row = SatelliteScene(id=scene_id, job_id=job.id, event_id=job.event_id)
            session.add(row)
        row.role = role
        row.product_id = product_id
        row.acquired_at = scene.acquired_at
        row.stopped_at = scene.stopped_at
        row.platform = scene.platform
        row.sensor = scene.sensor
        row.relative_orbit = scene.relative_orbit
        row.flight_direction = scene.flight_direction
        row.burst_id = scene.burst_id
        row.polarizations = list(scene.polarizations)
        row.product_version = scene.product_version
        row.geometry = from_shape(scene.footprint, srid=4326)
        row.assets = _asset_payload(scene)
        row.source = CATALOG_SOURCE
        row.source_url = job.catalog_url
        row.catalog_record = dict(scene.raw_properties)


async def _add_timeline(
    session: AsyncSession,
    *,
    event_id: str,
    category: str,
    summary: str,
    discriminator: str,
    evidence_id: str | None = None,
) -> None:
    entry_id = _stable_id("timeline", event_id, category, discriminator)
    if await session.get(EventTimelineEntry, entry_id) is not None:
        return
    session.add(
        EventTimelineEntry(
            id=entry_id,
            event_id=event_id,
            evidence_id=evidence_id,
            occurred_at=datetime.now(UTC),
            category=category,
            summary=summary,
            metadata_={},
        )
    )


async def _record_impact_snapshot(
    session: AsyncSession,
    *,
    event: FloodEvent,
    extent: FloodExtent,
) -> ImpactSnapshot:
    """Persist explicitly partial potential exposure for one observed extent."""

    settlements = (
        await session.scalars(
            select(Settlement)
            .where(func.ST_Intersects(Settlement.geometry, extent.geometry))
            .order_by(Settlement.id)
        )
    ).all()
    facilities = (
        await session.scalars(
            select(Facility)
            .where(func.ST_Intersects(Facility.geometry, extent.geometry))
            .order_by(Facility.id)
        )
    ).all()
    totals = summarise_point_exposure(
        [
            PointAsset(
                asset_type="settlement",
                asset_id=item.id,
                name=item.name,
                population=item.population,
            )
            for item in settlements
        ]
        + [
            PointAsset(asset_type="facility", asset_id=item.id, name=item.name)
            for item in facilities
        ]
    )
    now = datetime.now(UTC)
    snapshot_id = _stable_id("impact", event.id, extent.id, IMPACT_ALGORITHM, ALGORITHM_VERSION)
    snapshot = await session.get(ImpactSnapshot, snapshot_id)
    if snapshot is None:
        snapshot = ImpactSnapshot(
            id=snapshot_id,
            event_id=event.id,
            flood_extent_id=extent.id,
        )
        session.add(snapshot)
    snapshot.calculated_at = now
    snapshot.algorithm = IMPACT_ALGORITHM
    snapshot.algorithm_version = ALGORITHM_VERSION
    snapshot.inundated_area_km2 = extent.area_km2
    snapshot.settlement_count = totals.settlement_count
    snapshot.facility_count = totals.facility_count
    snapshot.population_potentially_exposed = totals.population_potentially_exposed
    snapshot.population_record_count = totals.population_record_count
    snapshot.road_overlap_km = None
    snapshot.building_count = None
    snapshot.coverage = totals.coverage
    snapshot.metadata_ = {
        "terminology": "Potential exposure; not confirmed damage, closure, or displacement.",
        "facility_categories": dict(Counter(item.category for item in facilities)),
        "flood_extent_quality": str(extent.quality),
    }
    await session.flush()
    await session.execute(
        delete(PotentialExposure).where(PotentialExposure.snapshot_id == snapshot_id)
    )
    for asset_type, assets in (("settlement", settlements), ("facility", facilities)):
        for asset in assets:
            metadata: dict[str, Any] = {
                "asset_source": asset.source,
                "asset_source_record_id": asset.source_record_id,
                "asset_source_url": asset.source_url,
                "asset_source_version": asset.source_version,
                "asset_quality": str(asset.quality),
                "interpretation": "Geometry intersects satellite-observed change evidence.",
            }
            if asset_type == "settlement":
                metadata.update(
                    {
                        "settlement_type": asset.settlement_type,
                        "population": asset.population,
                    }
                )
            else:
                metadata.update({"category": asset.category, "subcategory": asset.subcategory})
            session.add(
                PotentialExposure(
                    id=_stable_id("exposure", snapshot_id, asset_type, asset.id),
                    snapshot_id=snapshot_id,
                    event_id=event.id,
                    flood_extent_id=extent.id,
                    asset_type=asset_type,
                    asset_id=asset.id,
                    name=asset.name,
                    metric_type="intersects",
                    metric_value=1.0,
                    unit="boolean",
                    geometry=asset.geometry,
                    metadata_=metadata,
                    source="JalDrishti impact engine",
                    source_record_id=asset.id,
                    observed_at=extent.observed_at,
                    published_at=None,
                    ingested_at=now,
                    last_checked_at=now,
                    source_url=None,
                    source_version=ALGORITHM_VERSION,
                    quality=ProvenanceQuality.MODEL_DERIVED,
                )
            )

    evidence_id = _stable_id("evidence", event.id, "potential_exposure", snapshot_id)
    evidence = await session.get(EventEvidence, evidence_id)
    if evidence is None:
        evidence = EventEvidence(id=evidence_id, event_id=event.id)
        session.add(evidence)
    population_text = (
        f"{totals.population_potentially_exposed:,} people from "
        f"{totals.population_record_count} population-bearing settlement record(s)"
        if totals.population_potentially_exposed is not None
        else "population unavailable from intersecting settlement records"
    )
    evidence.evidence_type = "potential_exposure"
    evidence.title = "Model-derived potential exposure"
    evidence.summary = (
        f"{totals.settlement_count} settlement point(s) and "
        f"{totals.facility_count} selected facility record(s) intersect the satellite "
        f"change extent; {population_text}. Roads and buildings are not configured."
    )
    evidence.geometry = extent.geometry
    evidence.source = "JalDrishti impact engine"
    evidence.source_record_id = snapshot_id
    evidence.observed_at = extent.observed_at
    evidence.published_at = None
    evidence.ingested_at = now
    evidence.last_checked_at = now
    evidence.source_url = None
    evidence.source_version = ALGORITHM_VERSION
    evidence.quality = ProvenanceQuality.MODEL_DERIVED
    evidence.metadata_ = {
        "snapshot_id": snapshot_id,
        "flood_extent_id": extent.id,
        "coverage": totals.coverage,
    }
    await _add_timeline(
        session,
        event_id=event.id,
        evidence_id=evidence_id,
        category="impact_snapshot",
        summary=evidence.summary,
        discriminator=snapshot_id,
    )
    return snapshot


async def _record_accessibility_snapshot(
    session: AsyncSession,
    *,
    event: FloodEvent,
    extent: FloodExtent,
) -> AccessibilitySnapshot:
    """Compare routable reachability before/after potential road disruption."""

    roads = (
        await session.scalars(
            select(RoadSegment)
            .where(RoadSegment.region_id == event.region_id)
            .order_by(RoadSegment.id)
        )
    ).all()
    settlements = (
        await session.scalars(
            select(Settlement)
            .where(Settlement.region_id == event.region_id)
            .order_by(Settlement.id)
        )
    ).all()
    facilities = (
        await session.scalars(
            select(Facility).where(Facility.region_id == event.region_id).order_by(Facility.id)
        )
    ).all()
    flood_geometry = to_shape(extent.geometry)
    result = analyse_accessibility(
        [
            RoadLine(
                id=item.id,
                road_class=item.road_class,
                geometry=to_shape(item.geometry),
            )
            for item in roads
        ],
        flood_geometry,
        [
            SettlementPoint(id=item.id, name=item.name, geometry=to_shape(item.geometry))
            for item in settlements
        ],
        [
            to_shape(item.geometry)
            for item in facilities
            if item.category == "healthcare" and "hospital" in (item.subcategory or "").casefold()
        ],
    )
    now = datetime.now(UTC)
    snapshot_id = _stable_id(
        "access", event.id, extent.id, ACCESSIBILITY_ALGORITHM, ALGORITHM_VERSION
    )
    snapshot = await session.get(AccessibilitySnapshot, snapshot_id)
    if snapshot is None:
        snapshot = AccessibilitySnapshot(
            id=snapshot_id,
            event_id=event.id,
            flood_extent_id=extent.id,
        )
        session.add(snapshot)
    road_by_id = {item.id: item for item in roads}
    settlement_by_id = {item.id: item for item in settlements}
    to_metric = Transformer.from_crs("EPSG:4326", "EPSG:32646", always_xy=True).transform
    flood_metric = transform(to_metric, flood_geometry)
    road_overlaps: dict[str, float] = {}
    for road_id in result.potentially_affected_road_ids:
        road = road_by_id[road_id]
        overlap_km = transform(to_metric, to_shape(road.geometry)).intersection(flood_metric).length
        road_overlaps[road_id] = float(overlap_km / 1_000)
    total_overlap_km = sum(road_overlaps.values())
    hospital_count = sum(
        item.category == "healthcare" and "hospital" in (item.subcategory or "").casefold()
        for item in facilities
    )
    status = "available" if roads else "not_configured"
    snapshot.calculated_at = now
    snapshot.algorithm = ACCESSIBILITY_ALGORITHM
    snapshot.algorithm_version = ALGORITHM_VERSION
    snapshot.status = status
    snapshot.road_count = result.road_count
    snapshot.graph_node_count = result.graph_node_count
    snapshot.graph_edge_count = result.graph_edge_count
    snapshot.potentially_affected_road_count = len(result.potentially_affected_road_ids)
    snapshot.potentially_affected_road_km = total_overlap_km
    snapshot.assessed_settlement_count = result.assessed_settlement_count
    snapshot.potentially_isolated_settlement_count = result.potentially_isolated_settlement_count
    snapshot.coverage = {
        "roads": {
            "status": "partial" if roads else "not_configured",
            "records": len(roads),
            "basis": "OSM routable backbone; residential/service/track/foot ways excluded",
        },
        "settlements": {
            "status": "partial",
            "records": len(settlements),
            "assessed": result.assessed_settlement_count,
        },
        "hospital_destinations": {
            "status": "partial" if hospital_count else "not_available",
            "records": hospital_count,
            "basis": "Selected OSM healthcare records tagged as hospitals",
        },
    }
    snapshot.metadata_ = {
        "terminology": (
            "Potential access disruption based on intersection with satellite change evidence; "
            "not a confirmed closure or safe-route instruction."
        ),
        "maximum_snap_distance_m": 5_000,
    }
    await session.flush()
    await session.execute(delete(RoadDisruption).where(RoadDisruption.snapshot_id == snapshot_id))
    await session.execute(
        delete(SettlementAccessibility).where(SettlementAccessibility.snapshot_id == snapshot_id)
    )
    for road_id in result.potentially_affected_road_ids:
        road = road_by_id[road_id]
        session.add(
            RoadDisruption(
                id=_stable_id("disruption", snapshot_id, road.id),
                snapshot_id=snapshot_id,
                event_id=event.id,
                flood_extent_id=extent.id,
                road_segment_id=road.id,
                name=road.name,
                road_class=road.road_class,
                overlap_km=road_overlaps[road.id],
                geometry=road.geometry,
                metadata_={
                    "road_source": road.source,
                    "road_source_record_id": road.source_record_id,
                    "road_source_url": road.source_url,
                    "road_source_version": road.source_version,
                    "interpretation": "Potentially affected; not a confirmed road closure.",
                },
                source="JalDrishti accessibility engine",
                source_record_id=road.id,
                observed_at=extent.observed_at,
                published_at=None,
                ingested_at=now,
                last_checked_at=now,
                source_url=None,
                source_version=ALGORITHM_VERSION,
                quality=ProvenanceQuality.MODEL_DERIVED,
            )
        )
    for item in result.settlements:
        settlement = settlement_by_id[item.settlement_id]
        session.add(
            SettlementAccessibility(
                id=_stable_id("reachability", snapshot_id, item.settlement_id),
                snapshot_id=snapshot_id,
                event_id=event.id,
                flood_extent_id=extent.id,
                settlement_id=settlement.id,
                name=item.name,
                snapped_distance_m=item.snapped_distance_m,
                major_road_reachable_before=item.major_road_reachable_before,
                major_road_reachable_after=item.major_road_reachable_after,
                hospital_reachable_before=item.hospital_reachable_before,
                hospital_reachable_after=item.hospital_reachable_after,
                nearest_major_road_km=item.nearest_major_road_km,
                nearest_hospital_km=item.nearest_hospital_km,
                potentially_isolated=item.potentially_isolated,
                assessment_status=item.assessment_status,
                geometry=settlement.geometry,
                metadata_={
                    "settlement_source": settlement.source,
                    "settlement_source_record_id": settlement.source_record_id,
                    "interpretation": "Modelled network reachability, not field verification.",
                },
                source="JalDrishti accessibility engine",
                source_record_id=settlement.id,
                observed_at=extent.observed_at,
                published_at=None,
                ingested_at=now,
                last_checked_at=now,
                source_url=None,
                source_version=ALGORITHM_VERSION,
                quality=ProvenanceQuality.MODEL_DERIVED,
            )
        )

    evidence_id = _stable_id("evidence", event.id, "road_accessibility", snapshot_id)
    evidence = await session.get(EventEvidence, evidence_id)
    if evidence is None:
        evidence = EventEvidence(id=evidence_id, event_id=event.id)
        session.add(evidence)
    evidence.evidence_type = "potential_access_disruption"
    evidence.title = "Model-derived road accessibility screening"
    evidence.summary = (
        f"{len(result.potentially_affected_road_ids)} road segment(s) with "
        f"{total_overlap_km:.2f} km overlap; "
        f"{result.potentially_isolated_settlement_count} settlement(s) potentially isolated."
    )
    evidence.geometry = extent.geometry
    evidence.source = "JalDrishti accessibility engine"
    evidence.source_record_id = snapshot_id
    evidence.observed_at = extent.observed_at
    evidence.published_at = None
    evidence.ingested_at = now
    evidence.last_checked_at = now
    evidence.source_url = None
    evidence.source_version = ALGORITHM_VERSION
    evidence.quality = ProvenanceQuality.MODEL_DERIVED
    evidence.metadata_ = {"snapshot_id": snapshot_id, "coverage": snapshot.coverage}
    await _add_timeline(
        session,
        event_id=event.id,
        evidence_id=evidence_id,
        category="accessibility_snapshot",
        summary=evidence.summary,
        discriminator=snapshot_id,
    )
    return snapshot


async def _set_terminal_status(
    job_id: str,
    *,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    satellite_status: str | None = None,
) -> dict[str, Any]:
    engine = create_async_engine(
        os.getenv("JALDRISHTI_DATABASE_URL", DEFAULT_DATABASE_URL),
        pool_pre_ping=True,
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
            job = await session.get(SatelliteJob, job_id)
            if job is None:
                return {"job_id": job_id, "status": "not_found"}
            job.status = status
            job.completed_at = datetime.now(UTC)
            job.error_code = error_code
            job.error_message = error_message
            event = await session.get(FloodEvent, job.event_id)
            if event is not None and satellite_status is not None:
                event.satellite_status = satellite_status
                event.last_updated_at = datetime.now(UTC)
            await _add_timeline(
                session,
                event_id=job.event_id,
                category="satellite_job",
                summary=error_message or f"Satellite job finished with status {status}.",
                discriminator=f"{job.id}:{status}",
            )
        return {"job_id": job_id, "status": status, "error_code": error_code}
    finally:
        await engine.dispose()


async def _process_satellite_job(job_id: str) -> dict[str, Any]:
    engine = create_async_engine(
        os.getenv("JALDRISHTI_DATABASE_URL", DEFAULT_DATABASE_URL),
        pool_pre_ping=True,
    )
    products_root = Path(os.getenv("JALDRISHTI_PRODUCTS_DIR", DEFAULT_PRODUCTS_DIR))
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": f"jaldrishti:satellite:{job_id}"},
                )
                job = await session.get(SatelliteJob, job_id)
                if job is None:
                    return {"job_id": job_id, "status": "not_found"}
                if job.status in {"completed", "completed_no_extent"}:
                    return {"job_id": job_id, "status": job.status, "idempotent": True}
                event = await session.get(FloodEvent, job.event_id)
                if event is None:
                    raise RuntimeError(f"event {job.event_id} no longer exists")
                job.status = "searching"
                job.started_at = job.started_at or datetime.now(UTC)
                job.completed_at = None
                job.error_code = None
                job.error_message = None
                event.satellite_status = "searching"
                event.last_updated_at = datetime.now(UTC)

            event_geometry = to_shape(event.geometry)
            scenes, raw_catalog, catalog_url = search_opera_s1(
                geometry_wkt=event_geometry.wkt,
                starts_at=job.before_start,
                ends_at=job.after_end,
            )
            pairs = select_scene_pairs(
                scenes,
                before_start=job.before_start,
                before_end=job.before_end,
                after_start=job.after_start,
                after_end=job.after_end,
            )
            job_dir = products_root / job.id
            catalog_path = atomic_write_json(job_dir / "catalog.json", raw_catalog)

            async with session.begin():
                job.catalog_url = catalog_url
                job.metadata_ = {
                    "catalog_record": dict(file_record(catalog_path, products_root)),
                    "candidate_scene_count": len(scenes),
                    "matched_pair_count": len(pairs),
                }
                await _record_selected_scenes(session, job=job, pairs=pairs)
                if not pairs:
                    job.status = "no_scenes"
                    job.completed_at = datetime.now(UTC)
                    job.error_code = "no_compatible_scene_pair"
                    job.error_message = (
                        "No compatible same-burst before/after OPERA-S1 pair was available "
                        "inside the requested windows."
                    )
                    event.satellite_status = "no_compatible_scene_pair"
                    event.last_updated_at = datetime.now(UTC)
                    await _add_timeline(
                        session,
                        event_id=event.id,
                        category="satellite_job",
                        summary=job.error_message,
                        discriminator=f"{job.id}:no_scenes",
                    )
                    return {"job_id": job.id, "status": job.status, "scenes": len(scenes)}
                if not _credentials_configured():
                    job.status = "awaiting_credentials"
                    job.completed_at = datetime.now(UTC)
                    job.error_code = "earthdata_credentials_required"
                    job.error_message = EARTHDATA_MESSAGE
                    event.satellite_status = "awaiting_credentials"
                    event.last_updated_at = datetime.now(UTC)
                    await _add_timeline(
                        session,
                        event_id=event.id,
                        category="satellite_job",
                        summary=EARTHDATA_MESSAGE,
                        discriminator=f"{job.id}:awaiting_credentials",
                    )
                    return {
                        "job_id": job.id,
                        "status": job.status,
                        "matched_pairs": len(pairs),
                    }
                job.status = "downloading"
                event.satellite_status = "downloading"

            earthdata = _earthdata_session()
            downloaded: dict[tuple[str, str], SarRasterSet] = {}
            asset_records: dict[str, dict[str, Any]] = {}
            for pair in pairs:
                for role, scene in (("before", pair.before), ("after", pair.after)):
                    key = (role, scene.product_id)
                    if key in downloaded:
                        continue
                    scene_dir = job_dir / "source" / scene.product_id
                    local: dict[str, Path] = {}
                    for asset_key in ("vv", "vh", "mask"):
                        asset = scene.assets[asset_key]
                        target = scene_dir / asset.name
                        asset_records[f"{role}:{scene.product_id}:{asset_key}"] = _download_asset(
                            earthdata,
                            asset,
                            target,
                        )
                        local[asset_key] = target
                    downloaded[key] = SarRasterSet(
                        product_id=scene.product_id,
                        vv=local["vv"],
                        vh=local["vh"],
                        mask=local["mask"],
                    )

            async with session.begin():
                job.status = "processing"
                job.metadata_ = {**job.metadata_, "downloaded_assets": asset_records}
                event.satellite_status = "processing"
                event.last_updated_at = datetime.now(UTC)

            parameters = dict(job.parameters)
            product = process_opera_rtc_change(
                before=[downloaded[("before", pair.before.product_id)] for pair in pairs],
                after=[downloaded[("after", pair.after.product_id)] for pair in pairs],
                geometry_wgs84=event_geometry,
                output_path=job_dir / "evidence.tif",
                resolution_m=float(parameters["resolution_m"]),
                median_kernel=int(parameters["median_kernel"]),
                minimum_valid_coverage=float(parameters["minimum_valid_coverage"]),
                water_threshold_override_db=parameters.get("water_threshold_override_db"),
                vv_drop_db=float(parameters["vv_drop_db"]),
                vh_drop_db=float(parameters["vh_drop_db"]),
                min_component_pixels=int(parameters["min_component_pixels"]),
            )

            acquired_at = max(pair.after.acquired_at for pair in pairs)
            extent_id = _stable_id("extent", job.event_id, job.id)
            evidence_id = _stable_id("evidence", job.event_id, "satellite_extent", extent_id)
            source_product_ids = sorted({pair.after.product_id for pair in pairs})
            async with session.begin():
                extent = await session.get(FloodExtent, extent_id)
                if extent is None:
                    extent = FloodExtent(id=extent_id, event_id=job.event_id, job_id=job.id)
                    session.add(extent)
                extent.acquired_at = acquired_at
                extent.algorithm = job.algorithm
                extent.algorithm_version = ALGORITHM_VERSION
                extent.parameters = product.parameters
                extent.area_km2 = product.area_km2
                extent.high_evidence_area_km2 = product.high_evidence_area_km2
                extent.valid_coverage_fraction = product.valid_coverage_fraction
                extent.resolution_m = product.resolution_m
                extent.analysis_crs = product.analysis_crs
                extent.raster_uri = f"artifact://satellite/{job.id}/evidence.tif"
                extent.geometry = from_shape(product.geometry_wgs84, srid=4326)
                extent.source = "NASA/JPL OPERA RTC-S1 via ASF DAAC"
                extent.source_record_id = ",".join(source_product_ids)
                extent.observed_at = acquired_at
                extent.published_at = None
                extent.ingested_at = datetime.now(UTC)
                extent.last_checked_at = datetime.now(UTC)
                extent.source_url = catalog_url
                extent.source_version = ",".join(
                    sorted({pair.after.product_version for pair in pairs})
                )
                extent.quality = ProvenanceQuality.SATELLITE_OBSERVED
                extent.metadata_ = {
                    "raster": product.raster_record,
                    "source_product_ids": source_product_ids,
                    "caveat": product.parameters["terminology"],
                }
                await session.flush()
                impact = await _record_impact_snapshot(
                    session,
                    event=event,
                    extent=extent,
                )
                accessibility = await _record_accessibility_snapshot(
                    session,
                    event=event,
                    extent=extent,
                )
                if accessibility.status == "available":
                    impact.road_overlap_km = accessibility.potentially_affected_road_km
                    impact.coverage = {
                        **impact.coverage,
                        "roads": accessibility.coverage["roads"],
                    }
                evidence = await session.get(EventEvidence, evidence_id)
                if evidence is None:
                    evidence = EventEvidence(
                        id=evidence_id,
                        event_id=job.event_id,
                    )
                    session.add(evidence)
                evidence.evidence_type = "satellite_flood_extent"
                evidence.title = "OPERA Sentinel-1 change extent"
                evidence.summary = (
                    f"{product.area_km2:.2f} km² of satellite-observed change evidence; "
                    "not field-confirmed inundation or damage."
                )
                evidence.geometry = extent.geometry
                evidence.source = extent.source
                evidence.source_record_id = extent_id
                evidence.observed_at = acquired_at
                evidence.published_at = None
                evidence.ingested_at = extent.ingested_at
                evidence.last_checked_at = extent.last_checked_at
                evidence.source_url = catalog_url
                evidence.source_version = extent.source_version
                evidence.quality = ProvenanceQuality.SATELLITE_OBSERVED
                evidence.metadata_ = {
                    "area_km2": product.area_km2,
                    "high_evidence_area_km2": product.high_evidence_area_km2,
                    "job_id": job.id,
                    "algorithm": job.algorithm,
                }
                job.status = "completed"
                job.completed_at = datetime.now(UTC)
                job.error_code = None
                job.error_message = None
                event.satellite_status = "observed_extent_available"
                event.last_updated_at = datetime.now(UTC)
                await _add_timeline(
                    session,
                    event_id=event.id,
                    evidence_id=evidence_id,
                    category="satellite_observation",
                    summary=evidence.summary,
                    discriminator=extent_id,
                )
            return {
                "job_id": job.id,
                "status": job.status,
                "matched_pairs": len(pairs),
                "extent_id": extent_id,
                "area_km2": product.area_km2,
                "impact_snapshot_id": impact.id,
                "accessibility_snapshot_id": accessibility.id,
            }
    except NoChangeEvidence as exc:
        return await _set_terminal_status(
            job_id,
            status="completed_no_extent",
            error_code="no_change_evidence",
            error_message=str(exc),
            satellite_status="observed_no_change_evidence",
        )
    except Exception as exc:
        return await _set_terminal_status(
            job_id,
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc),
            satellite_status="processing_failed",
        )
    finally:
        await engine.dispose()


@celery_app.task(name="jaldrishti.satellite.process_event")
def process_event_satellite(job_id: str) -> dict[str, Any]:
    """Discover, acquire, and process matched OPERA RTC scenes for one event."""

    return asyncio.run(_process_satellite_job(job_id))
