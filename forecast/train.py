"""Train and evaluate one (grid, fuel) model: python -m forecast.train SRP SUN. Specs.md FB1, FB7-FB9."""
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import xgboost as xgb

from forecast.features import build, WX
from pipeline import store

FEATURES = [f"{c}_{s}" for c in WX for s in ("m", "s")] + [
    "horizon", "lead_bucket", "hod_sin", "hod_cos", "doy_sin", "doy_cos", "dow", "holiday", "elev", "csi",
    "last_share", "same_share", "mean24_share"]
QUANTILES = np.array([0.1, 0.5, 0.9])
PARAMS = {"objective": "reg:quantileerror", "quantile_alpha": QUANTILES, "tree_method": "hist", "max_depth": 6,
          "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8}
# Time-ordered split (FB8, simplified): the last 6 months, which include spring, are the untouched holdout.
# shortcut: one validation window instead of rolling-origin folds by quarter, upgrade once there is more than ~1 year of training data.
HOLDOUT_START, VAL_START, GAP = "2026-04-25", "2026-01-25", pd.Timedelta(days=2)  # gap > 48 h so labels never straddle a split


def predict(bst, df):
    p = np.sort(bst.predict(xgb.DMatrix(df[FEATURES]), iteration_range=(0, bst.best_iteration + 1)), axis=1)  # no quantile crossing
    return np.clip(p, 0, 1.5)


def fit_widening(p, df, fuel):
    """FB9: per lead bucket, the factor k that widens the band around p50 until it covers 80% of validation actuals."""
    y = df["label"].values
    lo, mid, hi = p[:, 0], p[:, 1], p[:, 2]
    need = np.where(y < mid, (mid - y) / np.maximum(mid - lo, 1e-3), (y - mid) / np.maximum(hi - mid, 1e-3))  # k at which row i is covered
    day = (df["elev"].values > 0) if fuel == "SUN" else np.ones(len(df), bool)
    return [float(np.percentile(need[day & (df["lead_bucket"].values == b)], 80)) for b in range(3)]


def widen(p, df, k):
    f = np.array(k)[df["lead_bucket"].values]
    return np.clip(np.stack([p[:, 1] - (p[:, 1] - p[:, 0]) * f, p[:, 1], p[:, 1] + (p[:, 2] - p[:, 1]) * f], axis=1), 0, 1.5)


def to_mw(p, df, fuel):
    if fuel == "SUN":
        p = p * (df["elev"].values > 0)[:, None]  # no sun, no solar (FB7)
    return p * df["cap"].values[:, None]


def evaluate(df, mw, fuel):
    rows = []
    for name, lo, hi in [("1-12h", 1, 12), ("13-36h", 13, 36), ("37-48h", 37, 48), ("all", 1, 48)]:
        m = (df["horizon"] >= lo) & (df["horizon"] <= hi)
        if fuel == "SUN":
            m &= df["elev"] > 0  # night zeros would flatter every method
        m &= df[["b_persist", "b_same", "b_typical"]].notna().all(axis=1)
        d, p, y = df[m], mw[m.values], df.loc[m, "y_mw"].values
        rows.append({"horizon": name, "n": int(m.sum()), "mae_model": float(np.abs(p[:, 1] - y).mean()),
                     "mae_persistence": float(np.abs(d["b_persist"] - y).mean()), "mae_same_hour_last_day": float(np.abs(d["b_same"] - y).mean()),
                     "mae_typical_hour_7d": float(np.abs(d["b_typical"] - y).mean()),
                     "coverage_p10_p90": float(((y >= p[:, 0]) & (y <= p[:, 2])).mean())})
    return rows


def run(grid, fuel):
    cfg = json.load(open(os.path.join(store.ROOT, "data", "sample_points.json")))["grids"][grid]
    lat = np.mean([p["lat"] for p in cfg["points"]])
    lon = np.mean([p["lon"] for p in cfg["points"]])
    df = build(grid, fuel, lat, lon)
    t = pd.to_datetime(df["issue"])
    tr = df[t < pd.Timestamp(VAL_START) - GAP]
    va = df[(t >= VAL_START) & (t < pd.Timestamp(HOLDOUT_START) - GAP)]
    te = df[t >= HOLDOUT_START]
    print(f"{grid} {fuel}: train {len(tr)} val {len(va)} holdout {len(te)} rows")
    dtr = xgb.QuantileDMatrix(tr[FEATURES], tr["label"])
    dva = xgb.QuantileDMatrix(va[FEATURES], va["label"], ref=dtr)
    bst = xgb.train(PARAMS, dtr, 2000, evals=[(dva, "val")], early_stopping_rounds=50, verbose_eval=False)
    k = fit_widening(predict(bst, va), va, fuel)
    raw = evaluate(te, to_mw(predict(bst, te), te, fuel), fuel)
    cal = evaluate(te, to_mw(widen(predict(bst, te), te, k), te, fuel), fuel)
    for r, c in zip(raw, cal):
        c["coverage_raw"] = r["coverage_p10_p90"]
    metrics = {"grid": grid, "fuel": fuel, "best_iteration": bst.best_iteration, "widening_by_lead_bucket": k,
               "rows": {"train": len(tr), "val": len(va), "holdout": len(te)}, "holdout": cal}
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = os.path.join(store.ROOT, "models", grid, fuel, version)
    os.makedirs(out)
    bst.save_model(os.path.join(out, "model.json"))
    json.dump(FEATURES, open(os.path.join(out, "features.json"), "w"))
    json.dump(metrics, open(os.path.join(out, "metrics.json"), "w"), indent=1)
    print(pd.DataFrame(metrics["holdout"]).round(3).to_string(index=False))
    print("saved", out)
    return metrics


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
