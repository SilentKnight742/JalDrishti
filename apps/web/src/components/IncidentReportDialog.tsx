import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { submitIncidentReport } from "../lib/api";
import type { IncidentReceipt, IncidentType } from "../types";

interface IncidentReportDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmitted: (receipt: IncidentReceipt) => void;
}

interface CapturedLocation {
  latitude: number;
  longitude: number;
  accuracy: number | null;
}

const incidentOptions: Array<{ value: IncidentType; label: string }> = [
  { value: "stranded_people", label: "People stranded" },
  { value: "medical_emergency", label: "Medical emergency" },
  { value: "road_flooded", label: "Road flooded" },
  { value: "bridge_damage", label: "Bridge damage" },
  { value: "building_flooding", label: "Building flooding" },
  { value: "embankment_issue", label: "Embankment issue" },
  { value: "other", label: "Other flood incident" },
];

export function IncidentReportDialog({
  open,
  onClose,
  onSubmitted,
}: IncidentReportDialogProps) {
  const submissionId = useRef(crypto.randomUUID());
  const [location, setLocation] = useState<CapturedLocation | null>(null);
  const [locationState, setLocationState] = useState<"idle" | "locating" | "error">("idle");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<IncidentReceipt | null>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isSubmitting) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isSubmitting, onClose, open]);

  if (!open) return null;

  const captureLocation = () => {
    if (!("geolocation" in navigator)) {
      setLocationState("error");
      setError("This browser cannot provide a device location.");
      return;
    }
    setLocationState("locating");
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null,
        });
        setLocationState("idle");
      },
      () => {
        setLocationState("error");
        setError("Location permission was denied or a precise location could not be obtained.");
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 30_000 },
    );
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!location) {
      setError("Capture your device location before submitting.");
      return;
    }
    const body = new FormData(event.currentTarget);
    const photo = body.get("photo");
    if (photo instanceof File && photo.size === 0) body.delete("photo");
    body.set("people_count_approximate", body.has("people_count_approximate") ? "true" : "false");
    body.set("submission_id", submissionId.current);
    body.set("latitude", String(location.latitude));
    body.set("longitude", String(location.longitude));
    body.set("location_method", "gps");
    if (location.accuracy != null) body.set("location_accuracy_m", String(location.accuracy));
    body.set("privacy_consent", "true");
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await submitIncidentReport(body);
      setReceipt(result);
      onSubmitted(result);
      submissionId.current = crypto.randomUUID();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The report could not be submitted.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const close = () => {
    if (isSubmitting) return;
    setReceipt(null);
    setError(null);
    setLocation(null);
    setLocationState("idle");
    onClose();
  };

  return (
    <div className="incident-dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) close();
    }}>
      <section
        className="incident-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="incident-dialog-title"
      >
        <div className="incident-dialog__heading">
          <div>
            <span>Community reporting</span>
            <h2 id="incident-dialog-title">Report a flood incident</h2>
          </div>
          <button type="button" onClick={close} aria-label="Close incident report">Close</button>
        </div>

        {receipt ? (
          <div className="incident-receipt" role="status">
            <strong>Report received</strong>
            <p>{receipt.message}</p>
            <dl>
              <div><dt>Reference</dt><dd>{receipt.public_reference}</dd></div>
              <div><dt>Verification</dt><dd>{receipt.verification_state}</dd></div>
              <div><dt>Public location</dt><dd>{receipt.public_location_precision}</dd></div>
            </dl>
            <button type="button" onClick={close}>Done</button>
          </div>
        ) : (
          <form className="incident-form" onSubmit={(event) => void submit(event)}>
            <div className="incident-form__emergency" role="note">
              This does not dispatch emergency services. For immediate danger, call 112.
            </div>
            <label>
              Incident type
              <select name="incident_type" defaultValue="road_flooded" required>
                {incidentOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <div className="incident-form__row">
              <label>
                People affected
                <input name="people_affected" type="number" min="0" max="1000000" inputMode="numeric" />
              </label>
              <label className="incident-form__check">
                <input name="people_count_approximate" type="checkbox" value="true" defaultChecked />
                Count is approximate
              </label>
            </div>
            <label>
              What can be seen?
              <textarea name="description" minLength={5} maxLength={2000} rows={4} required />
              <small>This description is retained privately for review and is not shown on the public map.</small>
            </label>
            <div className="incident-form__location">
              <button type="button" onClick={captureLocation} disabled={locationState === "locating"}>
                {locationState === "locating" ? "Finding location…" : location ? "Refresh location" : "Use my device location"}
              </button>
              <span>
                {location
                  ? `Location captured${location.accuracy == null ? "" : ` · ±${Math.round(location.accuracy)} m`}`
                  : "Required. The public map receives only an approximately 1 km location."}
              </span>
            </div>
            <label>
              Photo <span>(optional)</span>
              <input name="photo" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" />
              <small>Maximum 8 MB. Metadata is removed; the image is kept private for review.</small>
            </label>
            <label>
              Contact detail <span>(optional)</span>
              <input name="contact" type="text" maxLength={240} autoComplete="tel" />
              <small>Encrypted at rest and never included in the public response.</small>
            </label>
            <label className="incident-form__check incident-form__consent">
              <input type="checkbox" required />
              I consent to JalDrishti storing the exact location and private report details for review.
            </label>
            {error && <p className="incident-form__error" role="alert">{error}</p>}
            <button className="incident-form__submit" type="submit" disabled={isSubmitting || !location}>
              {isSubmitting ? "Submitting securely…" : "Submit unverified report"}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
