# Phase 10 — direct incident reporting

The web application provides a mobile-ready **Report incident** flow for
stranded people, medical emergencies, flooded roads, bridge damage, building
flooding, embankment issues, and other flood incidents. It is not an emergency
dispatch channel and tells users to call 112 for immediate danger.

## Privacy and security boundaries

- A report requires explicit consent and a device location inside the official
  Assam boundary.
- The exact point and private description are stored only in the internal
  report table. The public point is rounded to 0.01 degrees, approximately one
  kilometre.
- Optional contact details are encrypted with Fernet in a separate table and
  are never returned by the public API.
- JPEG, PNG, and WebP uploads are decoded and re-encoded as private JPEG files,
  which removes EXIF and ancillary metadata. Files are limited to 8 MB and live
  in a private Docker volume that nginx does not serve. This is content
  normalisation, not a claim of malware scanning.
- Redis limits submissions per client address. A client-generated UUID makes
  retries idempotent, while reuse of that UUID for different content is
  rejected.
- Non-development deployments refuse the checked-in development encryption
  key and must inject a rotated Fernet key and key identifier.

Reports are linked to the newest open event whose geometry covers the exact
point. A linked report immediately appears at its coarsened location and adds
an evidence/timeline item, always marked `unverified_report`. Reports outside
an active event are retained for review but do not appear in an event layer.

The public contracts are:

- `POST /api/v1/incidents/report` using multipart form data; and
- `GET /api/v1/events/{event_id}/incidents` returning public-safe GeoJSON.

There is deliberately no public endpoint for exact points, descriptions,
contacts, or media. Verification and operator case-management are future
authenticated administrative functions.
