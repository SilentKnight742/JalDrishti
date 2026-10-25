import type { ServiceCondition } from "../types";

type BadgeTone = "positive" | "warning" | "danger" | "neutral" | "information";

const conditionTone = (condition: ServiceCondition): BadgeTone => {
  switch (condition.toLowerCase()) {
    case "ok":
    case "operational":
    case "available":
    case "healthy":
      return "positive";
    case "degraded":
    case "delayed":
    case "warning":
    case "watch":
      return "warning";
    case "severe":
    case "down":
    case "error":
    case "unavailable":
    case "failed":
      return "danger";
    case "recovery":
    case "model_derived":
      return "information";
    default:
      return "neutral";
  }
};

const humanise = (condition: string): string =>
  condition.replaceAll("_", " ").replace(/^./, (character) => character.toUpperCase());

interface StatusBadgeProps {
  condition: ServiceCondition;
  label?: string;
  tone?: BadgeTone;
  pulse?: boolean;
}

export function StatusBadge({ condition, label, tone, pulse = false }: StatusBadgeProps) {
  const resolvedTone = tone ?? conditionTone(condition);
  return (
    <span className={`status-badge status-badge--${resolvedTone}`}>
      <span className={pulse ? "status-badge__dot status-badge__dot--pulse" : "status-badge__dot"} />
      {label ?? humanise(condition)}
    </span>
  );
}
