"""The store interface (DS11): the only module that talks to Postgres."""
import json
import os

import psycopg2
from psycopg2.extras import execute_values

ROOT = os.path.join(os.path.dirname(__file__), "..")


def connect():
    return psycopg2.connect(os.environ["GRIDFLEX_DB_URL"])


def load_registry():
    """data/hubs.json -> grids and hubs tables (upsert)."""
    reg = json.load(open(os.path.join(ROOT, "data", "hubs.json")))
    with connect() as c, c.cursor() as cur:
        for g in reg["grids"]:
            cur.execute(
                """INSERT INTO grids (id, name, eia_code, type, tier, official_forecast_source)
                   VALUES (%(id)s, %(name)s, %(eia_code)s, %(type)s, %(tier)s, %(official_forecast_source)s)
                   ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, eia_code=EXCLUDED.eia_code, type=EXCLUDED.type,
                   tier=EXCLUDED.tier, official_forecast_source=EXCLUDED.official_forecast_source""", g)
        for h in reg["hubs"]:
            cur.execute(
                """INSERT INTO hubs (id, name, grid_id, serving_utility, lat, lon, load_anchor_mw, headroom_mw, latency_region)
                   VALUES (%(id)s, %(name)s, %(grid)s, %(serving_utility)s, %(lat)s, %(lon)s, %(load_anchor_mw)s, %(headroom_mw)s, %(latency_region)s)
                   ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, grid_id=EXCLUDED.grid_id, serving_utility=EXCLUDED.serving_utility,
                   lat=EXCLUDED.lat, lon=EXCLUDED.lon, load_anchor_mw=EXCLUDED.load_anchor_mw, headroom_mw=EXCLUDED.headroom_mw,
                   latency_region=EXCLUDED.latency_region""", h)


def write_readings(rows):
    """Insert only rows whose value differs from the latest stored one for the same key (DS5, DS9). Returns rows inserted."""
    if not rows:
        return 0
    sql = """
        INSERT INTO readings (grid_id, ts_utc, metric, value, source, quality)
        SELECT v.grid_id, v.ts_utc, v.metric, v.value, v.source, v.quality
        FROM (VALUES %s) AS v(grid_id, ts_utc, metric, value, source, quality)
        LEFT JOIN LATERAL (
          SELECT r.value FROM readings r
          WHERE r.grid_id = v.grid_id AND r.ts_utc = v.ts_utc AND r.metric = v.metric AND r.source = v.source
          ORDER BY r.fetched_at DESC LIMIT 1) l ON true
        WHERE l.value IS DISTINCT FROM v.value
        ON CONFLICT DO NOTHING
        RETURNING 1"""
    template = "(%s, %s::timestamptz, %s, %s::double precision, %s, %s)"
    with connect() as c, c.cursor() as cur:
        return len(execute_values(cur, sql, rows, template=template, page_size=1000, fetch=True))


def read_as_of(grid_id, metric, start, end, asof):
    """Latest value per (hour, source) using only rows fetched at or before `asof`, so scoring never sees the future (DS5)."""
    with connect() as c, c.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (ts_utc, source) ts_utc, source, value, quality FROM readings
               WHERE grid_id=%s AND metric=%s AND ts_utc >= %s AND ts_utc < %s AND fetched_at <= %s
               ORDER BY ts_utc, source, fetched_at DESC""", (grid_id, metric, start, end, asof))
        return cur.fetchall()


def run_started(source, grid_id):
    with connect() as c, c.cursor() as cur:
        cur.execute("INSERT INTO ingest_runs (source, grid_id, status) VALUES (%s, %s, 'running') RETURNING run_id", (source, grid_id))
        return cur.fetchone()[0]


def run_finished(run_id, status, rows_written=None, newest_ts=None, error=None):
    with connect() as c, c.cursor() as cur:
        cur.execute("UPDATE ingest_runs SET status=%s, rows_written=%s, newest_ts=%s, error=%s WHERE run_id=%s",
                    (status, rows_written, newest_ts, error, run_id))


def write_weather(rows):
    """Backfill-safe: an existing (grid, point, product, hour) is left alone. Returns rows inserted."""
    if not rows:
        return 0
    sql = """INSERT INTO weather (grid_id, point, product, valid_ts_utc, ghi, dni, cloud, temp, wind100, wdir100)
             VALUES %s ON CONFLICT DO NOTHING RETURNING 1"""
    with connect() as c, c.cursor() as cur:
        return len(execute_values(cur, sql, rows, template="(%s, %s, %s, %s::timestamptz, %s, %s, %s, %s, %s, %s)", page_size=2000, fetch=True))


def write_weather_forecast(rows):
    """rows: (grid_id, point, issued_at, valid_ts_utc, ghi, dni, cloud, temp, wind100, wdir100)."""
    if not rows:
        return 0
    sql = """INSERT INTO weather_forecasts (grid_id, point, issued_at, valid_ts_utc, ghi, dni, cloud, temp, wind100, wdir100)
             VALUES %s ON CONFLICT DO NOTHING RETURNING 1"""
    with connect() as c, c.cursor() as cur:
        return len(execute_values(cur, sql, rows, template="(%s, %s, %s::timestamptz, %s::timestamptz, %s, %s, %s, %s, %s, %s)", fetch=True))


def write_forecasts(rows):
    """rows: (grid_id, metric, issued_at, target_ts_utc, value, p10, p90, provider, model_version). Re-running an issue is a no-op."""
    if not rows:
        return 0
    sql = """INSERT INTO forecasts (grid_id, metric, issued_at, target_ts_utc, value, p10, p90, provider, model_version)
             VALUES %s ON CONFLICT DO NOTHING RETURNING 1"""
    with connect() as c, c.cursor() as cur:
        return len(execute_values(cur, sql, rows, template="(%s, %s, %s::timestamptz, %s::timestamptz, %s, %s, %s, %s, %s)", fetch=True))
