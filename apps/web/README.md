# JalDrishti web

The Phase 0–10 operational frontend for JalDrishti. It renders Assam geography and event evidence from the FastAPI service while keeping provenance, freshness, uncertainty, and unavailable evidence visible.

## Local development

```bash
cp .env.example .env
npm install
npm run dev
```

`VITE_API_BASE_URL` defaults to `/api/v1`. During local development, Vite proxies `/api` to `API_PROXY_TARGET` (default `http://localhost:8000`).

## Verification

```bash
npm run typecheck
npm test
npm run build

# With the Compose application running on port 8080:
npx playwright install chromium
npm run test:e2e
```

## API contract

The application reads:

- `GET /api/v1/status`
- `GET /api/v1/regions`
- `GET /api/v1/districts?region_id=assam`
- `GET /api/v1/districts/{id}`
- `GET /api/v1/settlements?region_id=assam`
- `GET /api/v1/rivers?region_id=assam`
- `GET /api/v1/facilities?region_id=assam`

All administrative geometry is API-supplied GeoJSON. No district or region GeoJSON is bundled in the client.

## Basemap

MapLibre renders the standard OpenStreetMap raster tiles with visible OpenStreetMap attribution. This endpoint does not require an API key and is suitable for JalDrishti's current low-volume development and portfolio use. A production deployment should use a self-hosted or SLA-backed tile service rather than depend on the community tile servers.
