# Phase 9 — road accessibility screening

JalDrishti builds a routable screening graph from a reproducible Assam extract
of selected OpenStreetMap backbone roads. The committed bootstrap contains
30,260 motorway, trunk, primary, secondary, tertiary, and unclassified road
records from the Geofabrik North-Eastern Zone extract dated 23 September 2026.
The extract is ODbL data and requires visible OpenStreetMap attribution.

After a satellite extent is created, road edges intersecting it are removed
from a copy of the graph. The worker then compares before/after reachability for
settlements to represented major roads and hospitals. It persists:

- road geometries with potential flood overlap and intersected length;
- baseline and screened reachability;
- network and snapping coverage; and
- settlements that had represented access before the screen but not after it.

The endpoint `/api/v1/events/{event_id}/accessibility` returns the summary,
potential road disruptions, settlement results, and caveats. The MapLibre and
SVG clients expose separate toggles for road disruptions and access screening.

This is not navigation and does not confirm that a road is closed, safe, or
passable. OSM coverage and topology are incomplete, the flood product has no
depth or velocity, and represented hospitals may be incomplete. Relief-centre
and district-headquarters routing remain not configured because no verified
operational destination dataset has been loaded.
