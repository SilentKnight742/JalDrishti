import numpy as np
import pytest
from jaldrishti.satellite.detection import (
    ChangeThresholds,
    DetectionInputError,
    classify_evidence,
    derive_water_threshold,
)


def test_classify_evidence_matches_valencia_moderate_and_high_parity() -> None:
    post = np.full((9, 9), -10.0, dtype=np.float32)
    delta_vv = np.zeros_like(post)
    delta_vh = np.zeros_like(post)
    post[2:7, 2:7] = -18
    delta_vv[2:7, 2:7] = -4
    delta_vh[2:7, 2:5] = -3

    result = classify_evidence(
        post,
        delta_vv,
        delta_vh,
        -15,
        ChangeThresholds(vv_drop_db=-3, vh_drop_db=-2),
        min_component_pixels=2,
    )

    assert result.detected.sum() == 25
    assert np.count_nonzero(result.evidence == 2) == 15
    assert np.count_nonzero(result.evidence == 1) == 10


def test_derived_threshold_matches_valencia_clamping_parity() -> None:
    rng = np.random.default_rng(7)
    values = np.concatenate(
        [rng.normal(-30, 0.2, 1000), rng.normal(-8, 0.2, 1000), rng.normal(-2, 0.2, 1000)]
    ).reshape(60, 50)

    result = derive_water_threshold(values, (-20, -12))

    assert result.value_db == -20
    assert result.method == "multi_otsu_3class_clamped"


def test_explicit_threshold_override_is_transparent_and_unclamped() -> None:
    result = derive_water_threshold(
        np.ones((2, 2), dtype=np.float32),
        (-20, -12),
        override_db=-16.5,
    )

    assert result.value_db == -16.5
    assert result.method == "config_override"


def test_morphology_never_creates_evidence_in_invalid_cells() -> None:
    post = np.full((5, 5), -18.0, dtype=np.float32)
    delta_vv = np.full_like(post, -4.0)
    delta_vh = np.full_like(post, -3.0)
    post[2, 2] = np.nan

    result = classify_evidence(
        post,
        delta_vv,
        delta_vh,
        -15,
        ChangeThresholds(vv_drop_db=-3, vh_drop_db=-2),
        min_component_pixels=1,
    )

    assert not result.detected[2, 2]
    assert result.evidence[2, 2] == 0


def test_classification_rejects_mismatched_grids() -> None:
    with pytest.raises(DetectionInputError, match="share one shape"):
        classify_evidence(
            np.ones((2, 2), dtype=np.float32),
            np.ones((2, 3), dtype=np.float32),
            np.ones((2, 2), dtype=np.float32),
            -15,
            ChangeThresholds(vv_drop_db=-3, vh_drop_db=-2),
            min_component_pixels=1,
        )
