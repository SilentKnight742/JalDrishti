"""Provenance vocabulary used throughout JalDrishti.

The enum intentionally describes *how* a fact entered the system rather than
pretending that all facts have the same level of certainty.  Later ingestion
adapters can add validation detail in metadata while retaining this stable,
operator-facing classification.
"""

from enum import StrEnum


class ProvenanceQuality(StrEnum):
    """Evidence/provenance classification exposed to API consumers."""

    OFFICIAL = "official"
    COMMUNITY_DATA = "community_data"
    SATELLITE_OBSERVED = "satellite_observed"
    MODEL_DERIVED = "model_derived"
    PUBLIC_REPORT = "public_report"
    OPERATOR_ENTERED = "operator_entered"
    SIMULATED = "simulated"
    UNVERIFIED_REPORT = "unverified_report"
