type IconName =
  | "alert"
  | "building"
  | "database"
  | "layers"
  | "map"
  | "pin"
  | "refresh"
  | "shield"
  | "signal";

interface IconProps {
  name: IconName;
  size?: number;
}

/** Small CSS-and-text icons keep the operational bundle free of an icon dependency. */
export function Icon({ name, size = 18 }: IconProps) {
  const glyph: Record<IconName, string> = {
    alert: "!",
    building: "▦",
    database: "≡",
    layers: "▱",
    map: "⌗",
    pin: "•",
    refresh: "↻",
    shield: "◇",
    signal: "⌁",
  };

  return (
    <span className={`icon icon--${name}`} style={{ "--icon-size": `${size}px` } as React.CSSProperties} aria-hidden="true">
      {glyph[name]}
    </span>
  );
}
