-- v1 tables needed for ingestion (specs.md section 5). Later components add theirs here.
-- All timestamps are timestamptz in UTC. Idempotent, so it is safe to re-apply.

CREATE TABLE IF NOT EXISTS grids (
  id text PRIMARY KEY,
  name text NOT NULL,
  eia_code text NOT NULL,
  type text NOT NULL,
  tier text NOT NULL,
  official_forecast_source text
);

CREATE TABLE IF NOT EXISTS hubs (
  id text PRIMARY KEY,
  name text NOT NULL,
  grid_id text NOT NULL REFERENCES grids(id),
  serving_utility text,
  lat double precision NOT NULL,
  lon double precision NOT NULL,
  load_anchor_mw double precision,
  headroom_mw double precision NOT NULL,  -- placeholder assumption
  latency_region text NOT NULL
);

-- Append-only (DS5). A revised value becomes a new row with a later fetched_at.
CREATE TABLE IF NOT EXISTS readings (
  grid_id text NOT NULL REFERENCES grids(id),
  ts_utc timestamptz NOT NULL,           -- start of the hour (EIA hour convention still unverified)
  metric text NOT NULL,
  value double precision NOT NULL,
  source text NOT NULL,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  quality text NOT NULL,                 -- measured | proxy | estimate | simulated
  PRIMARY KEY (grid_id, ts_utc, metric, source, fetched_at)
);

CREATE OR REPLACE VIEW readings_latest AS
SELECT DISTINCT ON (grid_id, ts_utc, metric, source) *
FROM readings
ORDER BY grid_id, ts_utc, metric, source, fetched_at DESC;

CREATE TABLE IF NOT EXISTS ingest_runs (
  run_id bigserial PRIMARY KEY,
  source text NOT NULL,
  grid_id text,
  started_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL,                  -- running | ok | failed
  rows_written integer,
  newest_ts timestamptz,
  error text
);
