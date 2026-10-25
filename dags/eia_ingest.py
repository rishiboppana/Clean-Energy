"""Thin DAGs (DS8): the work is in pipeline/. One task per grid (DS10)."""
import json
from datetime import datetime

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context

GRIDS = json.load(open("/opt/airflow/data/hubs.json"))["grids"]
DEFAULTS = {"retries": 2}


@task
def load_registry():
    from pipeline import store
    store.load_registry()


@task(max_active_tis_per_dag=4)
def ingest(grid):
    from pipeline.ingest import ingest_eia
    hours = int(get_current_context()["params"]["hours_back"])
    return ingest_eia(grid["id"], grid["eia_code"], hours)


def _dag(dag_id, schedule, hours_back):
    @dag(dag_id=dag_id, schedule=schedule, start_date=datetime(2026, 10, 1), catchup=False, max_active_runs=1,
         default_args=DEFAULTS, params={"hours_back": hours_back})
    def d():
        load_registry() >> ingest.expand(grid=GRIDS)
    return d()


# Hourly: re-pull 3 days, since EIA fuel mix arrives about a day late and numbers get revised. Idempotent.
eia_hourly = _dag("eia_hourly", "@hourly", 72)
# Manual: trigger with hours_back (default two years) for the day-one backfill.
eia_backfill = _dag("eia_backfill", None, 24 * 730)
