# Phase 7 — satellite product comparison

JalDrishti can compare one derived flood-change extent with an independently
sourced reference polygon. The comparison runs in a local UTM CRS and stores
the detected area, reference area, overlap, union, area difference, IoU, Dice,
precision, recall, acquisition-time offset, reference provenance, parameters,
and an interpretation caveat.

The API exposes persisted comparisons at
`/api/v1/events/{event_id}/satellite-comparisons`. The event inspector says
**Not configured** when no independent product has been supplied; it never
substitutes the detected extent for a reference or invents an accuracy score.

Comparison metrics describe agreement between two mapped products. They are
not field-verified accuracy, and temporal, resolution, sensor, cloud, and
classification differences remain material. Adding a reference product
requires an ingestion adapter that records its source URL, version, observation
time, geometry and licence before invoking the metric kernel.
