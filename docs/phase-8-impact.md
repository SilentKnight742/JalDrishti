# Phase 8 — potential exposure

When a satellite change extent is persisted, the worker creates a reproducible
impact snapshot. It intersects the extent with the available canonical source
records and retains every contributing feature with provenance.

The current Assam snapshot reports:

- inundated-change area from the satellite extent;
- intersecting settlement and selected facility points;
- population only where an intersecting settlement record contains a published
  population value; and
- road overlap when the Phase 9 road screen is available.

Buildings, cropland, railways, and population surfaces are not configured.
Their values remain null or are explicitly marked unavailable; missing data is
never displayed as measured zero. Point intersection also does not establish
that a whole settlement population or facility is affected.

The API endpoint is `/api/v1/events/{event_id}/impact`. Every label uses
**potential exposure**, not observed damage, casualties, loss, or service
disruption.
