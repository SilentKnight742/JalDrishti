"""Conservative, explainable state rules for FloodEvent creation.

The initial operational policy intentionally uses only the severity published
by IMD. Model rainfall is supporting evidence, and the incomplete pilot river
feed cannot drive a transition while thresholds and timezone are unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FloodEventState(StrEnum):
    """Lifecycle states exposed by the event API."""

    WATCH = "watch"
    WARNING = "warning"
    SEVERE = "severe"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class EventRulePolicy:
    """Versioned mapping from official warning colour to event state."""

    version: str
    warning_state_map: dict[str, FloodEventState | None]
    recovery_grace_hours: int
    severe_requires_satellite_inundation: bool

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> EventRulePolicy:
        version = str(payload.get("version", "")).strip()
        if not version:
            raise ValueError("Event rule policy requires a version")
        raw_mapping = payload.get("official_warning_state")
        if not isinstance(raw_mapping, dict):
            raise ValueError("official_warning_state must be an object")

        expected = {"green", "yellow", "orange", "red"}
        if set(raw_mapping) != expected:
            raise ValueError("official_warning_state must define green, yellow, orange and red")
        state_mapping: dict[str, FloodEventState | None] = {}
        for severity, raw_state in raw_mapping.items():
            state_mapping[severity] = (
                None if raw_state is None else FloodEventState(str(raw_state).lower())
            )

        recovery_grace_hours = int(payload.get("recovery_grace_hours", 24))
        if recovery_grace_hours < 1:
            raise ValueError("recovery_grace_hours must be at least one")
        severe_requires_satellite = bool(payload.get("severe_requires_satellite_inundation", True))
        if state_mapping["red"] == FloodEventState.SEVERE and severe_requires_satellite:
            raise ValueError(
                "Official warning colour cannot directly produce severe when satellite "
                "inundation is required"
            )
        return cls(
            version=version,
            warning_state_map=state_mapping,
            recovery_grace_hours=recovery_grace_hours,
            severe_requires_satellite_inundation=severe_requires_satellite,
        )


@dataclass(frozen=True, slots=True)
class EventRuleDecision:
    """Auditable output of one event-policy evaluation."""

    state: FloodEventState | None
    trigger_summary: str
    rationale: tuple[str, ...]
    rule_id: str


def evaluate_official_warning(
    *,
    severity: str,
    hazards: list[str] | tuple[str, ...],
    policy: EventRulePolicy,
) -> EventRuleDecision:
    """Map an official warning to a state without inventing numeric risk."""

    normalized = severity.strip().lower()
    if normalized not in policy.warning_state_map:
        raise ValueError(f"Unsupported official warning severity: {severity!r}")
    state = policy.warning_state_map[normalized]
    hazard_text = ", ".join(item for item in hazards if item) or "no hazard published"
    if state is None:
        return EventRuleDecision(
            state=None,
            trigger_summary="IMD currently publishes green/no-warning status.",
            rationale=(
                "No active event state is derived from an official green warning record.",
                "Model rainfall remains supporting guidance only.",
            ),
            rule_id=f"{policy.version}:official-warning-green",
        )

    return EventRuleDecision(
        state=state,
        trigger_summary=(f"IMD {normalized} district warning: {hazard_text}."),
        rationale=(
            f"Official IMD severity {normalized} maps to JalDrishti {state.value}.",
            "Rainfall model guidance does not independently raise the event state.",
            "Pilot river telemetry is excluded because thresholds and timezone are unpublished.",
            "Severe requires satellite-observed inundation plus supporting exposure evidence.",
        ),
        rule_id=f"{policy.version}:official-warning-{normalized}",
    )
