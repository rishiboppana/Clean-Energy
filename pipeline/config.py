"""Mappings from source codes to our fixed metric list (DS4)."""
import os
from datetime import datetime, timedelta, timezone

# Delayed-live demo clock: the app's "now" runs this many hours behind real time, so every grid has actuals up to "now"
# (EIA fuel mix is 18-22 h late). Everything that asks "what time is it" must call app_now(), never datetime.now().
APP_LAG_HOURS = int(os.environ.get("APP_LAG_HOURS", 24))


def app_now():
    return datetime.now(timezone.utc) - timedelta(hours=APP_LAG_HOURS)


# EIA region-data `type` facet
EIA_REGION_METRICS = {"D": "demand_mw", "DF": "demand_forecast_mw", "TI": "interchange_mw"}

# EIA fuel-type-data `fueltype` facet. Unmapped codes are skipped on purpose:
# BAT, PS, OES (storage, can be negative) and SNB (solar with battery, meaning unclear). Revisit with the surplus rule.
EIA_FUEL_METRICS = {
    "SUN": "gen_solar_mw", "WND": "gen_wind_mw", "WAT": "gen_hydro_mw", "NUC": "gen_nuclear_mw",
    "NG": "gen_gas_mw", "COL": "gen_coal_mw", "OIL": "gen_oil_mw", "OTH": "gen_other_mw", "GEO": "gen_other_mw",
}

# The operator's own forecast is not a measurement (A3)
ESTIMATE_METRICS = {"demand_forecast_mw"}
