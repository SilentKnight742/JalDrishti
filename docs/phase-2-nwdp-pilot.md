# Phase 2 NWDP Assam telemetry pilot

JalDrishti ingests the public **River Water Level (Telemetry - Hourly), Assam
Department** resource from the National Water Data Portal. This is an ingestion
and presentation pilot, not a production flood-warning feed.

## What is implemented

- paginated CKAN retrieval every hour through Celery Beat
- immutable timestamped raw-response archives in the Docker `raw-data` volume
- strict field, coordinate, state-code, timestamp, and numeric validation
- deterministic internal station and observation identities
- idempotent PostGIS station and observation upserts
- `/api/v1/stations` and `/api/v1/stations/{id}/observations`
- a MapLibre **Gauge pilot** layer and an evidence inspector with recent readings

## Limitations preserved by the data model

As verified on 24 September 2026, the current 2026–2030 resource contains 818
rows but only one station, `NH15 Crossing Fakirpara Tangni`. Its newest source
observation is labelled `22-09-2026 23:00`.

The source does not publish:

- a stable station identifier
- observation timezone
- gauge datum
- warning or danger levels
- useful river or basin values for the exposed station
- a coverage or update-latency service commitment

Accordingly, `observed_at` remains null while the original source-local text is
preserved in `source_observed_at`. Alert thresholds and datum remain null. The
UI labels the layer **Pilot**, describes coverage as incomplete, and does not
calculate flood state, threshold distance, or hourly rise rates.

## Evidence needed before operational use

Obtain confirmation from NWIC and the Assam producer for:

1. intended station coverage and a stable station identifier;
2. timestamp timezone and daylight/clock semantics;
3. gauge datum plus warning and danger levels;
4. river/basin metadata and missing-value conventions;
5. quality-control flags, revision semantics, and update-latency expectations;
6. explicit terms for automated republication.

Contacts published with the dataset are `helpdesk-nwic@gov.in` and
`assamwrd@gmail.com`.
