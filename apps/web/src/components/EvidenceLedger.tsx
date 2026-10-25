import { Icon } from "./Icon";
import { StatusBadge } from "./StatusBadge";

interface EvidenceLedgerProps {
  hasRegions: boolean;
  hasDistricts: boolean;
  hasSettlements: boolean;
  hasRivers: boolean;
  hasFacilities: boolean;
  stationCount: number;
  weatherDistrictCount: number;
  activeWarningCount: number;
  activeEventCount: number;
}

export function EvidenceLedger({
  hasRegions,
  hasDistricts,
  hasSettlements,
  hasRivers,
  hasFacilities,
  stationCount,
  weatherDistrictCount,
  activeWarningCount,
  activeEventCount,
}: EvidenceLedgerProps) {
  const entries = [
    {
      title: "Rule-based flood events",
      detail:
        activeEventCount > 0
          ? `${activeEventCount} active district events with inspectable rules, evidence and timelines`
          : "No active event derived by the configured policy",
      available: activeEventCount > 0,
      status: activeEventCount > 0 ? "model_derived" : "pending",
      icon: "alert" as const,
    },
    {
      title: "Administrative extent",
      detail: "Region boundary served by the JalDrishti API",
      available: hasRegions,
      icon: "map" as const,
    },
    {
      title: "District geography",
      detail: "Canonical administrative features with provenance",
      available: hasDistricts,
      icon: "layers" as const,
    },
    {
      title: "Settlement context",
      detail: "Named cities and towns with source-linked population tags",
      available: hasSettlements,
      icon: "pin" as const,
    },
    {
      title: "River context",
      detail: "Selected major river backdrop; not a flow-network model",
      available: hasRivers,
      icon: "map" as const,
    },
    {
      title: "Critical facilities",
      detail: "Reference locations; operational status not yet assessed",
      available: hasFacilities,
      icon: "building" as const,
    },
    {
      title: "River-level telemetry",
      detail:
        stationCount > 0
          ? `${stationCount} pilot station; incomplete coverage and no alert thresholds`
          : "Pilot feed not ingested",
      available: stationCount > 0,
      status: stationCount > 0 ? "pilot" : "pending",
      icon: "signal" as const,
    },
    {
      title: "Official weather warnings",
      detail:
        activeWarningCount > 0
          ? `${activeWarningCount} districts have a non-green IMD day-one warning`
          : "IMD day-one warning layer loaded; no non-green warnings",
      available: activeWarningCount > 0 || weatherDistrictCount > 0,
      icon: "alert" as const,
    },
    {
      title: "Rainfall model guidance",
      detail:
        weatherDistrictCount > 0
          ? `${weatherDistrictCount} district representative points; model-derived, not observed rainfall`
          : "Forecast guidance not ingested",
      available: weatherDistrictCount > 0,
      status: weatherDistrictCount > 0 ? "model_derived" : "pending",
      icon: "signal" as const,
    },
  ];

  return (
    <section className="evidence-ledger" aria-labelledby="evidence-ledger-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Evidence ledger</span>
          <h2 id="evidence-ledger-title">What this map can support</h2>
        </div>
        <Icon name="shield" />
      </div>
      <p className="section-intro">
        Every visible operational claim must retain its source, quality and time context.
      </p>
      <ul className="ledger-list">
        {entries.map((entry) => (
          <li key={entry.title}>
            <span className="ledger-list__icon"><Icon name={entry.icon} /></span>
            <span className="ledger-list__copy">
              <strong>{entry.title}</strong>
              <small>{entry.detail}</small>
            </span>
            <StatusBadge
              condition={entry.status ?? (entry.available ? "available" : "pending")}
              label={entry.status === "pilot" ? "Pilot" : entry.available ? "Available" : "Pending"}
            />
          </li>
        ))}
      </ul>
      <div className="method-note">
        <span className="method-note__mark">i</span>
        <p>
          <strong>Foundation mode</strong>
          Official warnings remain distinct from model guidance. Pilot telemetry is evidence, not a flood warning; statewide gauge coverage and thresholds remain unverified.
        </p>
      </div>
    </section>
  );
}
