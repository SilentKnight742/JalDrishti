import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import * as maplibregl from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type {
  ErrorEvent as MapLibreErrorEvent,
  GeoJSONSource,
  Map as MapLibreMap,
  MapLayerMouseEvent,
  StyleSpecification,
} from "maplibre-gl";
import type { Geometry, Position } from "geojson";
import type {
  AccessibilityResponse,
  EventProperties,
  FacilityProperties,
  FloodExtentProperties,
  GeographyCollection,
  GeographyFeature,
  GeographyProperties,
  IncidentProperties,
  RiverProperties,
  RoadDisruptionProperties,
  SelectedMapFeature,
  SettlementProperties,
  SettlementAccessibilityProperties,
  StationProperties,
  WarningProperties,
  WeatherSummaryProperties,
} from "../types";
import { emptyFeatureCollection } from "../lib/geojson";
import { Icon } from "./Icon";
import { StaticGeographyMap } from "./StaticGeographyMap";

const ASSAM_CENTER: [number, number] = [92.9376, 26.2006];
export const OPENSTREETMAP_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

maplibregl.setWorkerUrl(maplibreWorkerUrl);

const OPERATIONAL_SOURCE_IDS = [
  "regions",
  "districts",
  "rivers",
  "settlements",
  "stations",
  "weather",
  "warnings",
  "events",
  "extents",
  "disruptions",
  "accessibility",
  "incidents",
  "facilities",
] as const;

type OperationalSourceId = (typeof OPERATIONAL_SOURCE_IDS)[number];
type OperationalCollections = Record<OperationalSourceId, GeographyCollection>;

const isOperationalSourceId = (value: unknown): value is OperationalSourceId =>
  typeof value === "string" && OPERATIONAL_SOURCE_IDS.includes(value as OperationalSourceId);

const MAP_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    basemap: {
      type: "raster",
      tiles: [OPENSTREETMAP_TILE_URL],
      tileSize: 256,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  layers: [{ id: "basemap", type: "raster", source: "basemap", minzoom: 0, maxzoom: 19 }],
};

interface OperationalMapProps {
  regions?: GeographyCollection;
  districts?: GeographyCollection;
  settlements?: GeographyCollection<SettlementProperties>;
  rivers?: GeographyCollection<RiverProperties>;
  stations?: GeographyCollection<StationProperties>;
  weather?: GeographyCollection<WeatherSummaryProperties>;
  warnings?: GeographyCollection<WarningProperties>;
  events?: GeographyCollection<EventProperties>;
  floodExtents?: GeographyCollection<FloodExtentProperties>;
  accessibility?: AccessibilityResponse;
  incidents?: GeographyCollection<IncidentProperties>;
  facilities?: GeographyCollection<FacilityProperties>;
  isLoading: boolean;
  hasError: boolean;
  onRetry: () => void;
  selection: SelectedMapFeature | null;
  onSelect: (feature: SelectedMapFeature) => void;
}

