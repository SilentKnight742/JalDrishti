import type { Geometry, Position } from "geojson";
import type {
  AccessibilityResponse,
  EventProperties,
  FacilityProperties,
  FloodExtentProperties,
  GeographyCollection,
  IncidentProperties,
  RiverProperties,
  SelectedMapFeature,
  SettlementProperties,
  StationProperties,
  WarningProperties,
  WeatherSummaryProperties,
} from "../types";

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 560;
const VIEW_PADDING = 26;
const DEFAULT_BOUNDS: MapBounds = {
  minLongitude: 89.6,
  minLatitude: 24,
  maxLongitude: 96.1,
  maxLatitude: 28.3,
};

export interface MapBounds {
  minLongitude: number;
  minLatitude: number;
  maxLongitude: number;
  maxLatitude: number;
}

interface StaticGeographyMapProps {
  regions: GeographyCollection;
  districts: GeographyCollection;
  settlements: GeographyCollection<SettlementProperties>;
  rivers: GeographyCollection<RiverProperties>;
  stations: GeographyCollection<StationProperties>;
  facilities: GeographyCollection<FacilityProperties>;
  weather: GeographyCollection<WeatherSummaryProperties>;
  warnings: GeographyCollection<WarningProperties>;
  events: GeographyCollection<EventProperties>;
  floodExtents?: GeographyCollection<FloodExtentProperties>;
  accessibility?: AccessibilityResponse;
  incidents?: GeographyCollection<IncidentProperties>;
  visibleLayers: {
    districts: boolean;
    rivers: boolean;
    settlements: boolean;
    stations: boolean;
    facilities: boolean;
    weather: boolean;
    warnings: boolean;
    events: boolean;
    extents?: boolean;
    disruptions?: boolean;
    accessibility?: boolean;
    incidents?: boolean;
  };
  onSelect: (feature: SelectedMapFeature) => void;
  focusGeometry?: Geometry | null;
  selectedRecord?: SelectedMapFeature | null;
}

export const positionsFromGeometry = (geometry: Geometry): Position[] => {
  if (geometry.type === "GeometryCollection") {
    return geometry.geometries.flatMap(positionsFromGeometry);
  }

  const positions: Position[] = [];
  const walk = (coordinates: unknown): void => {
    if (!Array.isArray(coordinates)) return;
    if (
      coordinates.length >= 2 &&
      typeof coordinates[0] === "number" &&
      typeof coordinates[1] === "number"
    ) {
      positions.push(coordinates as Position);
      return;
    }
    coordinates.forEach(walk);
  };

  walk(geometry.coordinates);
  return positions;
};

export const boundsFromGeometries = (geometries: Geometry[]): MapBounds => {
  const positions = geometries.flatMap(positionsFromGeometry).filter(
    ([longitude, latitude]) => Number.isFinite(longitude) && Number.isFinite(latitude),
  );
  if (positions.length === 0) return DEFAULT_BOUNDS;

  const longitudes = positions.map(([longitude]) => longitude);
  const latitudes = positions.map(([, latitude]) => latitude);
  const minLongitude = Math.min(...longitudes);
  const maxLongitude = Math.max(...longitudes);
  const minLatitude = Math.min(...latitudes);
  const maxLatitude = Math.max(...latitudes);

  if (minLongitude === maxLongitude || minLatitude === maxLatitude) return DEFAULT_BOUNDS;
  return { minLongitude, minLatitude, maxLongitude, maxLatitude };
};

export const projectPosition = (position: Position, bounds: MapBounds): [number, number] => {
  const longitudeRange = bounds.maxLongitude - bounds.minLongitude;
  const latitudeRange = bounds.maxLatitude - bounds.minLatitude;
  const drawableWidth = VIEW_WIDTH - VIEW_PADDING * 2;
  const drawableHeight = VIEW_HEIGHT - VIEW_PADDING * 2;
  const x =
    VIEW_PADDING + ((position[0] - bounds.minLongitude) / longitudeRange) * drawableWidth;
  const y =
    VIEW_PADDING + ((bounds.maxLatitude - position[1]) / latitudeRange) * drawableHeight;
  return [x, y];
};

