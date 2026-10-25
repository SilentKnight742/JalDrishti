# Phase 3 weather and warning evidence

Phase 3 adds two deliberately separate evidence classes: official India
Meteorological Department district warnings and model-derived rainfall
guidance. Neither source is converted directly into a JalDrishti flood event.

## Official IMD district warnings

The scheduled adapter reads the public WFS layer used by IMD's
[district warning map](https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php?day=1):

- WFS service: `https://reactjs.imd.gov.in/geoserver/wfs`
- feature type: `imd:district_warnings_india`
- schedule: every 30 minutes
- retained horizon: all five published warning days
- quality class: `official`

The normalizer validates the response strictly and maps the 35 Assam IMD
object identifiers to current Survey of India/LGD district identifiers. The
mapping version is stored in provenance. Source spellings and legacy names are
retained as metadata; the API geometry always comes from the canonical Assam
district table.

IMD colour codes are presented as published: green, yellow, orange, and red.
Only non-green warnings are filled on the map by default, while green records
remain queryable and auditable. Hazard labels are decoded from IMD's published
numeric warning codes without creating an independent severity judgment.

The older per-district IMD API currently requires IP whitelisting. Phase 3 does
not depend on it. If IMD later provides a supported authenticated feed, its
identifier, schema, timestamps, terms, and cutover date must be recorded before
replacing the WFS adapter.

## Rainfall model guidance

The second adapter queries the documented [Open-Meteo forecast API](https://open-meteo.com/en/docs)
for ECMWF IFS 0.25-degree guidance:

- model: `ecmwf_ifs025`
- schedule: every 3 hours
- horizon: 72 hourly periods
- spatial support: one point-on-surface representative location per district
- variables: precipitation and precipitation probability
- quality class: `model_derived`

The UI and API call this *rainfall guidance*, never observed rainfall or an
official IMD forecast. A district summary totals the next 24 hourly
precipitation values and reports the maximum hourly probability. It does not
imply uniform rainfall across the district.

Open-Meteo attribution and its [terms](https://open-meteo.com/en/terms) must be
kept with the deployment. The free public endpoint is suitable for this
research/portfolio build but should not be assumed to cover a production or
commercial service; a production operator must confirm an appropriate access
plan and licence.

## Reproducibility and failure behaviour

Every response is archived in the Docker `raw-data` volume before
normalisation. Forecast and warning identifiers are deterministic, and database
upserts are idempotent. Forecast writes are split into bounded transactions to
stay below asyncpg/PostgreSQL bind-parameter limits.

The status endpoint reports each source independently. A missing or stale
weather source does not suppress canonical geography or pilot hydrology. The
map keeps the last persisted evidence with its ingestion timestamp and source
version so an operator can distinguish stale evidence from a current no-warning
state.
