"""EIA API v2: extract and normalize. No database here, so it can be tested alone."""
import os
from datetime import datetime, timezone

import requests

from pipeline.config import EIA_FUEL_METRICS, EIA_REGION_METRICS, ESTIMATE_METRICS

BASE = "https://api.eia.gov/v2/electricity/rto"
PAGE = 5000  # EIA's maximum rows per request


def _key():
    return os.environ["EIA_API_KEY"]


def extract(eia_code, route, start, end):
    """All hourly rows for one respondent between start and end ('YYYY-MM-DDTHH', UTC), paging until done."""
    params = [
        ("api_key", _key()), ("frequency", "hourly"), ("data[0]", "value"),
        ("facets[respondent][]", eia_code), ("start", start), ("end", end),
        ("sort[0][column]", "period"), ("sort[0][direction]", "asc"), ("length", PAGE),
    ]
    if route == "region-data":
        params += [("facets[type][]", t) for t in EIA_REGION_METRICS]
    rows, offset = [], 0
    while True:
        try:
            r = requests.get(f"{BASE}/{route}/data/", params=params + [("offset", offset)], timeout=60)
            r.raise_for_status()
        except requests.RequestException as e:
            # str(e) contains the URL and so the API key: report only type and status
            raise RuntimeError(f"EIA {route} failed ({type(e).__name__}, status {getattr(e.response, 'status_code', None)})") from None
        page = r.json()["response"]["data"]
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def normalize(grid_id, rows):
    """EIA rows -> (grid_id, ts_utc, metric, value, source, quality). Skips unmapped codes and null values."""
    out = []
    for r in rows:
        metric = EIA_REGION_METRICS.get(r.get("type")) or EIA_FUEL_METRICS.get(r.get("fueltype"))
        if metric is None or r.get("value") is None:
            continue
        ts = datetime.strptime(r["period"], "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
        quality = "estimate" if metric in ESTIMATE_METRICS else "measured"
        out.append((grid_id, ts.isoformat(), metric, float(r["value"]), "eia", quality))
    return out
