# Phase 4 event engine and Phase 5 event view

JalDrishti converts evidence into an operational event only through a small,
versioned and inspectable policy. The evaluator runs every five minutes and is
also queued after a successful warning or rainfall ingestion.

## State policy

The authoritative configuration is
[`configs/event_rules.json`](../configs/event_rules.json). Version
`assam-official-warning-v1` maps the current IMD day-one warning as follows:

| Official warning | JalDrishti state |
| --- | --- |
| Green | no new event; an existing event enters recovery |
| Yellow | watch |
| Orange | warning |
| Red | warning |

The distinction is intentional. A red weather warning is not itself proof of
observed inundation or impact. The `severe` event state is reserved for a later
rule that also requires satellite-observed flood extent and exposure evidence.

Open-Meteo rainfall guidance is attached as supporting evidence and never
creates an event by itself. The NWDP pilot station is likewise unable to
trigger a state because its public feed does not publish a timezone, datum,
stable station identifier, or warning/danger thresholds.

## Lifecycle and idempotency

The event identifier is deterministic for the region, district, and official
warning validity date. A PostgreSQL advisory transaction lock prevents two
evaluators from mutating Assam events concurrently. Repeated evaluations update
the existing event and evidence records rather than creating duplicates.

When the authoritative warning returns to green, an open event enters
`recovery`. It closes only after the configured 24-hour grace period remains
green. Every creation, state transition, and closure is written once to the
timeline using a deterministic entry identifier.

## Evidence and interface

Each event retains:

- its current state, trigger summary, rule version, and rule rationale;
- primary district and canonical geometry;
- official warning, rainfall, river, and satellite evidence statuses;
- provenance-bearing evidence records; and
- an append-only lifecycle timeline.

The API exposes the active-event collection and per-event evidence/timeline.
The MapLibre and SVG views both render the active event geometry, and the
record inspector explains why the state exists. Facilities remain opt-in to
avoid obscuring event geography.

This is decision-support software, not an authorised public warning system.
The interface must continue to distinguish official source evidence,
model-derived context, rule output, observed inundation, exposure, and confirmed
damage.
