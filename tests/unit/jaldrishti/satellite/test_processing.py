from pathlib import Path

import numpy as np
import pytest
import rasterio
from jaldrishti.satellite.processing import SarRasterSet, process_opera_rtc_change
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from shapely.geometry import box


def write_raster(path: Path, values: np.ndarray, transform, crs: str, *, nodata=None) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype=str(values.dtype),
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dataset:
        dataset.write(values, 1)
    return path


def test_opera_rtc_processing_writes_traceable_extent(tmp_path):
    crs = "EPSG:32646"
    raster_transform = from_origin(500_000, 3_000_000, 30, 30)
    shape = (64, 64)
    before_vv = np.full(shape, 0.1, dtype=np.float32)
    before_vh = np.full(shape, 0.05, dtype=np.float32)
    after_vv = before_vv.copy()
    after_vh = before_vh.copy()
    after_vv[20:36, 18:38] = 0.005
    after_vh[20:36, 18:38] = 0.002
    mask = np.zeros(shape, dtype=np.uint8)

    before = SarRasterSet(
        product_id="before",
        vv=write_raster(tmp_path / "before-vv.tif", before_vv, raster_transform, crs),
        vh=write_raster(tmp_path / "before-vh.tif", before_vh, raster_transform, crs),
        mask=write_raster(tmp_path / "before-mask.tif", mask, raster_transform, crs, nodata=255),
    )
    after = SarRasterSet(
        product_id="after",
        vv=write_raster(tmp_path / "after-vv.tif", after_vv, raster_transform, crs),
        vh=write_raster(tmp_path / "after-vh.tif", after_vh, raster_transform, crs),
        mask=write_raster(tmp_path / "after-mask.tif", mask, raster_transform, crs, nodata=255),
    )
    west, south, east, north = transform_bounds(
        crs,
        "EPSG:4326",
        500_000,
        3_000_000 - shape[0] * 30,
        500_000 + shape[1] * 30,
        3_000_000,
    )
    aoi = box(west, south, east, north)
    output = tmp_path / "evidence.tif"

    product = process_opera_rtc_change(
        before=[before],
        after=[after],
        geometry_wgs84=aoi,
        output_path=output,
        median_kernel=1,
        water_threshold_override_db=-15,
        min_component_pixels=4,
        minimum_valid_coverage=0.95,
    )

    assert output.is_file()
    assert product.geometry_wgs84.geom_type == "MultiPolygon"
    assert product.area_km2 > 0
    assert product.high_evidence_area_km2 > 0
    assert product.valid_coverage_fraction >= 0.95
    assert product.analysis_crs == crs
    assert product.raster_record["sha256"]
    assert product.parameters["terminology"].startswith("satellite-observed")
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    projected = __import__("shapely.ops", fromlist=["transform"]).transform(
        transformer.transform,
        product.geometry_wgs84,
    )
    assert projected.area / 1_000_000 == pytest.approx(product.area_km2)
