"""Step 1 of the build plan: which EIA series exist for each grid, and how stale are they?

Reads data/hubs.json and the EIA key from .env (EIA_API_KEY). Writes data/probe_results.json.
Run: python3 pipeline/probe_eia.py
"""
import json
import os
from datetime import datetime, timezone

import requests

ROOT = os.path.join(os.path.dirname(__file__), "..")
BASE = "https://api.eia.gov/v2/electricity/rto"


def load_key():
    # .env line looks like `EIA_API_KEY =value` (spaces around = are tolerated)
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            k, _, v = line.partition("=")
            if k.strip() == "EIA_API_KEY":
                return v.strip().strip('"')
    raise SystemExit("EIA_API_KEY not found in .env")


KEY = load_key()


def get(route, params):
    q = [("api_key", KEY), ("frequency", "hourly"), ("data[0]", "value"),
         ("sort[0][column]", "period"), ("sort[0][direction]", "desc")] + params
    try:
        r = requests.get(f"{BASE}/{route}/data/", params=q, timeout=30)
        r.raise_for_status()
        return r.json()["response"]["data"]
    except requests.RequestException as e:
        # str(e) can contain the URL, which contains the key: print only the type and status
        status = getattr(e.response, "status_code", None)
        raise SystemExit(f"EIA request failed ({type(e).__name__}, status {status}) for {route}")


def age_h(period):
    # period is 'YYYY-MM-DDTHH' in UTC. Start-vs-end of hour convention is still unchecked (specs.md section 5).
    t = datetime.strptime(period, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - t).total_seconds() / 3600, 1)


def newest(code, route, type_code):
    rows = get(route, [("facets[respondent][]", code), ("facets[type][]", type_code), ("length", 1)])
    return {"period": rows[0]["period"], "age_h": age_h(rows[0]["period"])} if rows else None


def probe(grid):
    code = grid["eia_code"]
    demand = newest(code, "region-data", "D")
    fuel_rows = get("fuel-type-data", [("facets[respondent][]", code), ("length", 100)])
    fuels = {}
    for r in fuel_rows:  # rows are newest first, so the first sighting is the newest
        fuels.setdefault(r["fueltype"], r["period"])
    solar_wind = [f for f in ("SUN", "WND") if f in fuels]
    newest_fuel = max(fuels.values()) if fuels else None
    return {
        "grid": grid["id"],
        "eia_code": code,
        "demand": demand,
        "demand_forecast": newest(code, "region-data", "DF"),
        "interchange": newest(code, "region-data", "TI"),
        "fuel_types": sorted(fuels),
        "fuel_newest_period": newest_fuel,
        "fuel_age_h": age_h(newest_fuel) if newest_fuel else None,
        "has_solar_wind": solar_wind,
        # FM10: no wind or solar series means no forecast model
        "modeled": bool(solar_wind),
        "tier_observed": None if not newest_fuel else ("fresh" if age_h(newest_fuel) <= 6 else "slow"),
        "tier_in_registry": grid["tier"],
    }


if __name__ == "__main__":
    grids = json.load(open(os.path.join(ROOT, "data", "hubs.json")))["grids"]
    results = [probe(g) for g in grids]
    out = {"probed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "grids": results}
    json.dump(out, open(os.path.join(ROOT, "data", "probe_results.json"), "w"), indent=2)
    for r in results:
        print(f"{r['grid']:6} demand_age={r['demand'] and r['demand']['age_h']}h  DF={'yes' if r['demand_forecast'] else 'no'}  "
              f"fuel_age={r['fuel_age_h']}h  solar/wind={r['has_solar_wind']}  fuels={r['fuel_types']}")
