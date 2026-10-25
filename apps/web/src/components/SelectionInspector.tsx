import { formatTimestamp } from "../lib/freshness";
import type {
  AccessibilityResponse,
  EventEvidenceProperties,
  EventProperties,
  EventTimelineItem,
  FloodExtentProperties,
  GeographyCollection,
  GeographyProperties,
  ImpactResponse,
  IncidentProperties,
  SelectedMapFeature,
  SatelliteJob,
  SatelliteComparisonProperties,
  StationObservationSeries,
  StationProperties,
  WarningProperties,
  WeatherSummaryProperties,
} from "../types";
import { Icon } from "./Icon";
import { StatusBadge } from "./StatusBadge";

interface SelectionInspectorProps {
  selection: SelectedMapFeature | null;
  districtDetail?: GeographyProperties;
  isDetailLoading: boolean;
  stationObservations?: StationObservationSeries;
  isStationDetailLoading: boolean;
  hasStationDetailError: boolean;
  eventEvidence?: GeographyCollection<EventEvidenceProperties>;
  eventTimeline?: EventTimelineItem[];
  satelliteJobs?: SatelliteJob[];
  floodExtents?: GeographyCollection<FloodExtentProperties>;
  satelliteComparisons?: GeographyCollection<SatelliteComparisonProperties>;
  impact?: ImpactResponse;
  accessibility?: AccessibilityResponse;
  incidents?: GeographyCollection<IncidentProperties>;
  isEventDetailLoading?: boolean;
  hasEventDetailError?: boolean;
  isRequestingSatellite?: boolean;
  satelliteRequestError?: boolean;
  onRequestSatellite?: () => void;
  onClear: () => void;
}

const DetailRow = ({ label, value }: { label: string; value: string }) => (
  <div className="detail-row">
    <dt>{label}</dt>
    <dd>{value}</dd>
  </div>
);

const trustedSourceUrl = (value: string | null | undefined): string | null => {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
};

const asStringList = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value !== "string" || !value.trim()) return [];
  try {
    const parsed = JSON.parse(value) as unknown;
    if (Array.isArray(parsed)) return parsed.map(String);
  } catch {
    // MapLibre may return a simple comma-separated string for array properties.
  }
  return value.split(",").map((item) => item.trim()).filter(Boolean);
};

