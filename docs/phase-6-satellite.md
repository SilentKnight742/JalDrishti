# Phase 6 — event-scoped satellite observation

JalDrishti searches for satellite evidence only for an existing flood event. It
does not continuously download or process all Sentinel-1 coverage over Assam.

## Workflow

1. An operator requests a satellite observation from an event inspector.
2. The API creates an idempotent job and calculates explicit before/after windows.
3. A Celery worker searches the public ASF OPERA-S1 catalogue using the event
   bounding envelope. Exact clipping is deferred to processing so complex
   district boundaries cannot exceed HTTP request-line limits.
4. The worker selects the nearest same-burst, same-orbit, same-direction
   before/after pair with both VV and VH assets.
5. If credentials are available, source rasters are downloaded with expected-size
   checks, archived with hashes, reprojected to a local metric CRS, mosaicked,
   filtered, and passed through the extracted RadarWatch change detector.
6. Valid coverage is checked before a Cloud Optimized GeoTIFF and WGS84 vector
   extent are persisted and attached to the event.

The job records algorithm, parameters, window, catalogue URL, selected scenes,
source versions, acquisition times, asset metadata, processing output and all
terminal errors. Repeating the same request returns the existing job.

## Honest terminal states

- `no_scenes`: no compatible pair exists in the requested windows.
- `awaiting_credentials`: matching scenes exist but Earthdata access is absent.
- `completed_no_extent`: processing completed but found no defensible change.
- `completed`: a provenance-bearing potential-inundation extent is available.
- `failed`: the catalogue, download, validation or processing contract failed.

These states are visible in the event inspector and source monitor. A derived
extent is labelled satellite-observed change evidence, not confirmed flooding,
depth, road closure, building damage, or affected population.

## Access requirements

ASF catalogue search is public. OPERA assets require a NASA Earthdata account,
valid credentials and accepted ASF terms. Development can use
`EARTHDATA_TOKEN` or `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD`; keep these out of
Git. The project can validate the catalogue/no-scene path without credentials.

References:

- ASF Search API: https://docs.asf.alaska.edu/api/basics/
- ASF authentication practices: https://docs.asf.alaska.edu/asf_search/BestPractices/
- Earthaccess authentication: https://earthaccess.readthedocs.io/en/latest/user/explanation/authenticate/
