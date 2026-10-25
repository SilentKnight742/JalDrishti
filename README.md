# JalDrishti

**Evidence-driven flood intelligence and response support for Assam.**

JalDrishti combines hydrometeorological observations, satellite flood evidence,
infrastructure exposure, incident reports, and provenance in one operational
picture. It is a research and portfolio system, not an authorised emergency
service. Detection and geometric exposure are never presented as confirmed
damage.

## Current milestone

Phase 0 through Phase 10 establish the portfolio-complete MVP:

- React, TypeScript, Vite, and MapLibre web application
- FastAPI service with GeoJSON geography endpoints
- PostgreSQL/PostGIS canonical geography model
- Redis and a Celery worker foundation
- versioned, provenance-bearing Assam geography ingestion (35 districts, 129
  settlements, 17 selected major rivers, and 1,481 facilities)
- Docker Compose development environment
- a frozen, independently reproducible Valencia case study
- an hourly, idempotent NWDP Assam river-level ingestion path with raw-response
  archiving, canonical station/observation tables, API endpoints, and a pilot
  gauge layer
- half-hourly official IMD district-warning ingestion from the public warning
  map WFS, with all five published forecast days retained
- three-hourly, 72-hour ECMWF IFS rainfall guidance for representative points
  in all 35 districts, explicitly labelled as model-derived
- interactive MapLibre and no-WebGL SVG layers for warnings, rainfall guidance,
  districts, rivers, settlements, the pilot gauge, and opt-in facilities
- a five-minute transparent event engine that maps official warning severity to
  district event states using a versioned JSON policy
- active event APIs and map layers with inspectable trigger rationale, evidence
  records, and append-only lifecycle timelines
- event-scoped, idempotent OPERA Sentinel-1 catalogue and processing jobs with
  credential-aware terminal states, raw catalogue/asset provenance, metric-CRS
  coverage validation, COG output, PostGIS extents, and UI controls
- external-product comparison contracts and metric-CRS IoU, Dice, precision,
  recall, and area-difference kernels, with an explicit not-configured state
- reproducible potential-exposure snapshots for represented settlements,
  facilities, population attributes, and road overlap
- a 30,260-record attributed OSM backbone-road dataset plus potential road
  disruption and settlement-to-major-road/hospital reachability screening
- privacy-separated direct public reporting with Assam-boundary validation,
  rate limiting, idempotency, encrypted optional contact details, metadata-
  stripped private photos, coarsened public locations, and unverified map labels

The public Assam telemetry resource is deliberately treated as a degraded
pilot. It currently exposes one station and does not publish a timezone, stable
station identifier, datum, or warning/danger thresholds. JalDrishti displays
the readings and those limitations, but does not derive a flood state from
them. The event engine can create a `watch` from an official yellow warning and
a `warning` from an official orange or red warning. Rainfall guidance remains
supporting evidence only. A `severe` state is deliberately unavailable until
satellite-observed inundation and exposure evidence are available. Verified
multi-station hydrology remains unavailable and cannot trigger a state.

## Repository layout

```text
apps/api/                  FastAPI application
apps/web/                  React + MapLibre application
packages/jaldrishti/       shared domain, ingestion, geospatial, and SAR code
workers/                   Celery worker entrypoint and task routing
migrations/                PostGIS schema migrations
configs/                   region and source policy
case_studies/valencia/     frozen RadarWatch Valencia v1 capsule
tests/                     Python unit and source/API contract tests
apps/web/e2e/              browser-to-API Playwright smoke tests
```

The historical Valencia implementation remains available from the annotated
`radarwatch-valencia-v1` tag and as a self-contained capsule under
`case_studies/valencia`. Streamlit and Folium are not dependencies of the new
application.

## Local development

Requirements:

