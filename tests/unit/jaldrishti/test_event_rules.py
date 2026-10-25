import pytest
from jaldrishti.events.rules import (
    EventRulePolicy,
    FloodEventState,
    evaluate_official_warning,
)


def policy() -> EventRulePolicy:
    return EventRulePolicy.from_mapping(
        {
            "version": "test-v1",
            "official_warning_state": {
                "green": None,
                "yellow": "watch",
                "orange": "warning",
                "red": "warning",
            },
            "recovery_grace_hours": 24,
            "severe_requires_satellite_inundation": True,
        }
    )


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("green", None),
        ("yellow", FloodEventState.WATCH),
        ("orange", FloodEventState.WARNING),
        ("red", FloodEventState.WARNING),
    ],
)
def test_official_warning_policy_is_explicit(severity, expected):
    decision = evaluate_official_warning(
        severity=severity,
        hazards=["Heavy rain"],
        policy=policy(),
    )

    assert decision.state == expected
    assert decision.rule_id == f"test-v1:official-warning-{severity}"
    assert "Heavy rain" in decision.trigger_summary or severity == "green"


def test_policy_rejects_direct_severe_when_satellite_is_required():
    with pytest.raises(ValueError, match="cannot directly produce severe"):
        EventRulePolicy.from_mapping(
            {
                "version": "unsafe-v1",
                "official_warning_state": {
                    "green": None,
                    "yellow": "watch",
                    "orange": "warning",
                    "red": "severe",
                },
                "severe_requires_satellite_inundation": True,
            }
        )


def test_unknown_severity_fails_closed():
    with pytest.raises(ValueError, match="Unsupported"):
        evaluate_official_warning(severity="purple", hazards=[], policy=policy())
