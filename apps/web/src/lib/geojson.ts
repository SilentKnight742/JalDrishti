import type { Feature, FeatureCollection, Geometry } from "geojson";
import type {
  GeographyCollection,
  GeographyFeature,
  GeographyProperties,
} from "../types";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const isFeature = (value: unknown): value is GeographyFeature =>
  isRecord(value) && value.type === "Feature" && "geometry" in value;

const recordToFeature = (value: unknown): GeographyFeature | null => {
  if (isFeature(value)) return value;
  if (!isRecord(value) || !("geometry" in value)) return null;

  const { geometry, ...properties } = value;
  if (!isRecord(geometry) || typeof geometry.type !== "string") return null;

  return {
    type: "Feature",
    id: typeof value.id === "string" || typeof value.id === "number" ? value.id : undefined,
    geometry: geometry as unknown as Geometry,
    properties: properties as GeographyProperties,
  };
};

const collectionFromList = (items: unknown[]): GeographyCollection => ({
  type: "FeatureCollection",
  features: items.map(recordToFeature).filter((item): item is GeographyFeature => item !== null),
});

/**
 * Normalises the API's GeoJSON contract while accepting common `data` and `items`
 * envelopes. Administrative geometry still always originates from the API.
 */
export const toFeatureCollection = (payload: unknown): GeographyCollection => {
  if (isRecord(payload) && payload.type === "FeatureCollection" && Array.isArray(payload.features)) {
    return payload as unknown as FeatureCollection<Geometry, GeographyProperties>;
  }

  if (isFeature(payload)) {
    return { type: "FeatureCollection", features: [payload] };
  }

  if (Array.isArray(payload)) return collectionFromList(payload);

  if (isRecord(payload) && "data" in payload) return toFeatureCollection(payload.data);
  if (isRecord(payload) && Array.isArray(payload.items)) return collectionFromList(payload.items);

  throw new TypeError("Expected a GeoJSON FeatureCollection from the JalDrishti API.");
};

export const toFeature = (payload: unknown): GeographyFeature => {
  if (isFeature(payload)) return payload;
  if (isRecord(payload) && "data" in payload) return toFeature(payload.data);

  const collection = toFeatureCollection(payload);
  if (collection.features.length !== 1) {
    throw new TypeError("Expected one GeoJSON Feature from the JalDrishti API.");
  }
  return collection.features[0];
};

export const emptyFeatureCollection = (): GeographyCollection => ({
  type: "FeatureCollection",
  features: [],
});

export const featureName = (feature: Feature<Geometry, GeographyProperties>): string =>
  feature.properties?.name || feature.properties?.code || "Unnamed area";