const coordinatesFromGeometry = (geometry: Geometry): Position[] => {
  if (geometry.type === "GeometryCollection") {
    return geometry.geometries.flatMap(coordinatesFromGeometry);
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

export const boundsFromGeometry = (
  geometry: Geometry,
): [[number, number], [number, number]] | null => {
  const positions = coordinatesFromGeometry(geometry).filter(
    ([longitude, latitude]) => Number.isFinite(longitude) && Number.isFinite(latitude),
  );
  if (positions.length === 0) return null;

  const longitudes = positions.map(([longitude]) => longitude);
  const latitudes = positions.map(([, latitude]) => latitude);
  return [
    [Math.min(...longitudes), Math.min(...latitudes)],
    [Math.max(...longitudes), Math.max(...latitudes)],
  ];
};

const focusGeometryOnMap = (
  map: MapLibreMap,
  geometry: Geometry,
  kind: SelectedMapFeature["kind"],
) => {
  const bounds = boundsFromGeometry(geometry);
  if (!bounds) return;
  const [[minLongitude, minLatitude], [maxLongitude, maxLatitude]] = bounds;
  const isPoint = minLongitude === maxLongitude && minLatitude === maxLatitude;

  if (isPoint) {
    map.flyTo({
      center: [minLongitude, minLatitude],
      zoom: kind === "facility" ? 13 : 11,
      duration: 700,
    });
    return;
  }

  map.fitBounds(bounds, {
    padding: 72,
    duration: 700,
    maxZoom: kind === "river" ? 9 : 10,
  });
};

const featureProperties = (event: MapLayerMouseEvent): GeographyProperties | null => {
  const properties = event.features?.[0]?.properties;
  if (!properties || typeof properties.id !== "string" || typeof properties.name !== "string") {
    return null;
  }
  return properties as GeographyProperties;
};

export function OperationalMap({
  regions = emptyFeatureCollection(),
  districts = emptyFeatureCollection(),
  settlements = emptyFeatureCollection() as GeographyCollection<SettlementProperties>,
  rivers = emptyFeatureCollection() as GeographyCollection<RiverProperties>,
  stations = emptyFeatureCollection() as GeographyCollection<StationProperties>,
  weather = emptyFeatureCollection() as GeographyCollection<WeatherSummaryProperties>,
  warnings = emptyFeatureCollection() as GeographyCollection<WarningProperties>,
  events = emptyFeatureCollection() as GeographyCollection<EventProperties>,
  floodExtents = emptyFeatureCollection() as GeographyCollection<FloodExtentProperties>,
  accessibility,
  incidents = emptyFeatureCollection() as GeographyCollection<IncidentProperties>,
  facilities = emptyFeatureCollection() as GeographyCollection<FacilityProperties>,
  isLoading,
  hasError,
  onRetry,
  selection,
  onSelect,
}: OperationalMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelect);
  const hasFittedRef = useRef(false);
  const geographyRef = useRef<OperationalCollections>({
    regions,
    districts,
    rivers,
    settlements,
    stations,
    weather,
    warnings,
    events,
    extents: floodExtents,
    disruptions: accessibility?.road_disruptions ?? emptyFeatureCollection(),
    accessibility: accessibility?.settlements ?? emptyFeatureCollection(),
    incidents,
    facilities,
  });
  const appliedCollectionsRef = useRef<Partial<OperationalCollections>>({});
  const [isReady, setIsReady] = useState(false);
  const [mapFailure, setMapFailure] = useState<string | null>(null);
  const [focusRequest, setFocusRequest] = useState<{
    geometry: Geometry;
    kind: SelectedMapFeature["kind"];
    id: string;
  } | null>(null);
  const [visibleLayers, setVisibleLayers] = useState({
    districts: true,
    rivers: true,
    settlements: true,
    stations: true,
    weather: true,
    warnings: true,
    events: true,
    extents: true,
    disruptions: true,
    accessibility: true,
    incidents: true,
    facilities: false,
  });

  onSelectRef.current = onSelect;
  geographyRef.current = {
    regions,
    districts,
    rivers,
    settlements,
    stations,
    weather,
    warnings,
    events,
    extents: floodExtents,
    disruptions: accessibility?.road_disruptions ?? emptyFeatureCollection(),
    accessibility: accessibility?.settlements ?? emptyFeatureCollection(),
    incidents,
    facilities,
  };

  useEffect(() => {
    if (isLoading || !mapContainerRef.current || mapRef.current) return;

    try {
      const map = new maplibregl.Map({
        container: mapContainerRef.current,
        style: MAP_STYLE,
        center: ASSAM_CENTER,
        zoom: 6.2,
        minZoom: 4.5,
        maxZoom: 16,
        attributionControl: false,
      });
      mapRef.current = map;

      map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "bottom-right");
      map.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 110 }), "bottom-left");
      map.addControl(new maplibregl.AttributionControl({ compact: false }), "bottom-right");

      const handleMapError = (event: MapLibreErrorEvent & { sourceId?: string }) => {
        if (!isOperationalSourceId(event.sourceId)) return;
        setMapFailure(`The ${event.sourceId} layer could not be rendered.`);
      };
      map.on("error", handleMapError);

      map.once("load", () => {
        const initialCollections = geographyRef.current;
        OPERATIONAL_SOURCE_IDS.forEach((sourceId) => {
          const collection = initialCollections[sourceId];
          map.addSource(sourceId, {
            type: "geojson",
            data: collection,
            promoteId: "id",
          });
          appliedCollectionsRef.current[sourceId] = collection;
        });

        map.addLayer({
          id: "region-fill",
          type: "fill",
          source: "regions",
          paint: { "fill-color": "#0b6370", "fill-opacity": 0.055 },
        });
        map.addLayer({
          id: "region-outline",
          type: "line",
          source: "regions",
          paint: { "line-color": "#0c5d69", "line-width": 2.2, "line-opacity": 0.82 },
        });
        map.addLayer({
          id: "district-fill",
          type: "fill",
          source: "districts",
          paint: {
            "fill-color": [
              "case",
              ["boolean", ["feature-state", "hover"], false],
              "#43b5b3",
              "#59bcb5",
            ],
            "fill-opacity": [
              "case",
              ["boolean", ["feature-state", "hover"], false],
              0.2,
              0.08,
            ],
          },
        });
        map.addLayer({
          id: "warning-fill",
          type: "fill",
          source: "warnings",
          filter: ["!=", ["get", "severity"], "green"],
          paint: {
            "fill-color": [
              "match",
              ["get", "severity"],
              "red",
              "#c63f3f",
              "orange",
              "#e87836",
              "yellow",
              "#e5bd3f",
              "#7abf72",
            ],
            "fill-opacity": 0.32,
          },
        });
        map.addLayer({
          id: "warning-selected",
          type: "line",
          source: "warnings",
          filter: ["==", ["get", "id"], "__none__"],
          paint: { "line-color": "#7a2634", "line-width": 3.5, "line-opacity": 0.98 },
        });
        map.addLayer({
          id: "extent-fill",
          type: "fill",
          source: "extents",
          paint: {
            "fill-color": "#177b9f",
            "fill-opacity": 0.42,
          },
        });
        map.addLayer({
          id: "extent-outline",
          type: "line",
          source: "extents",
          paint: { "line-color": "#07526f", "line-width": 2.2, "line-opacity": 0.96 },
        });
        map.addLayer({
          id: "extent-selected",
          type: "line",
          source: "extents",
          filter: ["==", ["get", "id"], "__none__"],
          paint: { "line-color": "#f7f3df", "line-width": 4.5, "line-opacity": 1 },
        });
        map.addLayer({
          id: "disruption-line",
          type: "line",
          source: "disruptions",
          paint: {
            "line-color": "#c94c45",
            "line-width": ["interpolate", ["linear"], ["zoom"], 6, 2.2, 12, 5.5],
            "line-opacity": 0.92,
            "line-dasharray": [1.5, 1],
          },
        });
        map.addLayer({
          id: "disruption-selected",
          type: "line",
          source: "disruptions",
          filter: ["==", ["get", "id"], "__none__"],
          paint: { "line-color": "#6f1f27", "line-width": 7, "line-opacity": 1 },
        });
        map.addLayer({
          id: "accessibility-settlement",
          type: "circle",
          source: "accessibility",
          paint: {
            "circle-radius": [
              "case",
              ["boolean", ["get", "potentially_isolated"], false],
              8,
              4,
            ],
            "circle-color": [
              "case",
              ["boolean", ["get", "potentially_isolated"], false],
              "#9d2636",
              "#6d8790",
            ],
            "circle-opacity": [
              "case",
              ["boolean", ["get", "potentially_isolated"], false],
              0.95,
              0.58,
            ],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.4,
          },
        });
        map.addLayer({
          id: "accessibility-selected",
          type: "circle",
          source: "accessibility",
          filter: ["==", ["get", "id"], "__none__"],
          paint: {
            "circle-radius": 11,
            "circle-color": "#9d2636",
            "circle-stroke-color": "#f7f3df",
            "circle-stroke-width": 3,
          },
        });
        map.addLayer({
          id: "event-fill",
          type: "fill",
          source: "events",
          paint: {
            "fill-color": [
              "match",
              ["get", "state"],
              "watch",
              "#e5bd3f",
              "warning",
              "#e87836",
              "severe",
              "#c63f3f",
              "recovery",
              "#4c9dd0",
              "#7f8f91",
            ],
            "fill-opacity": 0.22,
          },
        });
        map.addLayer({
          id: "event-outline",
          type: "line",
          source: "events",
          paint: {
            "line-color": [
              "match",
              ["get", "state"],
              "watch",
              "#9a7216",
              "warning",
              "#ad4b1f",
              "severe",
              "#912f36",
              "recovery",
              "#24678f",
              "#596b6f",
            ],
            "line-width": 2.4,
            "line-opacity": 0.94,
          },
        });
        map.addLayer({
          id: "event-selected",
          type: "line",
          source: "events",
          filter: ["==", ["get", "id"], "__none__"],
          paint: { "line-color": "#7a2634", "line-width": 4.5, "line-opacity": 1 },
        });
        map.addLayer({
          id: "district-outline",
          type: "line",
          source: "districts",
          paint: { "line-color": "#267f88", "line-width": 0.9, "line-opacity": 0.8 },
        });
        map.addLayer({
          id: "district-selected",
          type: "line",
          source: "districts",
          filter: ["==", ["get", "id"], "__none__"],
          paint: { "line-color": "#e26c45", "line-width": 3, "line-opacity": 0.95 },
        });
        map.addLayer({
          id: "river-line",
          type: "line",
          source: "rivers",
          paint: {
            "line-color": "#397fa8",
            "line-opacity": 0.82,
            "line-width": ["interpolate", ["linear"], ["zoom"], 5, 1.2, 10, 2.8],
          },
        });
        map.addLayer({
          id: "river-selected",
          type: "line",
          source: "rivers",
          filter: ["==", ["get", "id"], "__none__"],
          paint: { "line-color": "#e26c45", "line-width": 4, "line-opacity": 0.95 },
        });
        map.addLayer({
          id: "weather-halo",
          type: "circle",
          source: "weather",
          paint: {
            "circle-radius": [
              "interpolate",
              ["linear"],
              ["get", "precipitation_24h_mm"],
              0,
              4,
              20,
              9,
              75,
              16,
            ],
            "circle-color": "#4c9dd0",
            "circle-opacity": 0.28,
            "circle-stroke-color": "#24678f",
            "circle-stroke-width": 1.2,
          },
        });
        map.addLayer({
          id: "weather-dot",
          type: "circle",
          source: "weather",
          paint: {
            "circle-radius": 3,
            "circle-color": "#24678f",
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 0.8,
          },
        });
        map.addLayer({
          id: "weather-selected",
          type: "circle",
          source: "weather",
          filter: ["==", ["get", "id"], "__none__"],
          paint: {
            "circle-radius": 11,
            "circle-color": "#4c9dd0",
            "circle-opacity": 0.55,
            "circle-stroke-color": "#e26c45",
            "circle-stroke-width": 3,
          },
        });
        map.addLayer({
          id: "settlement-halo",
          type: "circle",
          source: "settlements",
          paint: {
            "circle-radius": 5.5,
            "circle-color": "#ffffff",
            "circle-opacity": 0.9,
            "circle-stroke-color": "#236e71",
            "circle-stroke-width": 1,
          },
        });
        map.addLayer({
          id: "settlement-dot",
          type: "circle",
          source: "settlements",
          paint: {
            "circle-radius": 2.6,
            "circle-color": "#2f8e8b",
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 0.5,
          },
        });
        map.addLayer({
          id: "settlement-selected",
          type: "circle",
          source: "settlements",
          filter: ["==", ["get", "id"], "__none__"],
          paint: {
            "circle-radius": 7,
            "circle-color": "#2f8e8b",
            "circle-stroke-color": "#e26c45",
            "circle-stroke-width": 2.5,
          },
        });
        map.addLayer({
          id: "station-halo",
          type: "circle",
          source: "stations",
          paint: {
            "circle-radius": 9,
            "circle-color": "#ffffff",
            "circle-opacity": 0.95,
            "circle-stroke-color": "#183f52",
            "circle-stroke-width": 1.4,
          },
        });
        map.addLayer({
          id: "station-dot",
          type: "circle",
          source: "stations",
          paint: {
            "circle-radius": 5,
            "circle-color": "#e7ae55",
            "circle-stroke-color": "#183f52",
            "circle-stroke-width": 1.2,
          },
        });
        map.addLayer({
          id: "station-selected",
          type: "circle",
          source: "stations",
          filter: ["==", ["get", "id"], "__none__"],
          paint: {
            "circle-radius": 11,
            "circle-color": "#e7ae55",
            "circle-stroke-color": "#e26c45",
            "circle-stroke-width": 3,
          },
        });
        map.addLayer({
          id: "facility-halo",
          type: "circle",
          source: "facilities",
          paint: {
            "circle-radius": 8,
            "circle-color": "#ffffff",
            "circle-opacity": 0.92,
            "circle-stroke-color": "#0a4a58",
            "circle-stroke-width": 1,
          },
        });
        map.addLayer({
          id: "facility-dot",
          type: "circle",
          source: "facilities",
          paint: {
            "circle-radius": 3.6,
            "circle-color": "#e26c45",
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 0.8,
          },
        });
        map.addLayer({
          id: "facility-selected",
          type: "circle",
          source: "facilities",
          filter: ["==", ["get", "id"], "__none__"],
          paint: {
            "circle-radius": 9,
            "circle-color": "#e26c45",
            "circle-stroke-color": "#0a4a58",
            "circle-stroke-width": 2.5,
          },
        });
        map.addLayer({
          id: "incident-halo",
          type: "circle",
          source: "incidents",
          paint: {
            "circle-radius": 10,
            "circle-color": "#fff7e6",
            "circle-opacity": 0.96,
            "circle-stroke-color": "#b95632",
            "circle-stroke-width": 2,
          },
        });
        map.addLayer({
          id: "incident-dot",
          type: "circle",
          source: "incidents",
          paint: {
            "circle-radius": 4,
            "circle-color": "#b95632",
            "circle-stroke-color": "#fff7e6",
            "circle-stroke-width": 1,
          },
        });
        map.addLayer({
          id: "incident-selected",
          type: "circle",
          source: "incidents",
          filter: ["==", ["get", "id"], "__none__"],
          paint: {
            "circle-radius": 13,
            "circle-color": "#b95632",
            "circle-opacity": 0.28,
            "circle-stroke-color": "#7a2634",
            "circle-stroke-width": 3,
          },
        });

        const handleDistrictClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) onSelectRef.current({ kind: "district", properties });
        };
        const handleFacilityClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({ kind: "facility", properties: properties as FacilityProperties });
          }
        };
        const handleSettlementClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({
              kind: "settlement",
              properties: properties as SettlementProperties,
            });
          }
        };
        const handleRiverClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({ kind: "river", properties: properties as RiverProperties });
          }
        };
        const handleStationClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({ kind: "station", properties: properties as StationProperties });
          }
        };
        const handleWeatherClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({
              kind: "weather",
              properties: properties as WeatherSummaryProperties,
            });
          }
        };
        const handleWarningClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({
              kind: "warning",
              properties: properties as WarningProperties,
            });
          }
        };
        const handleEventClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({
              kind: "event",
              properties: properties as EventProperties,
            });
          }
        };
        const handleExtentClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({
              kind: "extent",
              properties: properties as FloodExtentProperties,
            });
          }
        };
        const handleDisruptionClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({
              kind: "road_disruption",
              properties: properties as RoadDisruptionProperties,
            });
          }
        };
        const handleAccessibilityClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({
              kind: "accessibility",
              properties: properties as SettlementAccessibilityProperties,
            });
          }
        };
        const handleIncidentClick = (event: MapLayerMouseEvent) => {
          const properties = featureProperties(event);
          if (properties) {
            onSelectRef.current({
              kind: "incident",
              properties: properties as IncidentProperties,
            });
          }
        };
        const showPointer = () => {
          map.getCanvas().style.cursor = "pointer";
        };
        const hidePointer = () => {
          map.getCanvas().style.cursor = "";
        };

        map.on("click", "district-fill", handleDistrictClick);
        map.on("click", "river-line", handleRiverClick);
        map.on("click", "settlement-halo", handleSettlementClick);
        map.on("click", "station-halo", handleStationClick);
        map.on("click", "weather-halo", handleWeatherClick);
        map.on("click", "warning-fill", handleWarningClick);
        map.on("click", "event-fill", handleEventClick);
        map.on("click", "extent-fill", handleExtentClick);
        map.on("click", "disruption-line", handleDisruptionClick);
        map.on("click", "accessibility-settlement", handleAccessibilityClick);
        map.on("click", "facility-halo", handleFacilityClick);
        map.on("click", "incident-halo", handleIncidentClick);
        map.on("mouseenter", "district-fill", showPointer);
        map.on("mouseleave", "district-fill", hidePointer);
        map.on("mouseenter", "river-line", showPointer);
        map.on("mouseleave", "river-line", hidePointer);
        map.on("mouseenter", "settlement-halo", showPointer);
        map.on("mouseleave", "settlement-halo", hidePointer);
        map.on("mouseenter", "station-halo", showPointer);
        map.on("mouseleave", "station-halo", hidePointer);
        map.on("mouseenter", "weather-halo", showPointer);
        map.on("mouseleave", "weather-halo", hidePointer);
        map.on("mouseenter", "warning-fill", showPointer);
        map.on("mouseleave", "warning-fill", hidePointer);
        map.on("mouseenter", "event-fill", showPointer);
        map.on("mouseleave", "event-fill", hidePointer);
        map.on("mouseenter", "extent-fill", showPointer);
        map.on("mouseleave", "extent-fill", hidePointer);
        map.on("mouseenter", "disruption-line", showPointer);
        map.on("mouseleave", "disruption-line", hidePointer);
        map.on("mouseenter", "accessibility-settlement", showPointer);
        map.on("mouseleave", "accessibility-settlement", hidePointer);
        map.on("mouseenter", "facility-halo", showPointer);
        map.on("mouseleave", "facility-halo", hidePointer);
        map.on("mouseenter", "incident-halo", showPointer);
        map.on("mouseleave", "incident-halo", hidePointer);
        setIsReady(true);
      });
    } catch (error) {
      setMapFailure(
        error instanceof Error
          ? `WebGL map unavailable: ${error.message}`
          : "The WebGL map could not be initialised.",
      );
    }

    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [isLoading]);

  useEffect(() => {
    if (!isReady || !mapRef.current) return;
    const map = mapRef.current;
    const collections: OperationalCollections = {
      regions,
      districts,
      rivers,
      settlements,
      stations,
      weather,
      warnings,
      events,
      extents: floodExtents,
      disruptions: accessibility?.road_disruptions ?? emptyFeatureCollection(),
      accessibility: accessibility?.settlements ?? emptyFeatureCollection(),
      incidents,
      facilities,
    };
    let cancelled = false;

    const updateChangedSources = async () => {
      const updates = OPERATIONAL_SOURCE_IDS.flatMap((sourceId) => {
        const collection = collections[sourceId];
        if (appliedCollectionsRef.current[sourceId] === collection) return [];

        const source = map.getSource(sourceId) as GeoJSONSource | undefined;
        if (!source) {
          throw new Error(`MapLibre source ${sourceId} is unavailable.`);
        }

        return [
          source.setData(collection).then(() => {
            appliedCollectionsRef.current[sourceId] = collection;
          }),
        ];
      });

      await Promise.all(updates);
      if (!cancelled && updates.length > 0) map.triggerRepaint();
    };

    void updateChangedSources().catch((error: unknown) => {
      if (cancelled) return;
      setMapFailure(
        error instanceof Error
          ? `Operational layers could not be refreshed: ${error.message}`
          : "Operational layers could not be refreshed.",
      );
    });

    if (!hasFittedRef.current && districts.features.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      districts.features.forEach((feature) => {
        if (!feature.geometry) return;
        coordinatesFromGeometry(feature.geometry).forEach((position) => {
          bounds.extend([position[0], position[1]] as [number, number]);
        });
      });
      if (!bounds.isEmpty()) {
        mapRef.current.fitBounds(bounds, { padding: 48, duration: 700, maxZoom: 8 });
        hasFittedRef.current = true;
      }
    }

    return () => {
      cancelled = true;
    };
  }, [accessibility, districts, events, facilities, floodExtents, incidents, isReady, regions, rivers, settlements, stations, warnings, weather]);

  useEffect(() => {
    if (!isReady || !mapRef.current) return;
    const districtVisibility = visibleLayers.districts ? "visible" : "none";
    const riverVisibility = visibleLayers.rivers ? "visible" : "none";
    const settlementVisibility = visibleLayers.settlements ? "visible" : "none";
    const stationVisibility = visibleLayers.stations ? "visible" : "none";
    const weatherVisibility = visibleLayers.weather ? "visible" : "none";
    const warningVisibility = visibleLayers.warnings ? "visible" : "none";
    const eventVisibility = visibleLayers.events ? "visible" : "none";
    const extentVisibility = visibleLayers.extents ? "visible" : "none";
    const disruptionVisibility = visibleLayers.disruptions ? "visible" : "none";
    const accessibilityVisibility = visibleLayers.accessibility ? "visible" : "none";
    const incidentVisibility = visibleLayers.incidents ? "visible" : "none";
    const facilityVisibility = visibleLayers.facilities ? "visible" : "none";
    mapRef.current.setLayoutProperty("district-fill", "visibility", districtVisibility);
    mapRef.current.setLayoutProperty("district-outline", "visibility", districtVisibility);
    mapRef.current.setLayoutProperty("district-selected", "visibility", districtVisibility);
    mapRef.current.setLayoutProperty("river-line", "visibility", riverVisibility);
    mapRef.current.setLayoutProperty("river-selected", "visibility", riverVisibility);
    mapRef.current.setLayoutProperty("settlement-halo", "visibility", settlementVisibility);
    mapRef.current.setLayoutProperty("settlement-dot", "visibility", settlementVisibility);
    mapRef.current.setLayoutProperty("settlement-selected", "visibility", settlementVisibility);
    mapRef.current.setLayoutProperty("station-halo", "visibility", stationVisibility);
    mapRef.current.setLayoutProperty("station-dot", "visibility", stationVisibility);
    mapRef.current.setLayoutProperty("station-selected", "visibility", stationVisibility);
    mapRef.current.setLayoutProperty("weather-halo", "visibility", weatherVisibility);
    mapRef.current.setLayoutProperty("weather-dot", "visibility", weatherVisibility);
    mapRef.current.setLayoutProperty("weather-selected", "visibility", weatherVisibility);
    mapRef.current.setLayoutProperty("warning-fill", "visibility", warningVisibility);
    mapRef.current.setLayoutProperty("warning-selected", "visibility", warningVisibility);
    mapRef.current.setLayoutProperty("event-fill", "visibility", eventVisibility);
    mapRef.current.setLayoutProperty("event-outline", "visibility", eventVisibility);
    mapRef.current.setLayoutProperty("event-selected", "visibility", eventVisibility);
    mapRef.current.setLayoutProperty("extent-fill", "visibility", extentVisibility);
    mapRef.current.setLayoutProperty("extent-outline", "visibility", extentVisibility);
    mapRef.current.setLayoutProperty("extent-selected", "visibility", extentVisibility);
    mapRef.current.setLayoutProperty("disruption-line", "visibility", disruptionVisibility);
    mapRef.current.setLayoutProperty("disruption-selected", "visibility", disruptionVisibility);
    mapRef.current.setLayoutProperty(
      "accessibility-settlement",
      "visibility",
      accessibilityVisibility,
    );
    mapRef.current.setLayoutProperty(
      "accessibility-selected",
      "visibility",
      accessibilityVisibility,
    );
    mapRef.current.setLayoutProperty("facility-halo", "visibility", facilityVisibility);
    mapRef.current.setLayoutProperty("facility-dot", "visibility", facilityVisibility);
    mapRef.current.setLayoutProperty("facility-selected", "visibility", facilityVisibility);
    mapRef.current.setLayoutProperty("incident-halo", "visibility", incidentVisibility);
    mapRef.current.setLayoutProperty("incident-dot", "visibility", incidentVisibility);
    mapRef.current.setLayoutProperty("incident-selected", "visibility", incidentVisibility);
  }, [isReady, visibleLayers]);

  useEffect(() => {
    if (!isReady || !mapRef.current) return;
    const selectedId = selection?.properties.id ?? "__none__";
    const filterFor = (kind: SelectedMapFeature["kind"]): maplibregl.FilterSpecification => [
      "==",
      ["get", "id"],
      selection?.kind === kind ? selectedId : "__none__",
    ];
    mapRef.current.setFilter("district-selected", filterFor("district"));
    mapRef.current.setFilter("river-selected", filterFor("river"));
    mapRef.current.setFilter("settlement-selected", filterFor("settlement"));
    mapRef.current.setFilter("station-selected", filterFor("station"));
    mapRef.current.setFilter("weather-selected", filterFor("weather"));
    mapRef.current.setFilter("warning-selected", filterFor("warning"));
    mapRef.current.setFilter("event-selected", filterFor("event"));
    mapRef.current.setFilter("extent-selected", filterFor("extent"));
    mapRef.current.setFilter("disruption-selected", filterFor("road_disruption"));
    mapRef.current.setFilter("accessibility-selected", filterFor("accessibility"));
    mapRef.current.setFilter("facility-selected", filterFor("facility"));
    mapRef.current.setFilter("incident-selected", filterFor("incident"));
  }, [isReady, selection]);

  useEffect(() => {
    if (!isReady || !mapRef.current || !focusRequest) return;
    focusGeometryOnMap(mapRef.current, focusRequest.geometry, focusRequest.kind);
  }, [focusRequest, isReady]);

  const fitAssam = () => {
    setFocusRequest(null);
    if (!mapRef.current || !isReady) return;
    const positions = districts.features.flatMap((feature) =>
      coordinatesFromGeometry(feature.geometry),
    );
    if (positions.length === 0) return;
    const bounds = new maplibregl.LngLatBounds();
    positions.forEach((position) => {
      bounds.extend([position[0], position[1]] as [number, number]);
    });
    if (!bounds.isEmpty()) {
      mapRef.current.fitBounds(bounds, { padding: 48, duration: 700, maxZoom: 8 });
    }
  };

  const selectAndFocus = (
    kind: SelectedMapFeature["kind"],
    feature: GeographyFeature,
  ) => {
    const layerKey = {
      district: "districts",
      river: "rivers",
      settlement: "settlements",
      station: "stations",
      weather: "weather",
      warning: "warnings",
      event: "events",
      extent: "extents",
      road_disruption: "disruptions",
      accessibility: "accessibility",
      incident: "incidents",
      facility: "facilities",
    }[kind];
    setVisibleLayers((layers) => ({ ...layers, [layerKey]: true }));
    setFocusRequest({ geometry: feature.geometry, kind, id: feature.properties.id });
    onSelectRef.current({ kind, properties: feature.properties } as SelectedMapFeature);
  };

  const inspectFromPicker = (event: ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    const district = districts.features.find(
      (feature) => `district:${feature.properties.id}` === value,
    );
    if (district) {
      selectAndFocus("district", district);
      return;
    }
    const river = rivers.features.find(
      (feature) => `river:${feature.properties.id}` === value,
    );
    if (river) {
      selectAndFocus("river", river);
      return;
    }
    const settlement = settlements.features.find(
      (feature) => `settlement:${feature.properties.id}` === value,
    );
    if (settlement) {
      selectAndFocus("settlement", settlement);
      return;
    }
    const station = stations.features.find(
      (feature) => `station:${feature.properties.id}` === value,
    );
    if (station) {
      selectAndFocus("station", station);
      return;
    }
    const warning = warnings.features.find(
      (feature) => `warning:${feature.properties.id}` === value,
    );
    if (warning) {
      selectAndFocus("warning", warning);
      return;
    }
    const selectedEvent = events.features.find(
      (feature) => `event:${feature.properties.id}` === value,
    );
    if (selectedEvent) {
      selectAndFocus("event", selectedEvent);
      return;
    }
    const extent = floodExtents.features.find(
      (feature) => `extent:${feature.properties.id}` === value,
    );
    if (extent) {
      selectAndFocus("extent", extent);
      return;
    }
    const disruption = accessibility?.road_disruptions.features.find(
      (feature) => `road_disruption:${feature.properties.id}` === value,
    );
    if (disruption) {
      selectAndFocus("road_disruption", disruption);
      return;
    }
    const settlementAccess = accessibility?.settlements.features.find(
      (feature) => `accessibility:${feature.properties.id}` === value,
    );
    if (settlementAccess) {
      selectAndFocus("accessibility", settlementAccess);
      return;
    }
    const weatherSummary = weather.features.find(
      (feature) => `weather:${feature.properties.id}` === value,
    );
    if (weatherSummary) {
      selectAndFocus("weather", weatherSummary);
      return;
    }
    const incident = incidents.features.find(
      (feature) => `incident:${feature.properties.id}` === value,
    );
    if (incident) {
      selectAndFocus("incident", incident);
      return;
    }
    const facility = facilities.features.find(
      (feature) => `facility:${feature.properties.id}` === value,
    );
    if (facility) {
      selectAndFocus("facility", facility);
    }
  };

  const pickerValue = selection
    ? `${selection.kind}:${selection.properties.id}`
    : "";

  return (
    <section className="map-shell" aria-labelledby="map-heading">
      <div className="map-heading">
        <div>
          <span className="eyebrow">Operational geography</span>
          <h1 id="map-heading">Assam evidence map</h1>
        </div>
        <span className="map-heading__mode">{events.features.length > 0 ? "Live event view" : "Foundation view"}</span>
      </div>

      <div className="map-stage">
        <div
          ref={mapContainerRef}
          className={`map-canvas${mapFailure ? " map-canvas--hidden" : ""}`}
          role="application"
          aria-label="Interactive map of Assam flood events, warnings, public reports, rainfall guidance, districts, rivers, settlements, gauge stations and facilities"
          tabIndex={0}
        />

        {mapFailure && (
          <StaticGeographyMap
            regions={regions}
            districts={districts}
            settlements={settlements}
            rivers={rivers}
            stations={stations}
            weather={weather}
            warnings={warnings}
            events={events}
            floodExtents={floodExtents}
            accessibility={accessibility}
            incidents={incidents}
            facilities={facilities}
            visibleLayers={visibleLayers}
            onSelect={onSelect}
            focusGeometry={focusRequest?.geometry ?? null}
            selectedRecord={selection}
          />
        )}

        {(districts.features.length > 0 ||
          rivers.features.length > 0 ||
          settlements.features.length > 0 ||
          stations.features.length > 0 ||
          weather.features.length > 0 ||
          warnings.features.length > 0 ||
          events.features.length > 0 ||
          floodExtents.features.length > 0 ||
          Boolean(accessibility?.road_disruptions.features.length) ||
          Boolean(accessibility?.settlements.features.length) ||
          incidents.features.length > 0 ||
          facilities.features.length > 0) && (
          <div className="feature-picker">
            <label htmlFor="mapped-record-picker">Inspect mapped record</label>
            <select id="mapped-record-picker" value={pickerValue} onChange={inspectFromPicker}>
              <option value="" disabled>Select a mapped record</option>
              {events.features.length > 0 && (
                <optgroup label="Active flood events">
                  {events.features.map((feature) => (
                    <option key={`event:${feature.properties.id}`} value={`event:${feature.properties.id}`}>
                      {feature.properties.name} · {feature.properties.state}
                    </option>
                  ))}
                </optgroup>
              )}
              {floodExtents.features.length > 0 && (
                <optgroup label="Satellite change extents">
                  {floodExtents.features.map((feature) => (
                    <option key={`extent:${feature.properties.id}`} value={`extent:${feature.properties.id}`}>
                      {feature.properties.name} · {feature.properties.area_km2.toFixed(2)} km²
                    </option>
                  ))}
                </optgroup>
              )}
              {Boolean(accessibility?.road_disruptions.features.length) && (
                <optgroup label="Potential road disruptions">
                  {accessibility?.road_disruptions.features.map((feature) => (
                    <option
                      key={`road_disruption:${feature.properties.id}`}
                      value={`road_disruption:${feature.properties.id}`}
                    >
                      {feature.properties.name} · {feature.properties.overlap_km.toFixed(2)} km
                    </option>
                  ))}
                </optgroup>
              )}
              {Boolean(accessibility?.settlements.features.length) && (
                <optgroup label="Settlement accessibility">
                  {accessibility?.settlements.features.map((feature) => (
                    <option
                      key={`accessibility:${feature.properties.id}`}
                      value={`accessibility:${feature.properties.id}`}
                    >
                      {feature.properties.name} · {feature.properties.potentially_isolated ? "potentially isolated" : feature.properties.assessment_status.replaceAll("_", " ")}
                    </option>
                  ))}
                </optgroup>
              )}
              {incidents.features.length > 0 && (
                <optgroup label="Unverified public reports">
                  {incidents.features.map((feature) => (
                    <option
                      key={`incident:${feature.properties.id}`}
                      value={`incident:${feature.properties.id}`}
                    >
                      {feature.properties.public_reference} · {feature.properties.incident_type.replaceAll("_", " ")}
                    </option>
                  ))}
                </optgroup>
              )}
              {districts.features.length > 0 && (
                <optgroup label="Districts">
                  {districts.features.map((feature) => (
                    <option key={`district:${feature.properties.id}`} value={`district:${feature.properties.id}`}>
                      {feature.properties.name}
                    </option>
                  ))}
                </optgroup>
              )}
              {rivers.features.length > 0 && (
                <optgroup label="Rivers">
                  {rivers.features.map((feature) => (
                    <option key={`river:${feature.properties.id}`} value={`river:${feature.properties.id}`}>
                      {feature.properties.name}
                    </option>
                  ))}
                </optgroup>
              )}
              {settlements.features.length > 0 && (
                <optgroup label="Settlements">
                  {settlements.features.map((feature) => (
                    <option key={`settlement:${feature.properties.id}`} value={`settlement:${feature.properties.id}`}>
                      {feature.properties.name}
                    </option>
                  ))}
                </optgroup>
              )}
              {stations.features.length > 0 && (
                <optgroup label="Gauge stations · pilot">
                  {stations.features.map((feature) => (
                    <option key={`station:${feature.properties.id}`} value={`station:${feature.properties.id}`}>
                      {feature.properties.name}
                    </option>
                  ))}
                </optgroup>
              )}
              {warnings.features.some((feature) => feature.properties.severity !== "green") && (
                <optgroup label="Official warnings · day 1">
                  {warnings.features
                    .filter((feature) => feature.properties.severity !== "green")
                    .map((feature) => (
                      <option key={`warning:${feature.properties.id}`} value={`warning:${feature.properties.id}`}>
                        {feature.properties.name} · {feature.properties.severity}
                      </option>
                    ))}
                </optgroup>
              )}
              {weather.features.length > 0 && (
                <optgroup label="Rainfall model guidance · 24h">
                  {weather.features.map((feature) => (
                    <option key={`weather:${feature.properties.id}`} value={`weather:${feature.properties.id}`}>
                      {feature.properties.name} · {feature.properties.precipitation_24h_mm.toFixed(1)} mm
                    </option>
                  ))}
                </optgroup>
              )}
              {facilities.features.length > 0 && (
                <optgroup label="Facilities">
                  {facilities.features.map((feature) => (
                    <option key={`facility:${feature.properties.id}`} value={`facility:${feature.properties.id}`}>
                      {feature.properties.name}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
            {focusRequest && (
              <button className="feature-picker__reset" type="button" onClick={fitAssam}>
                Show all Assam
              </button>
            )}
          </div>
        )}

        <div className="layer-control" role="group" aria-label="Map layers">
          <span className="layer-control__title"><Icon name="layers" /> Layers</span>
          <button
            type="button"
            aria-pressed={visibleLayers.events}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, events: !layers.events }))}
          >
            <span className="legend-swatch legend-swatch--event" /> Active events
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.incidents}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, incidents: !layers.incidents }))}
          >
            <span className="legend-swatch legend-swatch--incident" /> Unverified reports
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.extents}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, extents: !layers.extents }))}
          >
            <span className="legend-swatch legend-swatch--extent" /> Satellite extent
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.disruptions}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, disruptions: !layers.disruptions }))}
          >
            <span className="legend-swatch legend-swatch--disruption" /> Potential road disruption
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.accessibility}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, accessibility: !layers.accessibility }))}
          >
            <span className="legend-swatch legend-swatch--isolation" /> Access screening
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.warnings}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, warnings: !layers.warnings }))}
          >
            <span className="legend-swatch legend-swatch--warning" /> IMD warnings
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.weather}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, weather: !layers.weather }))}
          >
            <span className="legend-swatch legend-swatch--weather" /> Rain model
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.stations}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, stations: !layers.stations }))}
          >
            <span className="legend-swatch legend-swatch--station" /> Gauge pilot
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.districts}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, districts: !layers.districts }))}
          >
            <span className="legend-swatch legend-swatch--district" /> Districts
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.rivers}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, rivers: !layers.rivers }))}
          >
            <span className="legend-swatch legend-swatch--river" /> Rivers
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.settlements}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, settlements: !layers.settlements }))}
          >
            <span className="legend-swatch legend-swatch--settlement" /> Settlements
          </button>
          <button
            type="button"
            aria-pressed={visibleLayers.facilities}
            onClick={() => setVisibleLayers((layers) => ({ ...layers, facilities: !layers.facilities }))}
          >
            <span className="legend-swatch legend-swatch--facility" /> Facilities
          </button>
        </div>

        {isLoading && (
          <div className="map-message" role="status" aria-live="polite">
            <span className="loader" />
            <div><strong>Loading canonical geography</strong><span>Requesting Assam records from the API</span></div>
          </div>
        )}

        {mapFailure && !hasError && !isLoading && (
          <div className="map-compatibility" role="status">
            Compatibility view · {mapFailure}
          </div>
        )}

        {hasError && !isLoading && (
          <div className="map-message map-message--error" role="alert">
            <Icon name="alert" />
            <div>
              <strong>Geography could not be verified</strong>
              <span>One or more API geography requests failed.</span>
            </div>
            <button type="button" onClick={onRetry}>Try again</button>
          </div>
        )}

        <div className="map-caption">
          <span className="map-caption__dot" />
          All operational geography is rendered from JalDrishti API responses
        </div>
      </div>
    </section>
  );
}
