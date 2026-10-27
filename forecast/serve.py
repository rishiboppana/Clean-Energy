"""Live forecast for one grid: fetch weather, archive it, predict every fuel up to 48 h ahead, write `forecasts` (specs.md FB10)."""
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from forecast import features as F
from forecast import train as T
from pipeline import store, weather

MAX_STALE_H = 72  # newest actual older than this: no forecast from us, the scheduler falls back (FM9, not built yet)


def _live_weather(grid, points, model, issued):
    """Fetch every sample point, archive the raw hourly rows, return the capacity-weighted frame the model expects."""
    parts, archive = [], []
    for p in points:
        h = weather.extract_live(p["lat"], p["lon"], model)
        df = pd.DataFrame({c: h[c] for c in weather.VARS.values()}, index=pd.to_datetime(h["time"]))
        archive += [(grid, p["id"], issued.isoformat(), t.isoformat() + "+00", *[None if pd.isna(v) else float(v) for v in r])
                    for t, r in zip(df.index, df.values)]
        parts.append(df.rename_axis("ts").reset_index().assign(product="live", w=p["weight"]))
    store.write_weather_forecast(archive)
    return F.align(F.aggregate_weather(pd.concat(parts)).set_index("ts")[F_NAMES])


F_NAMES = [f"{c}_{s}" for c in F.WXF for s in ("m", "s")]


def forecast_grid(grid, now=None):
    now = now or datetime.now(timezone.utc)
    issued = pd.Timestamp(now).tz_convert("UTC").tz_localize(None).floor("H")
    root = os.path.join(store.ROOT, "data", "sample_points.json")
    cfg = json.load(open(root))
    written = 0
    for fuel, fcfg in cfg["grids"][grid].items():
        lat, lon = F.centroid(fcfg["points"])
        wx_agg = _live_weather(grid, fcfg["points"], cfg["model"], issued)
        wx = {p: wx_agg for p in F.PRODUCT_BY_BUCKET}  # one live run serves every lead bucket; the bucket stays a feature
        y = F.load_y(grid, fuel)
        age_h = int((issued - y.index.max()) / pd.Timedelta(hours=1))
        if age_h > MAX_STALE_H:
            raise RuntimeError(f"{grid} {fuel}: newest actual is {age_h} h old, over {MAX_STALE_H}")
        lag = max(F.LAG_H, age_h)  # the models trained with at least a day of lag, never less
        df = F.rows(F.series_context(y), wx, F_NAMES, pd.DatetimeIndex([issued]), lat, lon, lag)
        df = df[df["cap"] > 0]
        bst, k, version = T.load_model(grid, fuel)
        mw = T.to_mw(T.widen(T.predict(bst, df), df, k), df, fuel)
        metric = F.FUEL_METRIC[fuel]
        ts = lambda t: pd.Timestamp(t).isoformat() + "+00"
        written += store.write_forecasts([
            (grid, metric, ts(issued), ts(r.target), float(m[1]), float(m[0]), float(m[2]), "xgboost", version)
            for r, m in zip(df.itertuples(), mw)])
    return written
