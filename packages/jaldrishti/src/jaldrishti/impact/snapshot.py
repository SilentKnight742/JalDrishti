"""Pure helpers for transparent potential-exposure summaries.

These functions deliberately distinguish unavailable data from a measured zero.
They do not infer damage, road closure, or population displacement.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PointAsset:
    """Minimal source record already found to intersect an observed extent."""

    asset_type: str
    asset_id: str
    name: str
    population: int | None = None


@dataclass(frozen=True, slots=True)
class ImpactTotals:
    settlement_count: int
    facility_count: int
    population_potentially_exposed: int | None
    population_record_count: int
    coverage: dict[str, dict[str, Any]]


def summarise_point_exposure(assets: Iterable[PointAsset]) -> ImpactTotals:
    """Summarise point intersections without overstating dataset completeness."""

    records = tuple(assets)
    settlements = tuple(item for item in records if item.asset_type == "settlement")
    facilities = tuple(item for item in records if item.asset_type == "facility")
    population_values = [
        item.population
        for item in settlements
        if item.population is not None and item.population >= 0
    ]
    population_total = sum(population_values) if population_values else None
    return ImpactTotals(
        settlement_count=len(settlements),
        facility_count=len(facilities),
        population_potentially_exposed=population_total,
        population_record_count=len(population_values),
        coverage={
            "settlements": {
                "status": "partial",
                "basis": "Named OSM city/town points intersecting the satellite extent",
                "records_evaluated": len(settlements),
            },
            "facilities": {
                "status": "partial",
                "basis": "Selected OSM hospitals, schools, police and fire records",
                "records_evaluated": len(facilities),
            },
            "population": {
                "status": "partial" if population_values else "not_available",
                "basis": (
                    "Population values attached to intersecting settlement points only"
                    if population_values
                    else "No population-bearing intersecting settlement records"
                ),
                "records_with_values": len(population_values),
                "intersecting_settlements": len(settlements),
            },
            "roads": {
                "status": "not_configured",
                "basis": "No canonical Assam road-network dataset is loaded",
            },
            "buildings": {
                "status": "not_configured",
                "basis": "No canonical Assam building-footprint dataset is loaded",
            },
        },
    )
