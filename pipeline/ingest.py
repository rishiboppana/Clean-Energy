"""Extract -> normalize -> load for one grid. Called by the Airflow tasks (DS8)."""
from datetime import datetime, timedelta, timezone

from pipeline import eia, store

ROUTES = ("region-data", "fuel-type-data")
WINDOW_DAYS = 30  # keeps memory bounded on backfills


def ingest_eia(grid_id, eia_code, hours_back):
    run = store.run_started("eia", grid_id)
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours_back)
        written, newest = 0, None
        t = start
        while t < end:
            t2 = min(t + timedelta(days=WINDOW_DAYS), end)
            for route in ROUTES:
                rows = eia.normalize(grid_id, eia.extract(eia_code, route, t.strftime("%Y-%m-%dT%H"), t2.strftime("%Y-%m-%dT%H")))
                written += store.write_readings(rows)
                if rows:
                    newest = max(newest or rows[0][1], max(r[1] for r in rows))
            t = t2
        store.run_finished(run, "ok", written, newest)
        return written
    except Exception as e:
        store.run_finished(run, "failed", error=str(e)[:500])
        raise


def ingest_weather(grid_id, start, end):
    """Backfill weather for one grid's sample points, all three lead products. start/end are 'YYYY-MM-DD'."""
    import json, os
    from pipeline import weather
    cfg = json.load(open(os.path.join(store.ROOT, "data", "sample_points.json")))
    run = store.run_started("open-meteo", grid_id)
    try:
        written = 0
        for p in [p for f in cfg["grids"][grid_id].values() for p in f["points"]]:
            for product in weather.PRODUCTS:
                h = weather.extract(product, p["lat"], p["lon"], start, end, cfg["model"])
                written += store.write_weather(weather.normalize(grid_id, p["id"], product, h))
        store.run_finished(run, "ok", written)
        return written
    except Exception as e:
        store.run_finished(run, "failed", error=str(e)[:500])
        raise
