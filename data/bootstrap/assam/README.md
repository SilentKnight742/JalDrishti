# Assam development bootstrap

This directory contains the attributed, network-independent Phase 1 data loaded
by `docker compose up`:

- `regions.geojson` and `districts.geojson` use the official Survey of India
  Administrative Boundary Data Base (ABDB) snapshot. The district layer has the
  current 35-feature coverage and its `DIST_LGD` codes.
- `facilities.geojson` contains selected named hospitals, clinics, doctors,
  schools, police facilities, and fire stations from OpenStreetMap via Overpass.
- `settlements.geojson` contains 129 OSM `city`/`town` points clipped to the
  official state boundary.
- `rivers.geojson` contains 17 reviewed, named major-river line sets clipped to
  Assam. This is a map backdrop, not a connected flow-network model.
- `roads.geojson` contains 30,260 OSM routable-backbone way parts from the
  current Geofabrik North-Eastern India extract, clipped to Assam. It supports
  potential-access disruption screening, not confirmed closure or legal routing.
- `manifest.json` identifies both sources and the exact transformations applied.

Every boundary feature retains its ABDB layer/object ID, raw source name, source
version, and `official` quality classification. Display names correct a few
capitalisation, spelling, or expanded-name issues without hiding the raw value.
Every OSM feature retains stable source identifiers, a source URL/version, and
the `community_data` quality classification.

## Boundary normalization

The official archive is not committed. The checked-in geometry was generated
from the ABDB state and district shapefiles in their original `LCC_WGS84`
metre-based CRS. Districts are topology-preservingly simplified as a coverage at
25 metres, transformed to EPSG:4326, and serialized to seven decimal places.
OSM facilities are then clipped to that official district coverage so the
database can assign every retained facility without inventing a nearest-area
match. The full-detail archive remains the source for survey-grade work.

Reproduce the checked-in boundaries after extracting the ABDB archive:

```bash
uv run python scripts/build_soi_assam_boundaries.py \
  --state-boundary '/path/to/State Boundary/State Boundary.shp' \
  --district-boundary '/path/to/District Boundary/District Boundary.shp' \
  --archive '/path/to/State_District_Subdistrict_PAN INDIA.rar' \
  --output data/bootstrap/assam \
  --source-version abdb-2026-05-07 \
  --archive-http-last-modified 2026-05-12 \
  --retrieved-at 2026-09-22T03:00:00Z \
  --simplify-metres 25 \
  --expected-archive-sha256 b8325e5d9dd0f04a6663d775363fe38cd2f23bd9dbae3fb7118b4e6e0ce0bcb7
```

The normalizer verifies the archive checksum, the expected 35 LGD codes and raw
names, geometry validity, coverage topology, and agreement between the state
and district layers. It rewrites `regions.geojson`, `districts.geojson`,
`facilities.geojson`, and `manifest.json`; facility source records and
provenance are preserved while out-of-coverage points are excluded.

The original OSM-only export utility is `scripts/build_assam_bootstrap.py`.
Run the ABDB normalizer after that utility whenever the facility bootstrap is
refreshed.

## Settlement and river normalization

The context layers were selected with bounded OSM queries, then normalized with
the official Assam polygon as the clip boundary. Rebuild them from frozen OSM
API node batches and an Overpass `out geom` river response:

```bash
uv run python scripts/build_osm_assam_context.py \
  --settlements /path/to/settlement-nodes-1.json /path/to/settlement-nodes-2.json \
  --settlement-source-version osm-api-YYYY-MM-DD \
  --rivers /path/to/major-rivers-overpass.json \
  --output data/bootstrap/assam \
  --retrieved-at YYYY-MM-DDTHH:MM:SSZ
```

The script excludes points outside the official boundary, merges river way
segments under reviewed display names, strips OSM contributor/user metadata,
and updates counts and source versions in the manifest. Public Overpass is used
only to prepare a frozen development snapshot; production refreshes use the
bulk Geofabrik extract configured in `configs/assam.yaml`.

## Road-network normalization

Rebuild the accessibility network from a current Geofabrik extract:

```bash
uv run python scripts/build_osm_assam_roads.py \
  --pbf /path/to/north-eastern-zone-latest.osm.pbf \
  --region data/bootstrap/assam/regions.geojson \
  --output data/bootstrap/assam/roads.geojson \
  --manifest data/bootstrap/assam/manifest.json \
  --source-version geofabrik-YYYY-MM-DDTHH:MM:SSZ \
  --download-url https://download.geofabrik.de/asia/india/north-eastern-zone-latest.osm.pbf
```

The builder retains motorway through tertiary roads plus unclassified
connectors, clips them to the official state boundary, simplifies by two
metres in a projected CRS, strips contributor metadata, and records the source
archive checksum. Residential, service, track and foot-only ways are excluded;
therefore a missing connection means “not represented in this screening
network,” not “no route exists.”

## Terms and attribution

Administrative boundaries remain subject to the Survey of India terms stated
by the upstream ABDB source. OpenStreetMap data is © OpenStreetMap contributors
and available under the Open Data Commons Open Database License (ODbL) 1.0; see
<https://www.openstreetmap.org/copyright>. The repository's MIT licence applies
to source code, not to either dataset.
