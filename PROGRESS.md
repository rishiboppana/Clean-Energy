# Progress

Spec: [specs.md](specs.md). Frontend is built one feature at a time (section 13), on mock data until the API exists.

| # | Feature | Status | Spec |
|---|---|---|---|
| 1 | Vite + React + TS scaffold, repo layout | Done | FE23 |
| 2 | Flat US map, 10 hub nodes, red-to-green by absorbable surplus, quality outlines | Done | FE2, FE4-FE7, FE25 |
| 3 | Globe view + Globe/Flat toggle (choice remembered) | Done | FE2, FE3, FE24, FE26 |
| 4 | Light green land, light blue water | Done | FE28 (tokens) |
| 4b | Realistic globe (Google-Earth-like): NASA Blue Marble imagery, real day/night with city lights and twilight, ocean sun glint, atmosphere, star sky, static clouds, real Sun and Moon directions and phase (`astronomy-engine`), nodes stay vivid. Flat map keeps the green/blue style | Done | FE1, FE24 |
| 5a | Left panel dashboard (all 7 sections + footer, quality badges, click a node to set the forecast chart's grid) | Done, mock data | FE9 |
| 5b | Dynamic left panel: click a node (flat or globe) to show only that node (state, surplus + band, absorbable, tank, jobs, ledger, Set as my location); Escape, Back or empty-map click returns to the dashboard; selected node gets a ring | Done, mock data | FE9 |
| 6 | Time scrubber | Todo | FE8 |
| 7a | Right-hand job box chat: describe job + location, reply with estimate (min/typ/max, assumptions), location dropdown, collapsible. Backend `POST /v1/chat` (agent + estimator), location found by `pipeline/location.py` | Done | FE10 |
| 7a+ | Chat guardrails and interactivity (`pipeline/guardrails.py`, before the LLM): prompt-injection and out-of-scope refusals, off-topic reply, rate limit (30/h per session), server-driven quick-reply chips, "Not sure" and 3-question cap fill labeled defaults, New job button | Done | FE13-FE15, FE19, FE20 |
| 7b | Preview verdict, pop-up, confirm and submit (needs the scheduler), quick-reply chips, editable "what I understood" card | Todo | FE11, FE13-FE22 |
| 8 | Arc animation | Todo | FE12 |
| 9 | Starfield, reduce-motion, colorblind palette, states (loading, stale, API down) | Todo | FE1, FE6, FE30 |

## Data (build plan, specs.md section 16)

| # | Step | Status |
|---|---|---|
| D1 | Hub registry: `data/hubs.json` (8 grids, 10 hubs), frontend reads it | Done |
| D2 | EIA probe: `pipeline/probe_eia.py` -> `data/probe_results.json` | Done (EIA only) |
| D3 | Store: Postgres in Docker Compose, `db/02_schema.sql`, `pipeline/store.py`, idempotent writes | Done |
| D4 | EIA ingestion through Airflow: `eia_hourly` DAG (verified, re-run writes 0 new rows) and `eia_backfill` (2 years, running) | Done, backfill in progress |
| D5 | Direct feeds (CAISO, ERCOT, MISO), probe for those | Next |
| D6 | Surplus rule (S3), F floor, CAISO calibration | Todo |
| D7 | Job energy estimator: `pipeline/estimator.py` (min/typ/max, assumptions, warnings), constants v2 sourced where possible, per-hub GPU fleets `data/hub_gpus.json` (made up), HTTP service `pipeline/estimator_api.py` (threaded, batch endpoint, tested with 200 concurrent calls) | Done |
| D8 | Job box parser: `pipeline/parser.py` (Llama via Hugging Face, validation, grounding, call cap, retry; regex form-parser fallback), `POST /v1/jobs/parse` | Done |
| D9 | Job box agent: `pipeline/agent.py` (LangGraph extract -> respond, Llama 3.1 8B via Hugging Face, per-session memory of chat + collected job). Friendly persona prompt (stays on job estimates, declines off-topic, can explain the estimate); estimate numbers come from the estimator, never the LLM, and any reply with a number it wasn't given is replaced by plain text. Needs `.venv-agent` (Python 3.12). Parser now uses Llama too (replaces the Anthropic call), with grounding checks. Tested live on HF | Done (CLI only; no HTTP chat endpoint yet) |

## Forecast engine (specs.md section 11, FB1-FB11)

| # | Step | Status |
|---|---|---|
| M0 | Weather: `weather` and `weather_forecasts` tables, Open-Meteo backfill (3 lead products, `gfs_seamless`), sample points from EIA-860M plants weighted by capacity (`forecast/sample_points.py` -> `data/sample_points.json`) | Done (SRP, PACE, SOCO) |
| M1 | Training table `forecast/features.py`, trainer `forecast/train.py` (XGBoost p10/p50/p90, band widening FB9), season-stratified split `forecast/split.py`, Ray Tune `forecast/tune.py` | Done |
| M2 | Accuracy, forward holdout from 2026-04-25, MAE as % of mean output: SRP SUN 13.6%, SOCO SUN 27.7%, PACE SUN 12.4%, PACE WND 35.6% (first version: 14.1 / 29.6 / 15.6 / 41.6). Gains from capacity-weighted points, half-hour weather alignment, 30-day cap, cubed wind. Tuning gave nothing once these were in. With observed (ERA5) weather SRP is still ~119 MW, so the rest is mostly plant and data noise | Done |
| M3 | Live path: `forecast/serve.py` (fetch and archive weather, predict 48 h, write `forecasts`), DAG `forecast_6h` (`airflow dags test forecast_6h` passes in the container). Production models come from `python -m forecast.train GRID FUEL final`, pointer `models/<grid>/<fuel>/current.txt` | Done |
| M4 | Scoring DAG (forecast vs actual, as-of queries), weekly training DAG with do-not-regress promotion, fall back to persistence when stale or erroring | Next |
| M5 | Wind (largest error) and SOCO: more weather models, curtailment signals. Other grids (PJM, ERCOT, MISO, CAISO) | Todo |

Run: `PYTHONPATH=. GRIDFLEX_DB_URL=postgresql://gridflex:gridflex@localhost:5432/gridflex ~/.gridflex-venv/bin/python -m forecast.train SRP SUN` (use `~/.gridflex-venv`, not `.venv`: Ray breaks on the space in the project path, and libomp is patched into that venv's xgboost). The Airflow container installs `numpy<2 xgboost holidays` at start (dev only).

Probe findings: all 8 EIA codes valid; demand ~1-2 h old with operator forecast (DF) on every grid; fuel mix ~19-22 h old on every grid (so all are "slow" on EIA alone, direct feeds matter for CAISO/ERCOT/MISO); GCPD reports hydro only (not modeled, FM10); extra fuel codes BAT, GEO, PS, SNB, OES need a mapping (DS4). Still open: EIA hour-start vs hour-end convention.

Textures in `frontend/public/textures`: Earth day/night/water/sky from three-globe's examples (NASA Blue Marble based), Moon and clouds from the three.js examples (their exact licenses are unchecked; fine for a personal project, verify before any public use).

Known gaps: dashboard "same at the scrubbed hour" waits for the scrubber (6); quality outlines (FE7) show on flat only; time not yet shared between views; globe dashed arcs unverified.

Data stack: `docker compose up -d`, then Airflow UI at http://localhost:8080 (user `admin`, password: `docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt`). Tests: `python3 -m unittest tests.test_eia tests.test_estimator tests.test_parser tests.test_location tests.test_guardrails`. Agent: `.venv-agent/bin/python -m pipeline.agent`. Estimator + chat service (run this for the job box): `.venv-agent/bin/python -m pipeline.estimator_api 8000`; the frontend proxies `/v1` to it.

Run frontend: `cd frontend && npm install && npm run dev`
