from jaldrishti.impact.snapshot import PointAsset, summarise_point_exposure


def test_point_exposure_distinguishes_partial_population_and_unavailable_layers():
    result = summarise_point_exposure(
        [
            PointAsset("settlement", "s1", "Known population", 1200),
            PointAsset("settlement", "s2", "Unknown population", None),
            PointAsset("facility", "f1", "District Hospital"),
        ]
    )

    assert result.settlement_count == 2
    assert result.facility_count == 1
    assert result.population_potentially_exposed == 1200
    assert result.population_record_count == 1
    assert result.coverage["population"]["status"] == "partial"
    assert result.coverage["roads"]["status"] == "not_configured"
    assert result.coverage["buildings"]["status"] == "not_configured"


def test_absent_population_is_none_not_zero():
    result = summarise_point_exposure(
        [PointAsset("settlement", "s1", "No published population", None)]
    )

    assert result.population_potentially_exposed is None
    assert result.population_record_count == 0
    assert result.coverage["population"]["status"] == "not_available"
