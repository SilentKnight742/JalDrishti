"""Source adapters and normalized ingestion contracts."""

from jaldrishti.ingestion.bootstrap import AssamBootstrap, load_assam_bootstrap
from jaldrishti.ingestion.imd import IMDWarningBatch, normalize_imd_warning_payload
from jaldrishti.ingestion.nwdp import NWDPBatch, normalize_nwdp_payload
from jaldrishti.ingestion.open_meteo import RainfallForecastBatch, normalize_open_meteo_payload

__all__ = [
    "AssamBootstrap",
    "IMDWarningBatch",
    "NWDPBatch",
    "RainfallForecastBatch",
    "load_assam_bootstrap",
    "normalize_imd_warning_payload",
    "normalize_nwdp_payload",
    "normalize_open_meteo_payload",
]
