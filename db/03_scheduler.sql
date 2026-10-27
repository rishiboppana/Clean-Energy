-- Scheduler tables (specs.md SC12). NOT applied or tested yet: the scheduler (pipeline/scheduler.py) returns plain rows and has no writer.
-- Run by hand against an existing database; docker-entrypoint scripts only run on first init.
CREATE TABLE IF NOT EXISTS jobs (
  job_id text PRIMARY KEY, state text NOT NULL, home_hub text NOT NULL, latency_class text NOT NULL, submitted_at timestamptz NOT NULL,
  deadline_utc timestamptz NOT NULL, power_mw_typ double precision, duration_h_typ double precision, duration_h_max double precision,
  energy_mwh_typ double precision, allowed_grids text, interruptible boolean, placed_hub text, start_hour timestamptz, hours_left double precision);
CREATE TABLE IF NOT EXISTS placements (
  job_id text REFERENCES jobs, hub_id text NOT NULL, hour_utc timestamptz NOT NULL, mw double precision NOT NULL, plan_run_id text,
  PRIMARY KEY (job_id, hour_utc));
CREATE TABLE IF NOT EXISTS ledger_hourly (
  grid_id text NOT NULL, hour_utc timestamptz NOT NULL, surplus_mw_p10 double precision, surplus_mw_p50 double precision, surplus_mw_p90 double precision,
  jobs_mwh double precision, cooling_mwh double precision, filler_mwh double precision, unabsorbed_mwh double precision, unabsorbed_reason text,
  shortfall_mwh double precision, data_quality text, plan_run_id text, PRIMARY KEY (grid_id, hour_utc),
  CHECK (abs(jobs_mwh + cooling_mwh + filler_mwh + unabsorbed_mwh - surplus_mw_p50) < 1e-6));
CREATE TABLE IF NOT EXISTS tank_state (hub_id text NOT NULL, hour_utc timestamptz NOT NULL, level_mwh_th double precision, PRIMARY KEY (hub_id, hour_utc));
