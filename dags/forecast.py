"""Forecast DAG (FB10): every 6 hours, one task per grid fetches weather, predicts, writes `forecasts`. Work is in forecast/serve.py."""
import json
from datetime import datetime

from airflow.decorators import dag, task

GRIDS = list(json.load(open("/opt/airflow/data/sample_points.json"))["grids"])  # grids that have a model


@task(retries=2, max_active_tis_per_dag=3)
def forecast(grid):
    from forecast.serve import forecast_grid
    return forecast_grid(grid)


@dag(dag_id="forecast_6h", schedule="0 */6 * * *", start_date=datetime(2026, 10, 1), catchup=False, max_active_runs=1)
def forecast_6h():
    forecast.expand(grid=GRIDS)


forecast_6h()
