export type FreshnessLevel = "current" | "delayed" | "stale" | "unknown";

export interface Freshness {
  level: FreshnessLevel;
  label: string;
  detail: string;
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export const relativeTime = (timestamp: string | null | undefined, now = new Date()): string => {
  if (!timestamp) return "No update recorded";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Invalid timestamp";

  const differenceSeconds = Math.round((date.getTime() - now.getTime()) / 1_000);
  const absoluteSeconds = Math.abs(differenceSeconds);
  if (absoluteSeconds < 60) return rtf.format(differenceSeconds, "second");

  const differenceMinutes = Math.round(differenceSeconds / 60);
  if (Math.abs(differenceMinutes) < 60) return rtf.format(differenceMinutes, "minute");

  const differenceHours = Math.round(differenceMinutes / 60);
  if (Math.abs(differenceHours) < 48) return rtf.format(differenceHours, "hour");

  return rtf.format(Math.round(differenceHours / 24), "day");
};

export const assessFreshness = (
  timestamp: string | null | undefined,
  now = new Date(),
): Freshness => {
  if (!timestamp) {
    return { level: "unknown", label: "Not reported", detail: "No source timestamp supplied" };
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return { level: "unknown", label: "Unknown", detail: "Source timestamp is invalid" };
  }

  const ageMinutes = Math.max(0, (now.getTime() - date.getTime()) / 60_000);
  const detail = `Updated ${relativeTime(timestamp, now)}`;
  if (ageMinutes <= 30) return { level: "current", label: "Current", detail };
  if (ageMinutes <= 120) return { level: "delayed", label: "Delayed", detail };
  return { level: "stale", label: "Stale", detail };
};

export const assessSourceFreshness = (
  status: string,
  timestamp: string | null | undefined,
  now = new Date(),
): Freshness => {
  if (!timestamp) {
    return { level: "unknown", label: "Not reported", detail: "No source timestamp supplied" };
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return { level: "unknown", label: "Unknown", detail: "Source timestamp is invalid" };
  }

  const detail = `Updated ${relativeTime(timestamp, now)}`;
  switch (status.toLowerCase()) {
    case "ok":
    case "healthy":
    case "available":
    case "operational":
      return { level: "current", label: "Current", detail };
    case "degraded":
    case "delayed":
      return { level: "delayed", label: "Delayed", detail };
    case "stale":
      return { level: "stale", label: "Stale", detail };
    case "failed":
    case "unavailable":
    case "not_configured":
      return { level: "unknown", label: "Unavailable", detail };
    default:
      return assessFreshness(timestamp, now);
  }
};

export const formatTimestamp = (timestamp: string | null | undefined): string => {
  if (!timestamp) return "Not available";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(date);
};
