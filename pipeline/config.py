"""Mappings from source codes to our fixed metric list (DS4)."""

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
