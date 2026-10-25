import { assessSourceFreshness } from "../lib/freshness";
import type { SourceStatus } from "../types";
import { Icon } from "./Icon";
import { StatusBadge } from "./StatusBadge";

interface SourceMonitorProps {
  sources: SourceStatus[];
  isLoading: boolean;
  isUnavailable: boolean;
}

export function SourceMonitor({ sources, isLoading, isUnavailable }: SourceMonitorProps) {
  return (
    <section className="panel-section" aria-labelledby="source-monitor-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Source monitor</span>
          <h2 id="source-monitor-title">Evidence feeds</h2>
        </div>
        <Icon name="signal" />
      </div>

      {isLoading ? (
        <div className="source-stack" aria-live="polite" aria-busy="true">
          <div className="source-card source-card--skeleton" />
          <div className="source-card source-card--skeleton" />
        </div>
      ) : isUnavailable ? (
        <div className="empty-state empty-state--compact" role="status">
          <strong>Feed status unavailable</strong>
          <span>The map remains visible, but source freshness cannot be verified.</span>
        </div>
      ) : sources.length === 0 ? (
        <div className="empty-state empty-state--compact">
          <strong>No feeds registered</strong>
          <span>Live hydromet sources will appear here when ingestion is configured.</span>
        </div>
      ) : (
        <ul className="source-stack">
          {sources.map((source) => {
            const freshness = assessSourceFreshness(
              source.status,
              source.last_updated_at,
            );
            return (
              <li className="source-card" key={source.id}>
                <div className="source-card__topline">
                  <strong>{source.name}</strong>
                  <StatusBadge condition={source.status} />
                </div>
                <div className="source-card__freshness">
                  <span className={`freshness-dot freshness-dot--${freshness.level}`} />
                  <span>{freshness.detail}</span>
                </div>
                {source.detail && <p className="source-card__note">{source.detail}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