const StationSparkline = ({ series }: { series: StationObservationSeries }) => {
  const observations = [...series.observations].slice(0, 24).reverse();
  if (observations.length < 2) return null;
  const levels = observations.map((item) => item.water_level_m);
  const minimum = Math.min(...levels);
  const maximum = Math.max(...levels);
  const range = Math.max(maximum - minimum, 0.001);
  const points = levels
    .map((level, index) => {
      const x = 4 + (index / (levels.length - 1)) * 272;
      const y = 58 - ((level - minimum) / range) * 50;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="station-sparkline">
      <div className="station-sparkline__heading">
        <span>Recent source sequence</span>
        <small>{observations.length} readings</small>
      </div>
      <svg viewBox="0 0 280 64" role="img" aria-label="Recent pilot water-level readings">
        <line x1="4" x2="276" y1="58" y2="58" />
        <polyline points={points} />
      </svg>
      <div className="station-sparkline__range">
        <span>{minimum.toFixed(3)} m</span>
        <span>{maximum.toFixed(3)} m</span>
      </div>
    </div>
  );
};

export function SelectionInspector({
  selection,
  districtDetail,
  isDetailLoading,
  stationObservations,
  isStationDetailLoading,
  hasStationDetailError,
  eventEvidence,
  eventTimeline,
  satelliteJobs = [],
  floodExtents,
  satelliteComparisons,
  impact,
  accessibility,
  incidents,
  isEventDetailLoading = false,
  hasEventDetailError = false,
  isRequestingSatellite = false,
  satelliteRequestError = false,
  onRequestSatellite,
  onClear,
}: SelectionInspectorProps) {
  if (!selection) {
    return (
      <section className="inspector inspector--empty" aria-labelledby="inspector-title">
        <div className="inspector__symbol" aria-hidden="true">
          <Icon name="pin" size={26} />
        </div>
        <span className="eyebrow">Map inspection</span>
        <h2 id="inspector-title">Select a mapped record</h2>
        <p>Choose a mapped feature to inspect its source, quality and ingestion timestamp.</p>
      </section>
    );
  }

  const properties =
    selection.kind === "district" && districtDetail ? districtDetail : selection.properties;
  const kindLabel = {
    district: "District",
    facility: "Facility",
    settlement: "Settlement",
    river: "River",
    station: "Gauge station",
    weather: "Rainfall guidance",
    warning: "Official warning",
    event: "Flood event",
    extent: "Satellite flood extent",
    road_disruption: "Potential road disruption",
    accessibility: "Settlement accessibility",
    incident: "Unverified public report",
  }[selection.kind];
  const category = selection.kind === "facility" ? selection.properties.category : null;
  const context =
    selection.kind === "settlement"
      ? selection.properties.settlement_type
      : selection.kind === "river"
        ? selection.properties.river_class
        : selection.kind === "station"
          ? selection.properties.river_name || "River not published"
          : selection.kind === "warning"
            ? `Valid ${selection.properties.valid_date}`
            : selection.kind === "event"
              ? `${selection.properties.state.toUpperCase()} · rule-derived state`
            : selection.kind === "extent"
              ? `${selection.properties.area_km2.toFixed(2)} km² potential inundation`
            : selection.kind === "weather"
              ? "District representative point"
              : selection.kind === "road_disruption"
                ? `${selection.properties.road_class} · ${selection.properties.overlap_km.toFixed(2)} km overlap`
                : selection.kind === "accessibility"
                  ? selection.properties.potentially_isolated
                    ? "Potentially isolated in screened network"
                    : selection.properties.assessment_status.replaceAll("_", " ")
                  : selection.kind === "incident"
                    ? `${selection.properties.public_reference} · approximate public location`
          : category;
  const sourceUrl = trustedSourceUrl(properties.source_url);
  const stationProperties =
    selection.kind === "station" ? (selection.properties as StationProperties) : null;
  const weatherProperties =
    selection.kind === "weather" ? (selection.properties as WeatherSummaryProperties) : null;
  const warningProperties =
    selection.kind === "warning" ? (selection.properties as WarningProperties) : null;
  const eventProperties =
    selection.kind === "event" ? (selection.properties as EventProperties) : null;
  const extentProperties =
    selection.kind === "extent" ? (selection.properties as FloodExtentProperties) : null;
  const disruptionProperties =
    selection.kind === "road_disruption" ? selection.properties : null;
  const accessibilityProperties =
    selection.kind === "accessibility" ? selection.properties : null;
  const incidentProperties =
    selection.kind === "incident" ? selection.properties : null;
  const latestSatelliteJob = satelliteJobs[0];
  const satelliteBusy = Boolean(
    latestSatelliteJob &&
      ["queued", "searching", "downloading", "processing"].includes(latestSatelliteJob.status),
  );
  const latestObservation = stationObservations?.observations[0];
  const detailLoading = isDetailLoading || isStationDetailLoading || isEventDetailLoading;

  return (
    <section className="inspector" aria-labelledby="inspector-title" aria-busy={detailLoading}>
      <div className="inspector__topline">
        <span className="eyebrow">{kindLabel} evidence</span>
        <button className="text-button" type="button" onClick={onClear} aria-label="Close feature details">
          Close
        </button>
      </div>
      <div className="inspector__title-row">
        <div>
          <h2 id="inspector-title">{properties.name}</h2>
          <p>{context ? String(context) : properties.code || "Geographic context"}</p>
        </div>
        <StatusBadge
          condition={
            warningProperties?.severity ||
            eventProperties?.state ||
            stationProperties?.operational_status ||
            properties.quality ||
            "unrated"
          }
        />
      </div>

      {isDetailLoading && <div className="inline-loading">Loading canonical district record…</div>}
      {isStationDetailLoading && (
        <div className="inline-loading">Loading pilot river-level observations…</div>
      )}
      {hasStationDetailError && (
        <div className="inline-loading inline-loading--warning">
          Station observations could not be loaded.
        </div>
      )}
      {isEventDetailLoading && (
        <div className="inline-loading">Loading event evidence and timeline…</div>
      )}
      {hasEventDetailError && (
        <div className="inline-loading inline-loading--warning">
          Event evidence or timeline could not be loaded.
        </div>
      )}

      {eventProperties && (
        <div className={`event-summary event-summary--${eventProperties.state}`}>
          <span>Current transparent-rule state</span>
          <strong>{eventProperties.state.toUpperCase()}</strong>
          <p>{eventProperties.trigger_summary}</p>
          <ul>
            {asStringList(eventProperties.rationale).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {eventProperties && (
        <section className="satellite-panel" aria-labelledby="satellite-panel-title">
          <div className="satellite-panel__heading">
            <div>
              <span>Satellite observation</span>
              <strong id="satellite-panel-title">
                {latestSatelliteJob
                  ? latestSatelliteJob.status.replaceAll("_", " ")
                  : "Not requested"}
              </strong>
            </div>
            <StatusBadge condition={latestSatelliteJob?.status || "not configured"} />
          </div>
          {latestSatelliteJob?.error_message && <p>{latestSatelliteJob.error_message}</p>}
          {!latestSatelliteJob && (
            <p>Search the public ASF catalogue for a compatible before/after OPERA Sentinel-1 observation.</p>
          )}
          {floodExtents && floodExtents.features.length > 0 && (
            <p>{floodExtents.features.length} derived change extent{floodExtents.features.length === 1 ? "" : "s"} available on the map.</p>
          )}
          <button
            type="button"
            className="satellite-panel__action"
            disabled={satelliteBusy || isRequestingSatellite}
            onClick={onRequestSatellite}
          >
            {satelliteBusy || isRequestingSatellite
              ? "Satellite job in progress…"
              : latestSatelliteJob
                ? "Check same observation window"
                : "Request satellite observation"}
          </button>
          {satelliteRequestError && (
            <small role="alert">The satellite request could not be created. Try again after checking system status.</small>
          )}
          <small>Derived extents are change evidence, not automatically confirmed flooding.</small>
        </section>
      )}

      {eventProperties && (
        <section className="impact-panel" aria-labelledby="impact-panel-title">
          <div className="impact-panel__heading">
            <div>
              <span>Potential exposure</span>
              <strong id="impact-panel-title">
                {impact?.status === "available" ? "Model-derived snapshot" : "Not available"}
              </strong>
            </div>
            <StatusBadge condition={impact?.status || "not configured"} />
          </div>
          {impact?.summary ? (
            <>
              <div className="impact-metrics">
                <div><strong>{impact.summary.inundated_area_km2.toFixed(2)}</strong><span>km² extent</span></div>
                <div><strong>{impact.summary.settlement_count}</strong><span>settlement points</span></div>
                <div><strong>{impact.summary.facility_count}</strong><span>selected facilities</span></div>
                <div>
                  <strong>{impact.summary.population_potentially_exposed?.toLocaleString() ?? "—"}</strong>
                  <span>partial population</span>
                </div>
              </div>
              <dl className="impact-coverage">
                <DetailRow
                  label="Road overlap"
                  value={impact.summary.road_overlap_km == null ? "Not configured" : `${impact.summary.road_overlap_km.toFixed(2)} km`}
                />
                <DetailRow
                  label="Buildings"
                  value={impact.summary.building_count == null ? "Not configured" : String(impact.summary.building_count)}
                />
                <DetailRow label="Calculated" value={formatTimestamp(impact.summary.calculated_at)} />
              </dl>
              {impact.exposures.features.length > 0 && (
                <p>{impact.exposures.features.length} intersecting source record{impact.exposures.features.length === 1 ? "" : "s"} retained with provenance.</p>
              )}
            </>
          ) : (
            <p>An impact snapshot will be calculated automatically when a satellite extent is available.</p>
          )}
          <small>{impact?.caveats[0] || "Potential exposure is not confirmed damage or disruption."}</small>
        </section>
      )}

      {eventProperties && (
        <section className="comparison-panel" aria-labelledby="comparison-panel-title">
          <div className="impact-panel__heading">
            <div>
              <span>External product comparison</span>
              <strong id="comparison-panel-title">
                {satelliteComparisons?.features.length
                  ? `${satelliteComparisons.features.length} comparison${satelliteComparisons.features.length === 1 ? "" : "s"}`
                  : "Not configured"}
              </strong>
            </div>
            <StatusBadge condition={satelliteComparisons?.features.length ? "available" : "not configured"} />
          </div>
          {satelliteComparisons?.features.map((feature) => (
            <div className="comparison-result" key={feature.properties.id}>
              <strong>{feature.properties.reference_name}</strong>
              <div>
                <span>IoU {(feature.properties.iou * 100).toFixed(1)}%</span>
                <span>Dice {(feature.properties.dice_f1 * 100).toFixed(1)}%</span>
                <span>Precision {(feature.properties.precision * 100).toFixed(1)}%</span>
                <span>Recall {(feature.properties.recall * 100).toFixed(1)}%</span>
              </div>
              <small>{feature.properties.caveat}</small>
            </div>
          ))}
          {!satelliteComparisons?.features.length && (
            <p>No independent Assam flood product is configured for this observation.</p>
          )}
          <small>Agreement metrics compare mapped products; they are not field-verified accuracy.</small>
        </section>
      )}

      {eventProperties && (
        <section className="accessibility-panel" aria-labelledby="accessibility-panel-title">
          <div className="impact-panel__heading">
            <div>
              <span>Road accessibility</span>
              <strong id="accessibility-panel-title">
                {accessibility?.status === "available" ? "Network screening available" : "Not available"}
              </strong>
            </div>
            <StatusBadge condition={accessibility?.status || "not configured"} />
          </div>
          {accessibility?.summary ? (
            <>
              <div className="impact-metrics">
                <div><strong>{accessibility.summary.potentially_affected_road_count}</strong><span>road segments</span></div>
                <div><strong>{accessibility.summary.potentially_affected_road_km.toFixed(2)}</strong><span>km overlap</span></div>
                <div><strong>{accessibility.summary.assessed_settlement_count}</strong><span>settlements assessed</span></div>
                <div><strong>{accessibility.summary.potentially_isolated_settlement_count}</strong><span>potentially isolated</span></div>
              </div>
              <p>{accessibility.summary.road_count.toLocaleString()} backbone road records formed a {accessibility.summary.graph_edge_count.toLocaleString()}-edge graph.</p>
            </>
          ) : (
            <p>Accessibility is calculated after a satellite extent is available.</p>
          )}
          <small>{accessibility?.caveats[0] || "Potential disruptions are not confirmed road closures."}</small>
        </section>
      )}

      {eventProperties && (
        <section className="incident-panel" aria-labelledby="incident-panel-title">
          <div className="impact-panel__heading">
            <div>
              <span>Community reports</span>
              <strong id="incident-panel-title">
                {incidents?.features.length
                  ? `${incidents.features.length} unverified report${incidents.features.length === 1 ? "" : "s"}`
                  : "No linked reports"}
              </strong>
            </div>
            <StatusBadge condition={incidents?.features.length ? "unverified report" : "none"} />
          </div>
          <p>
            Public markers use coarsened locations. Exact locations, descriptions, contacts and
            media are withheld for private review.
          </p>
          <small>Reports do not confirm conditions and do not dispatch emergency services.</small>
        </section>
      )}

      {incidentProperties && (
        <div className="incident-warning" role="note">
          <span>Unverified community evidence</span>
          <strong>{incidentProperties.public_summary}</strong>
          <p>The point shown is deliberately coarsened; the exact submitted location is private.</p>
        </div>
      )}

      {stationProperties && latestObservation && (
        <div className="station-reading">
          <span>Latest published reading</span>
          <strong>
            {latestObservation.water_level_m.toFixed(3)} <small>{latestObservation.unit}</small>
          </strong>
          <p>
            Source time {latestObservation.source_observed_at} · timezone not published
          </p>
        </div>
      )}

      {stationProperties && stationObservations && (
        <StationSparkline series={stationObservations} />
      )}

      {weatherProperties && (
        <div className="station-reading weather-reading">
          <span>Next 24 hours · model guidance</span>
          <strong>
            {weatherProperties.precipitation_24h_mm.toFixed(1)} <small>mm</small>
          </strong>
          <p>
            Maximum hourly precipitation probability {weatherProperties.maximum_probability_pct == null
              ? "not available"
              : `${weatherProperties.maximum_probability_pct.toFixed(0)}%`}
          </p>
        </div>
      )}

      {warningProperties && (
        <div className={`warning-summary warning-summary--${warningProperties.severity}`}>
          <span>IMD day {warningProperties.day_index} warning</span>
          <strong>
            {asStringList(warningProperties.hazards).length > 0
              ? asStringList(warningProperties.hazards).join(" · ")
              : "No warning"}
          </strong>
          {warningProperties.description && <p>{warningProperties.description}</p>}
        </div>
      )}

      <dl className="detail-list">
        <DetailRow label="Record ID" value={properties.id || "Not supplied"} />
        {stationProperties && (
          <>
            <DetailRow label="Coverage" value="Incomplete public feed" />
            <DetailRow label="Timezone" value={stationProperties.time_zone || "Not published"} />
            <DetailRow
              label="Alert levels"
              value={
                stationProperties.warning_level_m == null &&
                stationProperties.danger_level_m == null
                  ? "Not published"
                  : "Partially configured"
              }
            />
          </>
        )}
        {weatherProperties && (
          <>
            <DetailRow label="Evidence class" value="Model-derived guidance" />
            <DetailRow label="Model" value={weatherProperties.model} />
            <DetailRow label="Forecast from" value={formatTimestamp(weatherProperties.forecast_from)} />
            <DetailRow label="Forecast through" value={formatTimestamp(weatherProperties.forecast_through)} />
          </>
        )}
        {warningProperties && (
          <>
            <DetailRow label="Evidence class" value="Official warning" />
            <DetailRow label="Issue time" value={formatTimestamp(warningProperties.issue_at)} />
            <DetailRow label="Valid date" value={warningProperties.valid_date} />
            <DetailRow label="IMD district ID" value={warningProperties.external_id} />
          </>
        )}
        {eventProperties && (
          <>
            <DetailRow label="Evidence class" value="Transparent rule output" />
            <DetailRow label="Started" value={formatTimestamp(eventProperties.started_at)} />
            <DetailRow label="State changed" value={formatTimestamp(eventProperties.state_changed_at)} />
            <DetailRow label="Rule version" value={eventProperties.rule_version} />
            <DetailRow label="Official warning" value={eventProperties.warning_status} />
            <DetailRow label="Rainfall" value={eventProperties.rainfall_status.replaceAll("_", " ")} />
            <DetailRow label="River evidence" value={eventProperties.river_status.replaceAll("_", " ")} />
            <DetailRow label="Satellite" value={eventProperties.satellite_status.replaceAll("_", " ")} />
          </>
        )}
        {extentProperties && (
          <>
            <DetailRow label="Evidence class" value="Satellite observed" />
            <DetailRow label="Acquired" value={formatTimestamp(extentProperties.acquired_at)} />
            <DetailRow label="Potential extent" value={`${extentProperties.area_km2.toFixed(2)} km²`} />
            <DetailRow label="High-evidence area" value={`${extentProperties.high_evidence_area_km2.toFixed(2)} km²`} />
            <DetailRow label="Valid coverage" value={`${(extentProperties.valid_coverage_fraction * 100).toFixed(1)}%`} />
            <DetailRow label="Resolution" value={`${extentProperties.resolution_m.toFixed(0)} m`} />
            <DetailRow label="Analysis CRS" value={extentProperties.analysis_crs} />
            <DetailRow label="Algorithm" value={`${extentProperties.algorithm} ${extentProperties.algorithm_version}`} />
          </>
        )}
        {disruptionProperties && (
          <>
            <DetailRow label="Evidence class" value="Model-derived screening" />
            <DetailRow label="Road class" value={disruptionProperties.road_class} />
            <DetailRow label="Overlap" value={`${disruptionProperties.overlap_km.toFixed(2)} km`} />
            <DetailRow label="Interpretation" value="Potentially affected; closure not confirmed" />
          </>
        )}
        {accessibilityProperties && (
          <>
            <DetailRow label="Evidence class" value="Model-derived reachability" />
            <DetailRow label="Potential isolation" value={accessibilityProperties.potentially_isolated ? "Yes — screening result" : "No"} />
            <DetailRow label="Major road access" value={accessibilityProperties.major_road_reachable_after ? "Reachable" : accessibilityProperties.major_road_reachable_before ? "Potentially disrupted" : "Not represented before event"} />
            <DetailRow label="Hospital access" value={accessibilityProperties.hospital_reachable_after ? "Reachable" : accessibilityProperties.hospital_reachable_before ? "Potentially disrupted" : "Not represented before event"} />
            <DetailRow label="Assessment" value={accessibilityProperties.assessment_status.replaceAll("_", " ")} />
          </>
        )}
        {incidentProperties && (
          <>
            <DetailRow label="Public reference" value={incidentProperties.public_reference} />
            <DetailRow label="Evidence class" value="Unverified public report" />
            <DetailRow label="Incident type" value={incidentProperties.incident_type.replaceAll("_", " ")} />
            <DetailRow
              label="People affected"
              value={
                incidentProperties.people_affected == null
                  ? "Not supplied"
                  : `${incidentProperties.people_count_approximate ? "Approximately " : ""}${incidentProperties.people_affected}`
              }
            />
            <DetailRow label="Reported" value={formatTimestamp(incidentProperties.reported_at)} />
            <DetailRow label="Location" value="Coarsened to approximately 1 km" />
            <DetailRow label="Review status" value={incidentProperties.verification_state} />
            <DetailRow label="Private media" value={incidentProperties.media_count ? "Retained for review; not public" : "None"} />
          </>
        )}
        <DetailRow label="Source" value={properties.source || "Not supplied"} />
        <DetailRow label="Source version" value={properties.source_version || "Not supplied"} />
        <DetailRow label="Ingested" value={formatTimestamp(properties.ingested_at)} />
      </dl>

      {eventProperties && eventEvidence && (
        <section className="event-detail-section" aria-labelledby="event-evidence-title">
          <h3 id="event-evidence-title">Evidence</h3>
          {eventEvidence.features.length > 0 ? (
            <ul className="event-evidence-list">
              {eventEvidence.features.map((feature) => (
                <li key={feature.properties.id}>
                  <div>
                    <strong>{feature.properties.name}</strong>
                    <StatusBadge condition={String(feature.properties.quality || "unrated")} />
                  </div>
                  <p>{feature.properties.summary}</p>
                  <small>
                    {feature.properties.source} · {formatTimestamp(feature.properties.ingested_at)}
                  </small>
                </li>
              ))}
            </ul>
          ) : (
            <p className="event-detail-empty">No evidence records are available.</p>
          )}
        </section>
      )}

      {eventProperties && eventTimeline && (
        <section className="event-detail-section" aria-labelledby="event-timeline-title">
          <h3 id="event-timeline-title">Timeline</h3>
          {eventTimeline.length > 0 ? (
            <ol className="event-timeline">
              {eventTimeline.map((entry) => (
                <li key={entry.id}>
                  <time dateTime={entry.occurred_at}>{formatTimestamp(entry.occurred_at)}</time>
                  <strong>{entry.category.replaceAll("_", " ")}</strong>
                  <p>{entry.summary}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="event-detail-empty">No timeline entries are available.</p>
          )}
        </section>
      )}

      {sourceUrl && (
        <a className="source-link" href={sourceUrl} target="_blank" rel="noreferrer">
          View source record <span aria-hidden="true">↗</span>
        </a>
      )}
    </section>
  );
}