const linePath = (positions: Position[], bounds: MapBounds, close = false): string => {
  if (positions.length === 0) return "";
  const commands = positions.map((position, index) => {
    const [x, y] = projectPosition(position, bounds);
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  return `${commands.join(" ")}${close ? " Z" : ""}`;
};

export const geometryToSvgPath = (geometry: Geometry, bounds: MapBounds): string => {
  switch (geometry.type) {
    case "LineString":
      return linePath(geometry.coordinates, bounds);
    case "MultiLineString":
      return geometry.coordinates.map((line) => linePath(line, bounds)).join(" ");
    case "Polygon":
      return geometry.coordinates.map((ring) => linePath(ring, bounds, true)).join(" ");
    case "MultiPolygon":
      return geometry.coordinates
        .flatMap((polygon) => polygon.map((ring) => linePath(ring, bounds, true)))
        .join(" ");
    case "GeometryCollection":
      return geometry.geometries.map((part) => geometryToSvgPath(part, bounds)).join(" ");
    default:
      return "";
  }
};

export const focusBoundsFromGeometry = (
  geometry: Geometry,
  fullBounds: MapBounds,
): MapBounds => {
  const positions = positionsFromGeometry(geometry).filter(
    ([longitude, latitude]) => Number.isFinite(longitude) && Number.isFinite(latitude),
  );
  if (positions.length === 0) return fullBounds;

  const longitudes = positions.map(([longitude]) => longitude);
  const latitudes = positions.map(([, latitude]) => latitude);
  const rawMinLongitude = Math.min(...longitudes);
  const rawMaxLongitude = Math.max(...longitudes);
  const rawMinLatitude = Math.min(...latitudes);
  const rawMaxLatitude = Math.max(...latitudes);
  const fullLongitudeSpan = fullBounds.maxLongitude - fullBounds.minLongitude;
  const fullLatitudeSpan = fullBounds.maxLatitude - fullBounds.minLatitude;
  const longitudeSpan = Math.min(
    Math.max((rawMaxLongitude - rawMinLongitude) * 1.3, 0.5),
    fullLongitudeSpan,
  );
  const latitudeSpan = Math.min(
    Math.max((rawMaxLatitude - rawMinLatitude) * 1.3, 0.32),
    fullLatitudeSpan,
  );
  const centerLongitude = (rawMinLongitude + rawMaxLongitude) / 2;
  const centerLatitude = (rawMinLatitude + rawMaxLatitude) / 2;
  const minLongitude = Math.min(
    Math.max(centerLongitude - longitudeSpan / 2, fullBounds.minLongitude),
    fullBounds.maxLongitude - longitudeSpan,
  );
  const minLatitude = Math.min(
    Math.max(centerLatitude - latitudeSpan / 2, fullBounds.minLatitude),
    fullBounds.maxLatitude - latitudeSpan,
  );
  return {
    minLongitude,
    minLatitude,
    maxLongitude: minLongitude + longitudeSpan,
    maxLatitude: minLatitude + latitudeSpan,
  };
};

const pointPositions = (geometry: Geometry): Position[] => {
  if (geometry.type === "Point") return [geometry.coordinates];
  if (geometry.type === "MultiPoint") return geometry.coordinates;
  if (geometry.type === "GeometryCollection") {
    return geometry.geometries.flatMap(pointPositions);
  }
  return [];
};

export function StaticGeographyMap({
  regions,
  districts,
  settlements,
  rivers,
  stations,
  facilities,
  weather,
  warnings,
  events,
  floodExtents = { type: "FeatureCollection", features: [] },
  accessibility,
  incidents = { type: "FeatureCollection", features: [] },
  visibleLayers,
  onSelect,
  focusGeometry = null,
  selectedRecord = null,
}: StaticGeographyMapProps) {
  const bounds = boundsFromGeometries(
    (districts.features.length > 0 ? districts.features : regions.features)
      .map((feature) => feature.geometry)
      .filter((geometry): geometry is Geometry => geometry !== null),
  );
  const renderBounds = focusGeometry
    ? focusBoundsFromGeometry(focusGeometry, bounds)
    : bounds;
  const isSelected = (kind: SelectedMapFeature["kind"], id: string) =>
    selectedRecord?.kind === kind && selectedRecord.properties.id === id;

  return (
    <div className="static-map" data-testid="static-geography-map">
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        data-focused={focusGeometry ? "true" : "false"}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Compatibility map of Assam flood events, warnings, unverified public reports, rainfall guidance, districts, rivers, settlements, gauge stations and facilities"
      >
        <title>Assam operational geography</title>
        <defs>
          <pattern id="static-map-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" className="static-map__grid" />
          </pattern>
        </defs>
        <rect width={VIEW_WIDTH} height={VIEW_HEIGHT} className="static-map__background" />
        <rect width={VIEW_WIDTH} height={VIEW_HEIGHT} fill="url(#static-map-grid)" />

        <g className="static-map__regions">
          {regions.features.map((feature) => (
            <path
              key={feature.properties.id}
              d={geometryToSvgPath(feature.geometry, renderBounds)}
              fillRule="evenodd"
            />
          ))}
        </g>

        {visibleLayers.districts && (
          <g className="static-map__districts">
            {districts.features.map((feature) => (
              <path
                key={feature.properties.id}
                className={isSelected("district", feature.properties.id) ? "is-selected" : undefined}
                d={geometryToSvgPath(feature.geometry, renderBounds)}
                fillRule="evenodd"
                onClick={() => onSelect({ kind: "district", properties: feature.properties })}
              >
                <title>{feature.properties.name}</title>
              </path>
            ))}
          </g>
        )}

        {visibleLayers.warnings && (
          <g className="static-map__warnings">
            {warnings.features
              .filter((feature) => feature.properties.severity !== "green")
              .map((feature) => (
                <path
                  key={feature.properties.id}
                  className={`static-map__warning static-map__warning--${feature.properties.severity}${
                    isSelected("warning", feature.properties.id) ? " is-selected" : ""
                  }`}
                  d={geometryToSvgPath(feature.geometry, renderBounds)}
                  fillRule="evenodd"
                  onClick={() =>
                    onSelect({ kind: "warning", properties: feature.properties })
                  }
                >
                  <title>{feature.properties.name}</title>
                </path>
              ))}
          </g>
        )}

        {visibleLayers.events && (
          <g className="static-map__events">
            {events.features.map((feature) => (
              <path
                key={feature.properties.id}
                className={`static-map__event static-map__event--${feature.properties.state}${
                  isSelected("event", feature.properties.id) ? " is-selected" : ""
                }`}
                d={geometryToSvgPath(feature.geometry, renderBounds)}
                fillRule="evenodd"
                onClick={() => onSelect({ kind: "event", properties: feature.properties })}
              >
                <title>{feature.properties.name}</title>
              </path>
            ))}
          </g>
        )}

        {visibleLayers.incidents && (
          <g className="static-map__incidents">
            {incidents.features.flatMap((feature) =>
              pointPositions(feature.geometry).map((position, index) => {
                const [cx, cy] = projectPosition(position, renderBounds);
                return (
                  <circle
                    key={`${feature.properties.id}:${index}`}
                    className={isSelected("incident", feature.properties.id) ? "is-selected" : undefined}
                    cx={cx}
                    cy={cy}
                    r="7"
                    onClick={() => onSelect({ kind: "incident", properties: feature.properties })}
                  >
                    <title>{feature.properties.public_summary}</title>
                  </circle>
                );
              }),
            )}
          </g>
        )}

        {visibleLayers.extents && (
          <g className="static-map__extents">
            {floodExtents.features.map((feature) => (
              <path
                key={feature.properties.id}
                className={isSelected("extent", feature.properties.id) ? "is-selected" : undefined}
                d={geometryToSvgPath(feature.geometry, renderBounds)}
                fillRule="evenodd"
                onClick={() => onSelect({ kind: "extent", properties: feature.properties })}
              >
                <title>{feature.properties.name}</title>
              </path>
            ))}
          </g>
        )}

        {visibleLayers.disruptions && (
          <g className="static-map__disruptions">
            {accessibility?.road_disruptions.features.map((feature) => (
              <path
                key={feature.properties.id}
                className={
                  isSelected("road_disruption", feature.properties.id) ? "is-selected" : undefined
                }
                d={geometryToSvgPath(feature.geometry, renderBounds)}
                onClick={() =>
                  onSelect({ kind: "road_disruption", properties: feature.properties })
                }
              >
                <title>{feature.properties.name}</title>
              </path>
            ))}
          </g>
        )}

        {visibleLayers.accessibility && (
          <g className="static-map__accessibility">
            {accessibility?.settlements.features.flatMap((feature) =>
              pointPositions(feature.geometry).map((position, index) => {
                const [cx, cy] = projectPosition(position, renderBounds);
                return (
                  <circle
                    key={`${feature.properties.id}:${index}`}
                    className={`${feature.properties.potentially_isolated ? "is-isolated" : ""}${
                      isSelected("accessibility", feature.properties.id) ? " is-selected" : ""
                    }`}
                    cx={cx}
                    cy={cy}
                    r={feature.properties.potentially_isolated ? 6 : 3.5}
                    onClick={() =>
                      onSelect({ kind: "accessibility", properties: feature.properties })
                    }
                  >
                    <title>{feature.properties.name}</title>
                  </circle>
                );
              }),
            )}
          </g>
        )}

        {visibleLayers.rivers && (
          <g className="static-map__rivers">
            {rivers.features.map((feature) => (
              <path
                key={feature.properties.id}
                className={isSelected("river", feature.properties.id) ? "is-selected" : undefined}
                d={geometryToSvgPath(feature.geometry, renderBounds)}
                onClick={() => onSelect({ kind: "river", properties: feature.properties })}
              >
                <title>{feature.properties.name}</title>
              </path>
            ))}
          </g>
        )}

        {visibleLayers.settlements && (
          <g className="static-map__settlements">
            {settlements.features.flatMap((feature) =>
              pointPositions(feature.geometry).map((position, index) => {
                const [cx, cy] = projectPosition(position, renderBounds);
                return (
                  <circle
                    key={`${feature.properties.id}:${index}`}
                    className={
                      isSelected("settlement", feature.properties.id) ? "is-selected" : undefined
                    }
                    cx={cx}
                    cy={cy}
                    r="3.5"
                    onClick={() =>
                      onSelect({ kind: "settlement", properties: feature.properties })
                    }
                  >
                    <title>{feature.properties.name}</title>
                  </circle>
                );
              }),
            )}
          </g>
        )}

        {visibleLayers.weather && (
          <g className="static-map__weather">
            {weather.features.flatMap((feature) =>
              pointPositions(feature.geometry).map((position, index) => {
                const [cx, cy] = projectPosition(position, renderBounds);
                const rainfallRadius = Math.min(
                  16,
                  Math.max(4, 4 + feature.properties.precipitation_24h_mm * 0.16),
                );
                return (
                  <g key={`${feature.properties.id}:${index}`}>
                    <circle
                      className={`static-map__weather-halo${
                        isSelected("weather", feature.properties.id) ? " is-selected" : ""
                      }`}
                      cx={cx}
                      cy={cy}
                      r={rainfallRadius}
                      onClick={() =>
                        onSelect({ kind: "weather", properties: feature.properties })
                      }
                    >
                      <title>
                        {feature.properties.name}: {feature.properties.precipitation_24h_mm.toFixed(1)} mm
                      </title>
                    </circle>
                    <circle
                      className="static-map__weather-dot"
                      cx={cx}
                      cy={cy}
                      r="3"
                      pointerEvents="none"
                    />
                  </g>
                );
              }),
            )}
          </g>
        )}

        {visibleLayers.facilities && (
          <g className="static-map__facilities">
            {facilities.features.flatMap((feature) =>
              pointPositions(feature.geometry).map((position, index) => {
                const [cx, cy] = projectPosition(position, renderBounds);
                return (
                  <circle
                    key={`${feature.properties.id}:${index}`}
                    className={
                      isSelected("facility", feature.properties.id) ? "is-selected" : undefined
                    }
                    cx={cx}
                    cy={cy}
                    r="2.6"
                    onClick={() =>
                      onSelect({ kind: "facility", properties: feature.properties })
                    }
                  >
                    <title>{feature.properties.name}</title>
                  </circle>
                );
              }),
            )}
          </g>
        )}

        {visibleLayers.stations && (
          <g className="static-map__stations">
            {stations.features.flatMap((feature) =>
              pointPositions(feature.geometry).map((position, index) => {
                const [cx, cy] = projectPosition(position, renderBounds);
                return (
                  <circle
                    key={`${feature.properties.id}:${index}`}
                    className={
                      isSelected("station", feature.properties.id) ? "is-selected" : undefined
                    }
                    cx={cx}
                    cy={cy}
                    r="5.5"
                    onClick={() =>
                      onSelect({ kind: "station", properties: feature.properties })
                    }
                  >
                    <title>{feature.properties.name}</title>
                  </circle>
                );
              }),
            )}
          </g>
        )}
      </svg>
      <div className="static-map__north" aria-hidden="true">
        <span>N</span>
        <span className="static-map__north-arrow" />
      </div>
      <a
        className="static-map__attribution"
        href="https://www.openstreetmap.org/copyright"
        target="_blank"
        rel="noreferrer"
      >
        © OpenStreetMap contributors
      </a>
    </div>
  );
}
