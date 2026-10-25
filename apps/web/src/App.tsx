import { lazy, Suspense, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brand } from "./components/Brand";
import { EvidenceLedger } from "./components/EvidenceLedger";
import { Icon } from "./components/Icon";
import { IncidentReportDialog } from "./components/IncidentReportDialog";
import { SelectionInspector } from "./components/SelectionInspector";
import { SourceMonitor } from "./components/SourceMonitor";
import { StatusBadge } from "./components/StatusBadge";
import {
  getEventAccessibility,
  getDistrict,
  getDistricts,
  getEventEvidence,
  getEventImpact,
  getEventIncidents,
  getEvents,
  getEventTimeline,
  getFloodExtents,
  getFacilities,
  getRegions,
  getRivers,
  getSettlements,
  getSatelliteJobs,
  getSatelliteComparisons,
  getStationObservations,
  getStations,
  getStatus,
  getWarnings,
  getWeatherForecasts,
  requestSatelliteObservation,
} from "./lib/api";
import { relativeTime } from "./lib/freshness";
import type { GeographyProperties, SelectedMapFeature } from "./types";

const QUERY_TIMINGS = {
  status: 15_000,
  geography: 5 * 60_000,
  telemetry: 60_000,
  weather: 5 * 60_000,
  events: 15_000,
};

const OperationalMap = lazy(async () => {
  const module = await import("./components/OperationalMap");
  return { default: module.OperationalMap };
});

const sourceIsAvailable = (status: string): boolean =>
  ["ok", "operational", "available", "healthy"].includes(status.toLowerCase());

