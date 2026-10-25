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

-- Weather per grid sample point (FM2). Wide, not long: ~27M rows long vs ~1M wide for three grids.
-- `product` says which lead time the numbers represent (FB3). Backfill rows have no issue time.
CREATE TABLE IF NOT EXISTS weather (
  grid_id text NOT NULL REFERENCES grids(id),
  point text NOT NULL,
  product text NOT NULL,                 -- historical_forecast (1-12 h) | previous_day1 | previous_day2
  valid_ts_utc timestamptz NOT NULL,
  ghi double precision, dni double precision, cloud double precision,
  temp double precision, wind100 double precision, wdir100 double precision,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (grid_id, point, product, valid_ts_utc)
);

-- Live weather forecasts, archived every fetch with issue time (FM8) so training can later use what we actually had.
CREATE TABLE IF NOT EXISTS weather_forecasts (
  grid_id text NOT NULL REFERENCES grids(id),
  point text NOT NULL,
  issued_at timestamptz NOT NULL,
  valid_ts_utc timestamptz NOT NULL,
  ghi double precision, dni double precision, cloud double precision,
  temp double precision, wind100 double precision, wdir100 double precision,
  PRIMARY KEY (grid_id, point, issued_at, valid_ts_utc)
);

-- Forecasts from any provider, kept for scoring (specs.md section 5). Append-only: each issue is new rows.
CREATE TABLE IF NOT EXISTS forecasts (
  grid_id text NOT NULL REFERENCES grids(id),
  metric text NOT NULL,
  issued_at timestamptz NOT NULL,
  target_ts_utc timestamptz NOT NULL,
  value double precision NOT NULL,       -- p50, MW
  p10 double precision, p90 double precision,
  provider text NOT NULL,                -- xgboost | persistence | official
  model_version text,
  PRIMARY KEY (grid_id, metric, issued_at, target_ts_utc, provider)
);
