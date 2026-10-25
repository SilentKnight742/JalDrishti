import numpy as np
import pytest
from jaldrishti.satellite.evaluation import EvaluationInputError, binary_metrics, vector_metrics
from shapely.geometry import Polygon


def test_binary_metrics_match_valencia_pixel_area_parity() -> None:
    predicted = np.array([[1, 1], [0, 0]], dtype=bool)
    reference = np.array([[1, 0], [1, 0]], dtype=bool)
    valid = np.ones((2, 2), dtype=bool)

    result = binary_metrics(
        predicted,
        reference,
        valid,
        0.0009,
        label="test",
        caveat="not ground truth",
        acquired_at="2024-10-31T18:02:00Z",
    )

    assert result.true_positive_pixels == 1
    assert result.false_positive_pixels == 1
    assert result.false_negative_pixels == 1
    assert result.true_negative_pixels == 1
    assert result.iou == 1 / 3
    assert result.dice_f1 == 0.5
    assert result.precision == 0.5
    assert result.recall == 0.5
    assert result.false_positive_rate == 0.5
    assert result.detected_area_km2 == 0.0018
    assert result.reference_area_km2 == 0.0018
    assert result.overlap_area_km2 == 0.0009


def test_invalid_pixels_are_excluded_from_counts_and_area() -> None:
    result = binary_metrics(
        np.array([[1, 1]], dtype=bool),
        np.array([[1, 0]], dtype=bool),
        np.array([[1, 0]], dtype=bool),
        1.0,
        label="fixture",
        caveat="comparison only",
        acquired_at="2026-09-22T00:00:00Z",
    )

    assert result.true_positive_pixels == 1
    assert result.false_positive_pixels == 0
    assert result.valid_comparison_area_km2 == 1.0


def test_binary_metrics_reject_empty_comparison_domain() -> None:
    with pytest.raises(EvaluationInputError, match="at least one"):
        binary_metrics(
            np.zeros((2, 2)),
            np.zeros((2, 2)),
            np.zeros((2, 2)),
            0.0009,
            label="fixture",
            caveat="comparison only",
            acquired_at="2026-09-22T00:00:00Z",
        )


def test_vector_metrics_measure_overlap_in_projected_units() -> None:
    detected = Polygon([(94, 27), (94.1, 27), (94.1, 27.1), (94, 27.1)])
    reference = Polygon([(94.05, 27), (94.15, 27), (94.15, 27.1), (94.05, 27.1)])

    result = vector_metrics(detected, reference)

    assert result.analysis_crs == "EPSG:32646"
    assert result.iou == pytest.approx(1 / 3, rel=0.01)
    assert result.dice_f1 == pytest.approx(0.5, rel=0.01)
    assert result.precision == pytest.approx(0.5, rel=0.01)
    assert result.recall == pytest.approx(0.5, rel=0.01)
    assert result.overlap_area_km2 > 50


def test_vector_metrics_reject_non_polygon_reference() -> None:
    detected = Polygon([(94, 27), (94.1, 27), (94.1, 27.1), (94, 27.1)])

    with pytest.raises(EvaluationInputError, match="reference geometry must be polygonal"):
        vector_metrics(detected, detected.boundary)