function App() {
  const [selection, setSelection] = useState<SelectedMapFeature | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: ["system-status"],
    queryFn: ({ signal }) => getStatus(signal),
    staleTime: QUERY_TIMINGS.status,
    refetchInterval: 30_000,
    retry: 2,
  });
  const regionsQuery = useQuery({
    queryKey: ["regions"],
    queryFn: ({ signal }) => getRegions(signal),
    staleTime: QUERY_TIMINGS.geography,
  });
  const districtsQuery = useQuery({
    queryKey: ["districts", "assam"],
    queryFn: ({ signal }) => getDistricts(signal),
    staleTime: QUERY_TIMINGS.geography,
  });
  const facilitiesQuery = useQuery({
    queryKey: ["facilities", "assam"],
    queryFn: ({ signal }) => getFacilities(signal),
    staleTime: QUERY_TIMINGS.geography,
  });
  const settlementsQuery = useQuery({
    queryKey: ["settlements", "assam"],
    queryFn: ({ signal }) => getSettlements(signal),
    staleTime: QUERY_TIMINGS.geography,
  });
  const riversQuery = useQuery({
    queryKey: ["rivers", "assam"],
    queryFn: ({ signal }) => getRivers(signal),
    staleTime: QUERY_TIMINGS.geography,
  });
  const stationsQuery = useQuery({
    queryKey: ["stations", "assam"],
    queryFn: ({ signal }) => getStations(signal),
    staleTime: QUERY_TIMINGS.telemetry,
    refetchInterval: 5 * 60_000,
  });
  const weatherQuery = useQuery({
    queryKey: ["weather-forecast", "assam", 24],
    queryFn: ({ signal }) => getWeatherForecasts(signal),
    staleTime: QUERY_TIMINGS.weather,
    refetchInterval: 15 * 60_000,
  });
  const warningsQuery = useQuery({
    queryKey: ["warnings", "assam", 1],
    queryFn: ({ signal }) => getWarnings(signal),
    staleTime: QUERY_TIMINGS.weather,
    refetchInterval: 5 * 60_000,
  });
  const eventsQuery = useQuery({
    queryKey: ["events", "assam"],
    queryFn: ({ signal }) => getEvents(signal),
    staleTime: QUERY_TIMINGS.events,
    refetchInterval: 30_000,
  });

  const selectedDistrictId = selection?.kind === "district" ? selection.properties.id : null;
  const districtDetailQuery = useQuery({
    queryKey: ["district", selectedDistrictId],
    queryFn: ({ signal }) => getDistrict(selectedDistrictId!, signal),
    enabled: Boolean(selectedDistrictId),
    staleTime: QUERY_TIMINGS.geography,
  });
  const selectedStationId = selection?.kind === "station" ? selection.properties.id : null;
  const stationObservationsQuery = useQuery({
    queryKey: ["station-observations", selectedStationId],
    queryFn: ({ signal }) => getStationObservations(selectedStationId!, signal),
    enabled: Boolean(selectedStationId),
    staleTime: QUERY_TIMINGS.telemetry,
    refetchInterval: selectedStationId ? 5 * 60_000 : false,
  });
  const selectedEventId =
    selection?.kind === "event"
      ? selection.properties.id
      : selection?.kind === "extent"
        ? selection.properties.event_id
        : selection?.kind === "road_disruption" || selection?.kind === "accessibility" || selection?.kind === "incident"
          ? selection.properties.event_id
        : null;
  const eventEvidenceQuery = useQuery({
    queryKey: ["event-evidence", selectedEventId],
    queryFn: ({ signal }) => getEventEvidence(selectedEventId!, signal),
    enabled: Boolean(selectedEventId),
    staleTime: QUERY_TIMINGS.events,
  });
  const eventTimelineQuery = useQuery({
    queryKey: ["event-timeline", selectedEventId],
    queryFn: ({ signal }) => getEventTimeline(selectedEventId!, signal),
    enabled: Boolean(selectedEventId),
    staleTime: QUERY_TIMINGS.events,
  });
  const satelliteJobsQuery = useQuery({
    queryKey: ["satellite-jobs", selectedEventId],
    queryFn: ({ signal }) => getSatelliteJobs(selectedEventId!, signal),
    enabled: Boolean(selectedEventId),
    staleTime: 5_000,
    refetchInterval: selectedEventId ? 10_000 : false,
  });
  const floodExtentsQuery = useQuery({
    queryKey: ["flood-extents", selectedEventId],
    queryFn: ({ signal }) => getFloodExtents(selectedEventId!, signal),
    enabled: Boolean(selectedEventId),
    staleTime: QUERY_TIMINGS.events,
    refetchInterval: selectedEventId ? 15_000 : false,
  });
  const satelliteComparisonsQuery = useQuery({
    queryKey: ["satellite-comparisons", selectedEventId],
    queryFn: ({ signal }) => getSatelliteComparisons(selectedEventId!, signal),
    enabled: Boolean(selectedEventId),
    staleTime: QUERY_TIMINGS.events,
  });
  const impactQuery = useQuery({
    queryKey: ["event-impact", selectedEventId],
    queryFn: ({ signal }) => getEventImpact(selectedEventId!, signal),
    enabled: Boolean(selectedEventId),
    staleTime: QUERY_TIMINGS.events,
    refetchInterval: selectedEventId ? 15_000 : false,
  });
  const accessibilityQuery = useQuery({
    queryKey: ["event-accessibility", selectedEventId],
    queryFn: ({ signal }) => getEventAccessibility(selectedEventId!, signal),
    enabled: Boolean(selectedEventId),
    staleTime: QUERY_TIMINGS.events,
    refetchInterval: selectedEventId ? 15_000 : false,
  });
  const incidentsQuery = useQuery({
    queryKey: ["event-incidents", selectedEventId],
    queryFn: ({ signal }) => getEventIncidents(selectedEventId!, signal),
    enabled: Boolean(selectedEventId),
    staleTime: QUERY_TIMINGS.events,
    refetchInterval: selectedEventId ? 30_000 : false,
  });
  const satelliteMutation = useMutation({
    mutationFn: (eventId: string) => requestSatelliteObservation(eventId),
    onSuccess: async (job) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["satellite-jobs", job.event_id] }),
        queryClient.invalidateQueries({ queryKey: ["events", "assam"] }),
        queryClient.invalidateQueries({ queryKey: ["event-timeline", job.event_id] }),
        queryClient.invalidateQueries({ queryKey: ["event-impact", job.event_id] }),
      ]);
    },
  });

  const geographyLoading =
    regionsQuery.isPending ||
    districtsQuery.isPending ||
    settlementsQuery.isPending ||
    riversQuery.isPending ||
    facilitiesQuery.isPending;
  const geographyError =
    regionsQuery.isError ||
    districtsQuery.isError ||
    settlementsQuery.isError ||
    riversQuery.isError ||
    facilitiesQuery.isError;
  const availableSources = useMemo(
    () => statusQuery.data?.sources.filter((source) => sourceIsAvailable(source.status)).length ?? 0,
    [statusQuery.data?.sources],
  );

  const retryGeography = () => {
    void Promise.all([
      regionsQuery.refetch(),
      districtsQuery.refetch(),
      settlementsQuery.refetch(),
      riversQuery.refetch(),
      facilitiesQuery.refetch(),
      stationsQuery.refetch(),
      weatherQuery.refetch(),
      warningsQuery.refetch(),
      eventsQuery.refetch(),
    ]);
  };

  const districtDetail = districtDetailQuery.data?.properties as GeographyProperties | undefined;
  const systemCondition = statusQuery.isError ? "unavailable" : statusQuery.data?.status ?? "connecting";
  const regionName = regionsQuery.data?.features[0]?.properties?.name ?? "Assam";
  const stationCount = stationsQuery.data?.features.length ?? 0;
  const weatherDistrictCount = weatherQuery.data?.features.length ?? 0;
  const activeWarningCount =
    warningsQuery.data?.features.filter((feature) => feature.properties.severity !== "green")
      .length ?? 0;
  const activeEventCount = eventsQuery.data?.features.length ?? 0;

  return (
    <div className="app-shell">
      <header className="topbar">
        <Brand />
        <div className="topbar__context" aria-label="Current operational context">
          <button className="report-incident-button" type="button" onClick={() => setReportOpen(true)}>
            <Icon name="alert" /> Report incident
          </button>
          <span className="context-location"><Icon name="pin" /> {regionName}, India</span>
          <span className="topbar__divider" aria-hidden="true" />
          <div className="service-state">
            <StatusBadge
              condition={systemCondition}
              label={systemCondition === "ok" ? "System connected" : undefined}
              pulse={systemCondition === "ok"}
            />
            <small>
              {statusQuery.data?.checked_at
                ? `Checked ${relativeTime(statusQuery.data.checked_at)}`
                : statusQuery.isPending
                  ? "Verifying service"
                  : "Status not verified"}
            </small>
          </div>
        </div>
      </header>

      {statusQuery.isError && (
        <div className="availability-banner" role="alert">
          <Icon name="alert" />
          <span>
            <strong>Live service status is unavailable.</strong> Geography may be incomplete and freshness cannot be confirmed.
          </span>
          <button type="button" onClick={() => void statusQuery.refetch()}>
            <Icon name="refresh" /> Retry
          </button>
        </div>
      )}

      <main id="main-content" className="workspace">
        <aside className="left-rail" aria-label="Situation overview">
          <section className="situation-panel" aria-labelledby="situation-title">
            <span className="eyebrow">Situation overview</span>
            <div className="situation-panel__title-row">
              <div>
                <h2 id="situation-title">Assam at a glance</h2>
                <p>Verified geographic context for flood intelligence operations.</p>
              </div>
              <span className="foundation-seal">
                {activeEventCount > 0 ? "P4" : weatherDistrictCount > 0 || warningsQuery.data?.features.length ? "P3" : stationCount > 0 ? "P2" : "P1"}
              </span>
            </div>

            <div className="metric-grid" aria-label="Loaded geographic records">
              <article className="metric-card metric-card--event">
                <span className="metric-card__icon metric-card__icon--warm"><Icon name="alert" /></span>
                <div>
                  <strong>{eventsQuery.isError ? "—" : activeEventCount}</strong>
                  <span>Active rule-based events</span>
                </div>
              </article>
              <article className="metric-card">
                <span className="metric-card__icon"><Icon name="layers" /></span>
                <div>
                  <strong>{districtsQuery.data?.features.length ?? "—"}</strong>
                  <span>Districts mapped</span>
                </div>
              </article>
              <article className="metric-card">
                <span className="metric-card__icon metric-card__icon--warm"><Icon name="alert" /></span>
                <div>
                  <strong>{warningsQuery.isError ? "—" : activeWarningCount}</strong>
                  <span>Active IMD warnings</span>
                </div>
              </article>
              <article className="metric-card">
                <span className="metric-card__icon"><Icon name="signal" /></span>
                <div>
                  <strong>{weatherQuery.isError ? "—" : weatherDistrictCount}</strong>
                  <span>Rainfall guidance districts</span>
                </div>
              </article>
              <article className="metric-card">
                <span className="metric-card__icon metric-card__icon--warm"><Icon name="signal" /></span>
                <div>
                  <strong>{stationsQuery.isError ? "—" : stationCount}</strong>
                  <span>Gauge stations in pilot</span>
                </div>
              </article>
              <article className="metric-card">
                <span className="metric-card__icon metric-card__icon--warm"><Icon name="building" /></span>
                <div>
                  <strong>{facilitiesQuery.data?.features.length ?? "—"}</strong>
                  <span>Facilities indexed</span>
                </div>
              </article>
              <article className="metric-card">
                <span className="metric-card__icon"><Icon name="pin" /></span>
                <div>
                  <strong>{settlementsQuery.data?.features.length ?? "—"}</strong>
                  <span>Settlements indexed</span>
                </div>
              </article>
              <article className="metric-card">
                <span className="metric-card__icon"><Icon name="map" /></span>
                <div>
                  <strong>{riversQuery.data?.features.length ?? "—"}</strong>
                  <span>Major rivers traced</span>
                </div>
              </article>
              <article className="metric-card metric-card--wide">
                <span className="metric-card__icon metric-card__icon--dark"><Icon name="signal" /></span>
                <div>
                  <strong>{availableSources}</strong>
                  <span>Evidence feeds available</span>
                </div>
                <small>of {statusQuery.data?.sources.length ?? 0} registered</small>
              </article>
            </div>

            <div className="scope-note">
              <span className="scope-note__label">Current scope</span>
              <p>
                {activeEventCount > 0
                  ? "Transparent rules have created active district events from official IMD warnings. Model rainfall is supporting evidence only; severe state remains unavailable without satellite inundation and exposure evidence."
                  : weatherDistrictCount > 0 || warningsQuery.data?.features.length
                    ? "Official IMD district warnings and model-derived rainfall guidance are visible. River telemetry remains a one-station pilot without alert thresholds."
                  : stationCount > 0
                    ? "Pilot river-level observations are visible, but coverage is incomplete and no warning thresholds are configured."
                  : "Geospatial foundation only. No flood warning, exposure or incident claim is active in this view."}
              </p>
            </div>
          </section>

          <SourceMonitor
            sources={statusQuery.data?.sources ?? []}
            isLoading={statusQuery.isPending}
            isUnavailable={statusQuery.isError}
          />

          <section className="dependency-strip" aria-label="Platform dependencies">
            <span>Platform</span>
            <ul>
              <li>
                <span className={`dependency-dot dependency-dot--${statusQuery.data?.dependencies.database.status ?? "unknown"}`} />
                Database
              </li>
              <li>
                <span className={`dependency-dot dependency-dot--${statusQuery.data?.dependencies.redis.status ?? "unknown"}`} />
                Queue
              </li>
            </ul>
          </section>
        </aside>

        <Suspense
          fallback={
            <section className="map-shell map-shell--module-loading" aria-label="Loading interactive map">
              <span className="loader" />
              <strong>Preparing the operational map</strong>
            </section>
          }
        >
          <OperationalMap
            regions={regionsQuery.data}
            districts={districtsQuery.data}
            settlements={settlementsQuery.data}
            rivers={riversQuery.data}
            facilities={facilitiesQuery.data}
            stations={stationsQuery.data}
            weather={weatherQuery.data}
            warnings={warningsQuery.data}
            events={eventsQuery.data}
            floodExtents={floodExtentsQuery.data}
            accessibility={accessibilityQuery.data}
            incidents={incidentsQuery.data}
            isLoading={geographyLoading}
            hasError={geographyError}
            onRetry={retryGeography}
            selection={selection}
            onSelect={setSelection}
          />
        </Suspense>

        <aside className="right-rail" aria-label="Evidence detail">
          <SelectionInspector
            selection={selection}
            districtDetail={districtDetail}
            isDetailLoading={districtDetailQuery.isFetching}
            stationObservations={stationObservationsQuery.data}
            isStationDetailLoading={stationObservationsQuery.isFetching}
            hasStationDetailError={stationObservationsQuery.isError}
            eventEvidence={eventEvidenceQuery.data}
            eventTimeline={eventTimelineQuery.data}
            satelliteJobs={satelliteJobsQuery.data}
            floodExtents={floodExtentsQuery.data}
            satelliteComparisons={satelliteComparisonsQuery.data}
            impact={impactQuery.data}
            accessibility={accessibilityQuery.data}
            incidents={incidentsQuery.data}
            isEventDetailLoading={eventEvidenceQuery.isFetching || eventTimelineQuery.isFetching || satelliteJobsQuery.isFetching || floodExtentsQuery.isFetching || satelliteComparisonsQuery.isFetching || impactQuery.isFetching || accessibilityQuery.isFetching || incidentsQuery.isFetching}
            hasEventDetailError={eventEvidenceQuery.isError || eventTimelineQuery.isError || satelliteJobsQuery.isError || floodExtentsQuery.isError || satelliteComparisonsQuery.isError || impactQuery.isError || accessibilityQuery.isError || incidentsQuery.isError}
            isRequestingSatellite={satelliteMutation.isPending}
            satelliteRequestError={satelliteMutation.isError}
            onRequestSatellite={() => {
              if (selectedEventId) satelliteMutation.mutate(selectedEventId);
            }}
            onClear={() => setSelection(null)}
          />
          <EvidenceLedger
            hasRegions={Boolean(regionsQuery.data?.features.length)}
            hasDistricts={Boolean(districtsQuery.data?.features.length)}
            hasSettlements={Boolean(settlementsQuery.data?.features.length)}
            hasRivers={Boolean(riversQuery.data?.features.length)}
            hasFacilities={Boolean(facilitiesQuery.data?.features.length)}
            stationCount={stationCount}
            weatherDistrictCount={weatherDistrictCount}
            activeWarningCount={activeWarningCount}
            activeEventCount={activeEventCount}
          />
        </aside>
      </main>

      <footer className="footer-bar">
        <span><strong>JalDrishti</strong> · Evidence before inference</span>
        <span>
          API {statusQuery.data?.version ?? "—"} · {statusQuery.data?.service ?? "service unverified"}
        </span>
      </footer>
      <IncidentReportDialog
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        onSubmitted={(receipt) => {
          if (!receipt.event_id) return;
          const linkedEvent = eventsQuery.data?.features.find(
            (feature) => feature.properties.id === receipt.event_id,
          );
          if (linkedEvent) {
            setSelection({ kind: "event", properties: linkedEvent.properties });
          }
          void Promise.all([
            queryClient.invalidateQueries({ queryKey: ["event-incidents", receipt.event_id] }),
            queryClient.invalidateQueries({ queryKey: ["event-evidence", receipt.event_id] }),
            queryClient.invalidateQueries({ queryKey: ["event-timeline", receipt.event_id] }),
          ]);
        }}
      />
    </div>
  );
}

export default App;
