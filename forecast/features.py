"""Training table for the Phase 1 model (specs.md FB2-FB6): one row per issue time and horizon, built as of the issue time."""
import numpy as np
import pandas as pd
import holidays

from pipeline import store

LAG_H = 24  # newest actual usable at issue time T is T-24h; refine per grid from the probe (FB6)
HORIZONS = np.arange(1, 49)
FUEL_METRIC = {"SUN": "gen_solar_mw", "WND": "gen_wind_mw"}
WX = ["ghi", "dni", "cloud", "temp", "wind100"]
WXF = WX + ["wind3", "wpc"]  # per point, then averaged: wind3 = speed cubed; wpc = turbine power-curve proxy (cut-in 3 m/s, rated 12 m/s, cubic between)  # wdir100 is stored but unused: a circular variable needs sin/cos, not worth it yet
PRODUCT_BY_BUCKET = ["historical_forecast", "previous_day1", "previous_day2"]  # horizons 1-12, 13-36, 37-48 (FB3)
H = np.timedelta64(1, "h")


def load_y(grid, fuel):
    with store.connect() as c, c.cursor() as cur:
        cur.execute("SELECT ts_utc, value FROM readings_latest WHERE grid_id=%s AND metric=%s AND source='eia' ORDER BY ts_utc",
                    (grid, FUEL_METRIC[fuel]))
        rows = cur.fetchall()
    idx = pd.to_datetime([r[0] for r in rows], utc=True).tz_localize(None)
    return pd.Series([r[1] for r in rows], index=idx).clip(lower=0)  # EIA solar dips slightly below 0 at night


def aggregate_weather(df):
    """df: one row per (product, ts, point) with weight `w` and the raw WX columns -> capacity-weighted mean and spread across points."""
    df = df.assign(wind3=df["wind100"] ** 3, wpc=np.clip((df["wind100"] - 3) / 9, 0, 1) ** 3)
    keys = [df["product"], df["ts"]]
    sw = df.groupby(keys)["w"].transform("sum")
    out = df[["product", "ts"]].copy()
    for c in WXF:
        wm = (df[c] * df["w"]).groupby(keys).transform("sum") / sw
        out[f"{c}_m"] = wm
        out[f"{c}_s"] = np.sqrt(((df[c] - wm) ** 2 * df["w"]).groupby(keys).transform("sum") / sw)
    return out.drop_duplicates(["product", "ts"])


def align(frame):
    """Average each hour with the one before it. Open-Meteo stamps an hour by its end and EIA's stamp sits half an hour off, so the mean
    of the two neighbours lines up best (SRP solar MAE 127.8 -> 124.4)."""
    return (frame + frame.set_axis(frame.index + pd.Timedelta(hours=1)).reindex(frame.index)) / 2


def load_wx(grid, points):
    """-> ({product: hourly frame of weighted mean/spread columns}, column names) for a fuel's sample points (FM2, FB4)."""
    weights = {p["id"]: p["weight"] for p in points}
    names = [f"{c}_{s}" for c in WXF for s in ("m", "s")]
    with store.connect() as c, c.cursor() as cur:
        cur.execute(f"SELECT product, valid_ts_utc, point, {', '.join(WX)} FROM weather WHERE grid_id=%s AND point = ANY(%s)", (grid, list(weights)))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["product", "ts", "point"] + WX)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
    df["w"] = df["point"].map(weights)
    agg = aggregate_weather(df)
    return {p: align(g.set_index("ts")[names].astype(float)) for p, g in agg.groupby("product")}, names


def centroid(points):
    w = np.array([p["weight"] for p in points])
    return float(np.average([p["lat"] for p in points], weights=w)), float(np.average([p["lon"] for p in points], weights=w))


def sun_elevation(times, lat, lon):
    """Degrees above the horizon (standard declination and equation-of-time approximation, good to a degree or so)."""
    t = pd.DatetimeIndex(times)
    doy = t.dayofyear.values
    b = np.radians(360 / 364 * (doy - 81))
    eot = 9.87 * np.sin(2 * b) - 7.53 * np.cos(b) - 1.5 * np.sin(b)  # minutes
    decl = np.radians(23.45 * np.sin(np.radians(360 / 365 * (284 + doy))))
    solar_h = t.hour.values + t.minute.values / 60 + lon / 15 + eot / 60
    ha = np.radians(15 * (solar_h - 12))
    la = np.radians(lat)
    return np.degrees(np.arcsin(np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(ha)))


