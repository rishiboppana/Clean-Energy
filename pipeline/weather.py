"""Open-Meteo extract and normalize for the forecast model's weather features. No database here."""
import requests

HIST = "https://historical-forecast-api.open-meteo.com/v1/forecast"
PREV = "https://previous-runs-api.open-meteo.com/v1/forecast"
# Open-Meteo variable -> weather table column
VARS = {"shortwave_radiation": "ghi", "direct_normal_irradiance": "dni", "cloud_cover": "cloud",
        "temperature_2m": "temp", "wind_speed_100m": "wind100", "wind_direction_100m": "wdir100"}
PRODUCTS = ("historical_forecast", "previous_day1", "previous_day2")


def extract(product, lat, lon, start, end, model):
    """Hourly UTC rows for one point, start/end as 'YYYY-MM-DD'. Returns the API's `hourly` dict keyed by our columns."""
    suffix = "" if product == "historical_forecast" else "_" + product
    params = {"latitude": lat, "longitude": lon, "start_date": start, "end_date": end, "timezone": "UTC",
              "wind_speed_unit": "ms", "models": model, "hourly": ",".join(v + suffix for v in VARS)}
    try:
        r = requests.get(HIST if not suffix else PREV, params=params, timeout=120)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Open-Meteo {product} failed ({type(e).__name__}, status {getattr(e.response, 'status_code', None)})") from None
    h = r.json()["hourly"]
    return {"time": h["time"], **{col: h[v + suffix] for v, col in VARS.items()}}


def normalize(grid_id, point, product, hourly):
    """-> (grid_id, point, product, valid_ts_utc, ghi, dni, cloud, temp, wind100, wdir100). Skips hours with no data at all."""
    cols = list(VARS.values())
    out = []
    for i, t in enumerate(hourly["time"]):
        vals = [hourly[c][i] for c in cols]
        if all(v is None for v in vals):
            continue
        out.append((grid_id, point, product, t + ":00+00", *vals))
    return out


LIVE = "https://api.open-meteo.com/v1/forecast"


def extract_live(lat, lon, model):
    """The current forecast at one point, from 2 days back (the delayed-live clock needs hours before today) through 72 h ahead, in the same columns as `extract`."""
    params = {"latitude": lat, "longitude": lon, "past_days": 2, "forecast_days": 3, "timezone": "UTC", "wind_speed_unit": "ms",
              "models": model, "hourly": ",".join(VARS)}
    try:
        r = requests.get(LIVE, params=params, timeout=60)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Open-Meteo live failed ({type(e).__name__}, status {getattr(e.response, 'status_code', None)})") from None
    h = r.json()["hourly"]
    return {"time": h["time"], **{col: h[v] for v, col in VARS.items()}}