- Docker with Compose
- Node.js 22 or newer for frontend-only development
- Python 3.12–3.14 and [`uv`](https://docs.astral.sh/uv/) for local Python work

```bash
cp .env.example .env
docker compose up --build
```

The web application is served at `http://localhost:8080`; the API and its
OpenAPI documentation are available at `http://localhost:8000` and
`http://localhost:8000/docs`.

Run local checks without containers:

```bash
uv sync --all-packages --group dev
uv run ruff check .
uv run pytest

cd apps/web
npm install
npm run lint
npm test
npm run build

# With the Compose application still running:
npx playwright install chromium
npm run test:e2e
```

## Data policy

Every operationally meaningful record carries source, source record ID,
observation/publication/ingestion timestamps, source URL and version, and a
quality classification. Administrative geometry is configured from the Survey
of India ABDB; selected settlements, major-river context, and facilities use
attributed OpenStreetMap data. Raw external responses are archived outside Git
before normalisation.

The Phase 1 API exposes `/api/v1/regions`, `/api/v1/districts`,
`/api/v1/settlements`, `/api/v1/rivers`, and `/api/v1/facilities` as GeoJSON.
The Phase 2 pilot adds `/api/v1/stations` as GeoJSON and
`/api/v1/stations/{station_id}/observations` as a provenance-bearing time
series contract. Phase 3 adds `/api/v1/warnings?region_id=assam&day=1` and
`/api/v1/weather/forecasts?region_id=assam&hours=24` as GeoJSON. Phase 4 adds
`/api/v1/events`, `/api/v1/events/{event_id}/evidence`, and
`/api/v1/events/{event_id}/timeline`. Phase 6 adds event satellite-job creation,
job status, and `/api/v1/events/{event_id}/flood-extents`. Phases 7–9 add
`/api/v1/events/{event_id}/satellite-comparisons`,
`/api/v1/events/{event_id}/impact`, and
`/api/v1/events/{event_id}/accessibility`. Phase 10 adds multipart
`POST /api/v1/incidents/report` and public-safe
`GET /api/v1/events/{event_id}/incidents`.

Celery Beat schedules the NWDP adapter hourly. Each source response is archived
in the Docker `raw-data` volume before validation and persistence. To trigger a
development ingestion immediately:

```bash
docker compose exec worker celery --app jaldrishti_workers.celery_app:celery_app \
  call jaldrishti.ingestion.nwdp_assam
docker compose exec worker celery --app jaldrishti_workers.celery_app:celery_app \
  call jaldrishti.ingestion.imd_warnings_assam
docker compose exec worker celery --app jaldrishti_workers.celery_app:celery_app \
  call jaldrishti.ingestion.rainfall_forecast_assam
docker compose exec worker celery --app jaldrishti_workers.celery_app:celery_app \
  call jaldrishti.events.evaluate_assam
```

See [`configs/assam.yaml`](configs/assam.yaml) and
[`configs/sources.yaml`](configs/sources.yaml) for the source contracts and
freshness policy. See [`docs/phase-2-nwdp-pilot.md`](docs/phase-2-nwdp-pilot.md)
for the telemetry limitations and
[`docs/phase-3-weather-warnings.md`](docs/phase-3-weather-warnings.md) for
warning/model semantics, attribution, and production constraints, and
[`docs/phase-4-event-engine.md`](docs/phase-4-event-engine.md) for the event
states, versioned rules, lifecycle, and evidence contract, and
[`docs/phase-6-satellite.md`](docs/phase-6-satellite.md) for catalogue,
authentication, processing and uncertainty semantics.
The remaining MVP methods and caveats are documented in
[`docs/phase-7-satellite-comparison.md`](docs/phase-7-satellite-comparison.md),
[`docs/phase-8-impact.md`](docs/phase-8-impact.md),
[`docs/phase-9-accessibility.md`](docs/phase-9-accessibility.md), and
[`docs/phase-10-incident-reporting.md`](docs/phase-10-incident-reporting.md).

## Valencia case study

The previous SAR flood/change application is intentionally isolated:

```bash
cd case_studies/valencia
uv sync --all-extras
uv run pytest
uv run streamlit run app.py
```

Its original documentation, dependency lock, tests, demo bundle, and caveats
remain byte-for-byte preserved from RadarWatch Valencia v1.

## License and upstream data

JalDrishti source code is licensed under the repository's MIT license. External
datasets retain their own licences and attribution requirements; the MIT licence
does not relicense Survey of India, OpenStreetMap, NASA, Copernicus, or other
upstream data.