def series_context(y):
    """Hourly actuals plus the as-of-time helpers (trailing p98 cap, 24 h mean) the rows are built from."""
    full = y.reindex(pd.date_range(y.index.min(), y.index.max(), freq="H"))
    # cap: trailing 30 days. Output grew ~20% a year and the sun's season moves the peak, so a short window tracks both (FB2 said 60; 30 scored better)
    return full, full.rolling(30 * 24, min_periods=20 * 24).quantile(0.98), full.rolling(24, min_periods=12).mean()


def rows(ctx, wx, wx_names, T, lat, lon, lag):
    """One row per issue time in T and horizon 1-48. Everything is as of the issue time minus `lag` hours (FB6).
    `wx` maps weather product -> hourly frame; training passes the three lead products, serving passes live forecasts for all three."""
    full, cap_at, mean24 = ctx
    Ti = np.repeat(T.values, len(HORIZONS))
    h = np.tile(HORIZONS, len(T))
    tgt = Ti + h.astype("timedelta64[h]")
    known = Ti - lag * H

    def at(series, times):
        return series.reindex(pd.DatetimeIndex(times)).values

    cap = at(cap_at, known)
    k = np.ceil((h + lag) / 24).astype(int)  # whole days back to the newest same-clock-hour actual we may use
    same = at(full, tgt - k * 24 * H)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            typ = np.nanmean([at(full, tgt - (k + j) * 24 * H) for j in range(7)], axis=0)  # baseline only, not a feature
    last = at(full, known)

    bucket = np.where(h <= 12, 0, np.where(h <= 36, 1, 2))
    W = np.full((len(h), len(wx_names)), np.nan)
    for b, prod in enumerate(PRODUCT_BY_BUCKET):
        m = bucket == b
        if prod in wx:
            W[m] = wx[prod].reindex(pd.DatetimeIndex(tgt[m])).values

    tt = pd.DatetimeIndex(tgt)
    elev = sun_elevation(tgt, lat, lon)
    sin_e = np.sin(np.radians(np.clip(elev, 0.1, 90)))
    cs = np.where(elev > 0, 1098 * sin_e * np.exp(-0.059 / sin_e), 0)  # Haurwitz clear-sky GHI
    ghi = W[:, wx_names.index("ghi_m")]
    with np.errstate(all="ignore"):
        csi = np.where(cs > 50, np.clip(ghi / cs, 0, 1.5), np.nan)
    hol = holidays.US(years=range(tt.year.min(), tt.year.max() + 1))
    ang_h, ang_d = 2 * np.pi * tt.hour.values / 24, 2 * np.pi * tt.dayofyear.values / 365.25

    def ghi_at(shift):
        out = np.full(len(h), np.nan)
        for b, prod in enumerate(PRODUCT_BY_BUCKET):
            m = bucket == b
            if prod in wx:
                out[m] = wx[prod]["ghi_m"].reindex(pd.DatetimeIndex(tgt[m]) + shift).values
        return out

    df = pd.DataFrame(W, columns=wx_names)
    with np.errstate(all="ignore"):
        df = df.assign(
            ghi_prev=ghi_at(-H), ghi_next=ghi_at(H), cs_ghi=cs,
            ghi_temp=ghi * (1 - 0.004 * (W[:, wx_names.index("temp_m")] - 25)),  # panels lose ~0.4% per degree C above 25
            horizon=h, lead_bucket=bucket, hod_sin=np.sin(ang_h), hod_cos=np.cos(ang_h), doy_sin=np.sin(ang_d), doy_cos=np.cos(ang_d),
            dow=tt.dayofweek.values, holiday=[int(d.date() in hol) for d in tt], elev=elev, csi=csi,
            last_share=last / cap, same_share=same / cap, mean24_share=at(mean24, known) / cap,
            issue=Ti, target=tgt, cap=cap, y_mw=at(full, tgt), b_persist=last, b_same=same, b_typical=typ)
        df["label"] = df["y_mw"] / df["cap"]
    return df


def build(grid, fuel, points, lag=LAG_H):
    y = load_y(grid, fuel)
    lat, lon = centroid(points)
    wx, wx_names = load_wx(grid, points)
    first = max(y.index.min(), min(w.index.min() for w in wx.values()))
    T = pd.date_range(first.ceil("6H"), y.index.max(), freq="6H")
    df = rows(series_context(y), wx, wx_names, T, lat, lon, lag)
    return df[df["label"].notna() & (df["cap"] > 0)].reset_index(drop=True)
