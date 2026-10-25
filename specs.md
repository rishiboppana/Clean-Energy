# GridFlex specs

Status as of Sat 2026-10-24. **Specification complete (v1).** Personal project, US only, live data required.
Current phase: ready to build. No code has been run yet. `hubs.json` and `probe.py` exist as drafts. `DECISIONS.md` is superseded by this file. The next action is to run `probe.py` (section 16).
Status labels: **Locked** (agreed), **Proposed** (suggested, not yet confirmed), **Deferred** (intentionally later).
Facts marked *(unverified)* come from memory or third-party descriptions and must be confirmed, mostly by running `probe.py`. *(placeholder)* marks a config assumption to calibrate later, and *(checked)* marks something read from a source during the specification work.

**Locked** means the design is agreed. It does not make an unverified fact true. Every *(unverified)* and *(placeholder)* item is listed in section 15.

---

## 1. Product

GridFlex is an AI-assisted scheduler for data centers. A forecasting model predicts when and where surplus renewable power will appear on a grid. The scheduler places flexible compute jobs on hubs of that grid. Any leftover surplus pre-chills a cooling tank or runs low-priority filler work. A ledger accounts for every MWh of surplus.

One line: *we don't create clean energy, we stop wasting it.*

### Honest framing (rule A3, Locked)

- We do not control curtailment. The grid operator decides it. We add demand where and when surplus appears, so curtailment becomes less necessary.
- Energy does not move. Work moves. A job on grid X can only absorb grid X's surplus.
- "Absorbed surplus" is a what-if estimate from replay or simulation, not a measurement.
- Every number on screen is labeled **measured**, **proxy**, **estimate**, **simulated** or **assumption**.
- We never claim any company (including AWS) uses this system or has capacity at these hubs.
- Emissions use grid-average intensity, not marginal. This is stated on screen.
- The project shifts demand. It does not create generation or fix transmission bottlenecks.

### Out of scope for now

- Grid Enhancing Technologies (line ratings, power flow control, reconductoring). Possible later "headroom signal".
- Grid stress state (turning load down when the grid is overloaded). See G1.
- Reinforcement learning (D6). A later experiment against the greedy baseline.
- Non-US grids (H2).

---

## 2. Architecture

```
Sources -> Ingestion (Airflow) -> Store (Postgres) -> Forecast Engine -> Scheduler + Ledger -> API -> Frontend
                                        ^                                     ^
                                  Hub Registry                       Grid Operator Model
                                                                     Job Energy Estimator
```

| # | Component | One job | Status |
|---|---|---|---|
| 1 | Hub Registry | Hubs and grids, as `hubs.json` | Done (v0.1) |
| 2 | Live Data Ingestion | Poll sources on a schedule | Locked, probe pending |
| 3 | Data Store and Normalizer | One hourly UTC schema, remembers what we knew when | Locked |
| 4 | Forecast Engine | Surplus and carbon forecasts, plus nowcast for slow grids | Locked |
| 5 | Job Energy Estimator | Turn a job description into kWh and runtime ranges | Locked |
| 6 | Scheduler and Energy Ledger | Place jobs, account for every MWh | Locked |
| 7 | API Layer | Serve data to the frontend, host the LLM job intake | Locked |
| 8 | Frontend | Globe and flat map, dashboard, chat job flow, pop-up | Locked |
| 9 | Grid Operator Model | Baseline curtailment vs. curtailment with our load | Locked (v1) |

---

## 3. Hub registry (component 1)

Hubs are **modeled clusters of data centers**, not any company's sites. Each hub maps to the grid that serves it. One grid can serve several hubs. The mapping is inferred from public reporting.

Source of truth: `hubs.json`. Loaded into the `grids` and `hubs` tables.

### Decisions

- **H1 (Locked):** build the registry by grouping sites into hubs and mapping each to its grid. No scraping of AWS building lists. Data Center Map lists about 597 AWS entries but states AWS does not publish its locations, so those entries are third-party inference.
- **H2 (Locked):** US first. Other countries later, one data source at a time.
- **H3 (Locked):** ten hubs on eight grids. Phoenix maps to SRP (not APS). Quincy maps to GCPD (not BPA).
- **H4 (Locked):** the scheduler chooses among grids. Hubs are map markers. The three PJM hubs count as one choice, since grid-level data cannot tell them apart.

### Hubs

| Hub id | Name | Serving utility | Grid | Load anchor (MW) | Headroom placeholder (MW) |
|---|---|---|---|---|---|
| nova | Northern Virginia | Dominion Energy | PJM (DOM zone) | none | 1200 |
| columbus | Greater Columbus | AEP Ohio | PJM (AEP zone) | none | 900 |
| chicago | Greater Chicago | ComEd | PJM (COMED zone) | none | 750 (probably too high) |
| dfw | Dallas-Fort Worth | not checked | ERCOT | none | 850 |
| svalley | Silicon Valley (Santa Clara) | Silicon Valley Power / PG&E | CAISO | none | 350 |
| phoenix | Phoenix-Mesa | Salt River Project | SRP | none | 600 |
| iowa | Central Iowa (Altoona) | MidAmerican Energy | MISO | 506 | 450 |
| atlanta | Atlanta Metro (Douglas County) | Georgia Power | SOCO | 980 | 500 |
| quincy | Quincy / Columbia Basin | Grant County PUD | GCPD | 1013 | 400 |
| slc | Salt Lake Valley | Rocky Mountain Power | PACE | none | 350 |

- Load anchors are tracker estimates (DC Hub for Altoona, Datacentres.com for the whole Atlanta metro, Baxtel for the Quincy market). They are not metered use.
- Headroom values are **placeholder assumptions**. They must be replaced with sourced figures. PJM's own zone data suggests Dominion carries about two-thirds of PJM's data center load at the 2025 July peak, which makes Chicago's placeholder look high.
- A West Valley Phoenix hub would sit on APS (balancing authority `AZPS`) and needs its own row if added.

### Grids

| Grid | EIA code *(unverified)* | Type | Freshness tier |
|---|---|---|---|
| PJM | PJM | ISO/RTO | slow |
| ERCOT | ERCO | ISO | fresh |
| CAISO | CISO | ISO | fresh |
| SRP | SRP | utility BA | slow |
| MISO | MISO | ISO | fresh |
| SOCO | SOCO | utility BA | slow |
| GCPD | GCPD | utility BA | slow |
| PACE | PACE | utility BA | slow |

---

## 4. Data sources and freshness (component 2)

### Decisions

- **I1 (Locked):** two-tier ingestion. Direct operator feeds for CAISO, ERCOT and MISO. EIA for every grid as the baseline.
- **I3 (Locked):** freshness is per grid, not one global lag. Slow-tier grids show "estimated" until the daily fuel mix arrives. Every reading carries its source and age.
- **PJM1 (Locked):** PJM uses whatever real data is available. EIA covers PJM's demand and fuel mix, so EIA is the PJM source. PJM's own Data Miner stays optional and private (I6). PJM's three hubs share one grid result (H4).
- **SY1 (Locked): synthetic data as a labeled last resort.** Order for every grid and metric: (1) direct official feed, (2) EIA, (3) nowcast from weather, (4) generic synthetic series. Level (4) is used only when a grid or metric has no usable real data after the probe, so the project still runs end to end.
  - Synthetic series are weather-driven where possible (demand with a daily and seasonal shape scaled to the grid's size, solar and wind from Open-Meteo weather and assumed capacity). All shapes and capacities are config assumptions.
  - They are stored with `quality: simulated` and shown as **Synthetic** everywhere. They are never mixed into measured or proxy figures and never counted in headline totals without that label.
  - The forecast model is **not trained on synthetic data** and no forecast skill is reported for a synthetic grid. Those grids use a seasonal baseline.
  - Hub load (H5) was already synthetic. SY1 extends the same honesty rule to grid data.
- **I4 (Locked, amended by SY1):** slow-tier grids use real EIA hourly demand plus a weather-based nowcast. Synthetic grid data is allowed only as a labeled last-resort fallback (SY1), never in place of data that exists.
- **Delayed-live idea:** the app clock can run behind real time by a lag, so live and replay share one code path. Superseded by per-grid tiers for the lag, but the shared live/replay code path stays.

### What we found

| Source | What we learned | Confidence |
|---|---|---|
| EIA Hourly Electric Grid Monitor | Total demand arrives about one hour after the hour. Most other elements arrived on a one-to-two-day lag in EIA's 2019 note. A third-party write-up says generation by fuel updates once a day. | Partly sourced. The probe measures the real lag. |
| CAISO | OASIS API and Today's Outlook feeds reported anonymous, with 5-minute fuel mix, demand and CO2 as CSV. Curtailment is available (gridstatus library wraps it). | Third-party description *(unverified)* |
| ERCOT | Free registration. Calls need a subscription key plus an ID token. API data starts Dec 2023. Data portal runs about an hour behind. | From ERCOT's docs |
| MISO | One third-party profile says real-time fuel mix, load and prices are anonymous at `public-api.misoenergy.org`. Another says broader data needs an account. | Conflicting *(unverified)* |
| PJM | Data Miner 2 API needs an account. Non-members: 6 connections per minute. Redistribution prohibited without a license. | From PJM's portal. Private use only. |
| BPA | 5-minute load and generation downloads exist. BPA is a neighbor of GCPD, not the same grid, so it is a regional proxy at best. | From BPA's pages |
| SRP, SOCO, GCPD, PACE | No public real-time generation feed found. SRP and PACE take part in CAISO's Western Energy Imbalance Market, so CAISO price data is a possible proxy. | Lead only *(unverified)* |
| Open-Meteo | Free weather forecasts (temperature, cloud cover, wind, irradiance) at any coordinates. Used for the nowcast and forecaster. | Assumed *(probe checks)* |

### Surplus signal

- CAISO: **measured** curtailment.
- Every other grid: **proxy**, from low or negative price, or high renewable share. The UI must say "proxy".

### Source decisions

- **I5 (Locked):** CAISO OASIS and Today's Outlook are in the core pipeline. Curtailment is stored as `curtailment_mwh`.
- **I6 (Locked):** PJM Data Miner is an optional private source behind a config flag, off by default, and not used in anything shown outside the owner's machine. PJM's portal text prohibits redistributing data "contained in or derived from" Data Miner without a license, so read the terms before any hosted use. EIA is PJM's baseline. Zone-level demand (DOM, AEP, COMED) may exist in EIA *(unverified, the probe checks)*.
- **I7 (Locked):** the open-source `gridstatus` library may help extract CAISO, MISO and ERCOT data. It stays behind our own extract functions (DS8). Its current coverage is unverified.
- **F1 (Locked):** each grid in the registry gets an `official_forecast_source` field, filled as an unverified lead (CAISO OASIS renewable forecast, ERCOT solar/wind reports, MISO, PJM). The probe tests each one. A source becomes a forecast provider only after it works. A pasted table of peak output and fuel-mix percentages was not used, because it had no sources.

### Data contract (what the APIs return)

| Source | Returns | Resolution | Covers | Fills metrics |
|---|---|---|---|---|
| EIA | Hourly demand, operator demand forecast, net generation, interchange, generation by fuel, hourly CO2 estimates, subregional demand where available | Hourly | All 8 grids | `demand_mw`, `demand_forecast_mw`, `interchange_mw`, `gen_*_mw` |
| CAISO | Fuel mix, demand, net demand, CO2 (Today's Outlook). Prices and renewable forecasts (OASIS). Curtailment (OASIS or gridstatus). | 5 minutes | CAISO | `gen_*_mw`, `price_usd_mwh`, `curtailment_mwh` |
| ERCOT | Day-ahead and real-time prices, load, generation mix, possibly wind/solar forecasts | 15 minutes (real-time prices), hourly otherwise | ERCOT | `price_usd_mwh`, `demand_mw`, `gen_*_mw` |
| MISO | Real-time fuel mix, load, prices | About 5 minutes | MISO | `gen_*_mw`, `demand_mw`, `price_usd_mwh` |
| Open-Meteo | Temperature, cloud cover, 100 m wind speed, solar radiation. Four APIs: live forecast, Historical Forecast (from about 2022), Previous Model Runs (forecasts issued 1 to 7 days earlier, most models archived from January 2024), and the ERA5 archive. | Hourly | Any coordinates | `weather` table |

Gaps:

- Measured curtailment exists only for CAISO.
- All data is grid-wide, never per hub.
- Only average emissions are available, not marginal.
- SRP, SOCO, GCPD and PACE have no known market price, so the price proxy may not exist for them.
- Slow-tier grids get hourly demand but a late fuel mix.

### Probe

`probe.py` tests each source, prints the age of the newest reading and saves `probe_results.json`. It needs `EIA_API_KEY`. ERCOT credentials are optional. It has not been run yet. Several URLs inside it are unverified, and the ERCOT login there sends token parameters in the request body while ERCOT's guide puts them in the URL.

---

## 5. Data store (component 3)

### Decisions

| # | Decision | Status |
|---|---|---|
| DS1 | **Postgres** is the data store. Reverses the earlier SQLite idea, since Airflow already needs Postgres, parallel writes work, SQLite on mounted Docker volumes may be slow or lock on a Mac *(unverified)*, and AWS later means RDS. | Locked (confirmed) |
| DS2 | Long table format: one row per grid, hour, metric and source. New sources need no schema change. | Locked |
| DS3 | Hourly resolution, UTC. 5-minute feeds are averaged to the hour. Sub-hour detail is lost in v1. | Locked |
| DS4 | Fixed metric list, with a config file mapping each source's fuel names to it. | Locked |
| DS5 | Append-only. Never overwrite. A "latest" view and an "as of T" query on `fetched_at`. | Locked |
| DS6 | Carbon intensity is computed at read time from fuel mix and an emission-factor config file. Not stored. | Locked |
| UTC | All timestamps are `timestamptz` in UTC. Hub time zones are for display and day/night only. | Locked |

### Tables (v1)

| Table | Purpose | Key columns |
|---|---|---|
| `grids`, `hubs` | Reference data from `hubs.json` | ids, EIA code, tier, coordinates, headroom |
| `readings` | Grid measurements, append-only | `grid_id, ts_utc, metric, value, source, fetched_at, quality` |
| `weather` | Weather per hub, observed and forecast | `hub_id, valid_ts_utc, issued_at, metric, value` |
| `forecasts` | Forecasts from any provider, kept for scoring | `grid_id, metric, issued_at, target_ts_utc, value, p10, p90, provider, model_version` |
| `ingest_runs` | One row per extraction attempt | `run_id, source, grid_id, started_at, status, rows_written, newest_ts, error` |

Tables added by later components (created in the same `schema.sql`, built in the order of section 16):

| Table | Added by | Purpose |
|---|---|---|
| `hub_load_synthetic` | H5 | Synthetic hub baseline load (fixed random seed for reproducibility) |
| `jobs`, `placements` | Scheduler (SC12) | Jobs and where and when they run |
| `ledger_hourly` | Scheduler (SC11) | Surplus accounting per grid and hour |
| `tank_state` | Scheduler (SC12) | Cooling tank level per hub and hour |
| `grid_state` | Grid model (G2 to G7) | State, baseline, with-load and absorbed per grid and hour |
| `plan_runs` | API (AP16) | Plan run id, status, failed check, latest-successful pointer |
| `replay_runs` | API (AP9) | Replay runs and their results |
| `idempotency_keys` | API (AP15) | Repeat-request protection |

Synthetic grid series (SY1) are stored in `readings` with `quality = simulated`.

### Metrics

`demand_mw`, `demand_forecast_mw`, `interchange_mw`, `gen_solar_mw`, `gen_wind_mw`, `gen_hydro_mw`, `gen_nuclear_mw`, `gen_gas_mw`, `gen_coal_mw`, `gen_oil_mw`, `gen_other_mw`, `price_usd_mwh`, `curtailment_mwh`, `f_floor_mw` (computed nightly, S3a).

### Rules

- `ts_utc` is the start of the hour. EIA's hour convention (start or end) must be checked against probe output, and not assumed.
- The load step inserts a row only when the value differs from the latest stored value for that key. Re-runs are safe, and a revised number becomes a new row.
- "As of T" picks the latest row with `fetched_at <= T`. This lets forecast scoring avoid using information from the future.
- `weather` and `forecasts` carry `issued_at`, since forecasts change each time they are polled.
- Surplus is a **view**, with a `basis` column (`measured`, `proxy` or `simulated`).
- `ingest_runs` supplies the "data age" shown in the UI.
- Backfill one to two years of history per grid on day one, for forecaster training and replay.

---

## 6. Orchestration

| # | Decision | Status |
|---|---|---|
| DS7 | **Airflow** runs the ETL. Locally on a Mac via Docker Compose, with Postgres as Airflow's own database. `airflow standalone` is an acceptable first-day shortcut. | Locked |
| DS8 | DAGs stay thin. Extract, normalize and load are plain Python functions in a package. Tasks only call them, so the same code can run under cron or Lambda later. | Locked |
| DS9 | Idempotent writes (see store rules). | Locked |
| DS10 | Extraction runs in parallel, one task per grid. With Postgres, parallel loads are also fine. | Locked |
| DS11 | The store sits behind a small interface (`write_readings`, `read_as_of`). | Locked |

- Different schedules per source: CAISO and MISO hourly, EIA fuel mix on its own cadence.
- Airflow catches up on missed runs when the laptop wakes.
- **Hosting:** laptop first, AWS later. Managed Airflow on AWS (MWAA) may have a high monthly floor *(unverified)*. Lighter options are a scheduled Lambda or ECS task, or Airflow in a container on one small server. Postgres moves to RDS.
- The laptop is an M-series Mac (Apple Silicon). To check when we build: that current Airflow Docker images run natively on Apple Silicon *(unverified)*.

---

## 7. Job energy estimator (component 5)

Status: Locked (EE1 to EE12), confirmed by the user. Marks used below: *(checked)* means read from a source during this session. *(placeholder)* means an assumption to calibrate later, not a fact. *(unverified)* means from memory.

### What it does

Input: a job description. Output: the GPU type and count, duration, power draw and energy, each as **minimum / typical / maximum**, plus a list of every value that was assumed instead of given. The scheduler plans with the typical value and checks headroom with the maximum.

### Two uses

1. **A single user job** (UI job box, LLM-assisted).
2. **A synthetic job population** for simulation. One 8-GPU fine-tune draws only a few kW (see the worked example), while hub headroom is hundreds of MW. Absorbing 1 MW takes about 160 such jobs at once, so the simulation needs hundreds or thousands of generated jobs sized to each hub's flexible load (H5). The estimator must therefore be cheap and work on many jobs at once. The job-size mix is decided in the scheduler spec.

### Inputs

| Field | Example | Needed |
|---|---|---|
| Job type | fine-tune | Always |
| Model parameters N | 7 billion | ML jobs |
| Tokens D (dataset tokens times epochs) | 150 million | Training and fine-tuning |
| Input tokens and output tokens | 2,000 and 500 per request, times request count | Inference |
| GPU type and count | H100 x 8 | Optional, defaults from a table |
| Server-hours or data size | 40 server-hours | Non-ML jobs |
| Direct GPU-hours | 64 GPU-hours | Alternative to everything above |
| Deadline (UTC) | 2026-10-25 20:00 | Always |
| Interruptible | no | Default no |
| Allowed grids (privacy) | all | Default all |
| Data size (GB) | 200 | Optional |

The LLM job box (D4) only fills these fields from text. It never supplies constants such as utilization, and missing values are asked for or defaulted from config and shown as "assumed".

### Formulas

- Training from scratch: `FLOPs = 6 x N x D`. The factor 6 is 2 for the forward pass, 2 for activation gradients and 2 for weight gradients *(checked)*.
- Adapter fine-tuning (frozen base weights): about `4 x N x D`. This is derived by dropping the weight-gradient term from the split above, so it is an approximation that ignores the small adapter cost.
- Full fine-tuning: `6 x N x D`.
- Inference: about `2 x N` FLOPs per token, for both input and output tokens *(forward pass only)*.
- Runtime: `hours = FLOPs / (G x peak FLOPs x MFU x 3600)`. For inference, prefill tokens and decode tokens use different MFU values and the times add.
- IT power: `G x TDP x power_fraction`, in watts per GPU.
- Facility power: `IT power x host_overhead x PUE`.
- Energy: facility power times hours.
- Non-ML jobs: `server-hours x server power x PUE`. Low confidence.
- Direct mode: skip FLOPs and use the given GPU-hours.

Two different "utilizations" must not be mixed up. **MFU** (share of peak compute achieved) sets how long the job runs. **Power fraction** (share of TDP actually drawn) sets how much power it uses.

### Constants

GPUs, v1 supports only these two *(checked on a third-party spec comparison page; confirm against NVIDIA's datasheets)*:

| GPU | TDP | BF16 dense peak |
|---|---|---|
| A100 SXM4 80GB | 400 W | 312 TFLOPS |
| H100 SXM5 80GB | 700 W | 990 TFLOPS |

MFU ranges, from a page describing typical values *(checked)*. The minimum for training is widened below the page's range to cover untuned code *(placeholder)*:

| Job type | Min | Typical | Max | Basis |
|---|---|---|---|---|
| Dense pretraining | 0.25 | 0.40 | 0.55 | Page: well-tuned runs 40 to 55 percent |
| Fine-tuning | 0.25 | 0.40 | 0.50 | Page: 35 to 50 percent |
| Inference prefill | 0.30 | 0.40 | 0.50 | Page: 30 to 50 percent |
| Inference decode | 0.08 | 0.10 | 0.12 | Page: 8 to 12 percent at batch 32 |

The same page says naive eager-mode code can be 3 to 8 percent and mixture-of-experts training 25 to 40 percent. Duration uses the high MFU for the shortest time and the low MFU for the longest.

Power and overhead *(all placeholders)*:

| Quantity | Min | Typical | Max |
|---|---|---|---|
| Power fraction of TDP, training and fine-tuning | 0.5 | 0.7 | 0.9 |
| Power fraction of TDP, inference | 0.3 | 0.5 | 0.7 |
| Host overhead multiplier (CPU, memory, network) | 1.15 | 1.25 | 1.4 |
| PUE | 1.1 | 1.3 | 1.6 |

I could not retrieve a sourced PUE figure. The Uptime Institute's survey page says only that the global average has been stable since 2018, with the numbers behind a login.

The minimum and maximum energy use the all-low and all-high corners, so the range is wide on purpose.

### Worked example (illustrative, using the constants above)

Full fine-tune of a 7B dense model on 150 million tokens, 8 H100s.

- FLOPs: 6 x 7e9 x 1.5e8 = 6.3e18.
- Duration: 27 minutes (MFU 0.50), 33 minutes (0.40), 53 minutes (0.25).
- Facility power, typical: 8 x 700 W x 0.7 x 1.25 x 1.3 = about 6.4 kW.
- Energy: about 1.6 kWh minimum, 3.5 kWh typical, 10 kWh maximum.

### Sanity check

The Llama 2 7B paper reported 184,320 A100-80GB GPU-hours for about 2 trillion tokens *(from memory, verify against the paper)*. The formula gives 6 x 7e9 x 2e12 = 8.4e22 FLOPs, which at 312 TFLOPS and MFU 0.40 is about 187,000 GPU-hours. That is close, but it is one data point with an MFU taken from the typical range and not fitted. It checks the order of magnitude, not the power numbers.

### Output record

`job_id, job_type, gpu_type, gpu_count, duration_h {min, typ, max}, power_kw {min, typ, max}, energy_kwh {min, typ, max}, interruptible, resume_overhead, deadline_utc, allowed_grids, data_gb, assumptions[], confidence`

Confidence is medium for training and fine-tuning with known N and D, low for inference and non-ML jobs, and high only for direct GPU-hours entries (the user supplied the main number).

### Decisions

| # | Decision |
|---|---|
| EE1 | Output the record above, with minimum, typical and maximum values and an explicit assumptions list. |
| EE2 | v1 job types: dense training from scratch, full fine-tuning, adapter fine-tuning, batch inference, CPU or server batch, and direct GPU-hours. Not in v1: mixture-of-experts, image and video generation. |
| EE3 | FLOPs rules: 6ND, about 4ND for adapters, 2N per token for inference. Runtime from FLOPs, GPUs, peak and MFU. |
| EE4 | v1 hardware table has two GPUs, A100 and H100. |
| EE5 | MFU ranges per job type as in the table. |
| EE6 | Energy equals GPUs x TDP x power fraction x hours x host overhead x PUE, reported with corner cases. Power fraction, host overhead and PUE are placeholders. |
| EE7 | GPU count is user-given, otherwise defaults from a size table *(placeholder)*. The estimator warns, but does not block, if weights probably will not fit in GPU memory. |
| EE8 | The power profile is constant while the job runs (a rectangle). The scheduler sees a fixed GPU count and duration. Letting the scheduler trade GPUs against time is deferred. |
| EE9 | Jobs are contiguous unless marked interruptible. An interruptible job may pause and resume on hour boundaries, with a fixed resume overhead *(placeholder)*. |
| EE10 | The LLM fills fields only. Anything missing is defaulted from config and listed in `assumptions`, and the UI shows it as "assumed". |
| EE11 | Check against published runs (the Llama 2 example) now. Calibrate power fraction later by measuring real GPU power with NVML or CodeCarbon on a short rented-GPU run, since a Mac has no NVIDIA GPU. |
| EE12 | One estimator serves both single jobs and the synthetic population, and works on many jobs at once. |

### Limits

- Multi-node communication losses are folded into the MFU range.
- Mixture-of-experts models use more energy than dense models with similar active parameters in one study *(checked)*, so they are excluded for now.
- Inference energy is dominated by decode and grows with output length *(checked)*. Batch size changes it a lot, which the MFU ranges only roughly capture.
- Data transfer energy for moving a job between grids is ignored in v1. Data size only matters for latency and privacy rules.
- Heat load for the cooling model equals IT power.

---

## 8. Hub load and energy attribution

- **H5 (Locked):** hub baseline load is synthetic, anchored to public estimates where they exist, with a flexible-share assumption (start at 20 to 40 percent, labeled an assumption). **Headroom** (extra load a hub can absorb) is separate from baseline load.
  - Baseline: anchor times a utilization curve (mostly flat, small daily swing, some noise).
  - Total facility power: IT load times PUE, which feeds the cooling model.
- **H6 (Locked):** a hub's energy mix is its grid's mix, labeled as grid-average attribution.
  - `hub energy from source s at hour t = hub load(t) x share of s in the grid mix(t)`
  - `hub CO2(t) = hub load(t) x grid carbon intensity(t)`
  - Limits: contracts such as PPAs are not physical flows, local conditions can differ from the grid average, and average is not marginal.

---

## 9. Scheduler and ledger (component 6)

### Cascade (S1, Locked)

For each grid with surplus at hour t, using the combined headroom of its hubs:

1. **Jobs first.** Place pending jobs on the grid's hubs. Rules: least slack first, check privacy (allowed grids), latency class and deadline. Jobs may come from other grids.
2. **Pre-chill.** If headroom remains, charge the cooling tank, up to its size and temperature limit.
3. **Filler work.** If headroom still remains, run low-priority deferrable tasks (backups, re-indexing, batch analytics).
4. **Unabsorbed.** Record the remainder with the reason: *headroom full*, *tank full* or *no eligible work*.

Pre-chill and filler work also draw power, so they count against the same hub headroom as jobs. Cooling is not a fallback for a full hub.

### Constraints

- Surplus is local to its grid.
- Deadlines always win. A job near its deadline is never deferred.
- Privacy and latency rules are hard constraints.
- Ledger invariant: every MWh of surplus lands in exactly one bucket (jobs, cooling, filler, unabsorbed), and the buckets sum to the total.
- The ledger can also report how much extra headroom or storage would capture the unabsorbed remainder. This is a planning output, not a request to the grid.

### Algorithm (S2 and SC1 to SC13, Locked)

Marks as in section 7: *(placeholder)* means a config assumption to tune later.

**Loop (SC1).** Time steps are hourly UTC. Each hour the scheduler re-plans over a 48-hour horizon using the latest forecasts (a rolling plan), commits only the starts due this hour, and leaves later hours open. Plans are cheap to redo, and the forecast improves as the hour gets closer.

**Job record (SC2).** The estimator record from section 7, plus: `submitted_at`, `home_hub` (where it would run with no scheduler), `latency_class`, `state` (pending, scheduled, running, done, home_run, missed, cancelled; transitions in section 12b), `placed_hub`, `start_hour`, `hours_left`.

- Planning uses the **typical** power and duration. The deadline check uses the **maximum** duration, so `latest_start = deadline - duration_max`. Slack is `latest_start - now`.
- Power is held constant for the job's duration (EE8). Load in MW is `power_kw_typ / 1000`.

**Latency classes (SC3).** Three classes, using the hub `latency_region` field *(placeholder rule)*:

| Class | Allowed hubs |
|---|---|
| `local` | home hub only |
| `regional` | home region and neighboring regions (east, central, mountain, west chain) |
| `batch` | anywhere in `allowed_grids` |

Moving data takes `ceil(data_gb x 8 / (bandwidth_gbps x 3600))` hours before the job can start *(bandwidth 10 Gbps, placeholder)*. Moving a job never makes it miss its deadline: the transfer time is added to the start time before the `latest_start` check.

**Candidate slots (SC4).** For each pending job, the candidates are every (hub, start hour) pair where all of these hold:

1. The hub's grid is in `allowed_grids` and the hub is allowed by the latency class.
2. `start_hour` is between the earliest possible start (now plus transfer time) and `latest_start`.
3. The hub has enough unreserved headroom for the job's MW in every hour of the run.
4. **Surplus-only test (SC13):** in every hour of the run, the grid's remaining surplus covers the job's full MW. A slot that fails this test is not a candidate.

**Scoring (SC5).** Every candidate is fully covered by surplus, so its `absorbed_mwh` is the whole job energy (typical power x typical hours). Pick the candidate by these keys in order:

1. Lowest shortfall risk, meaning the widest margin between the P10 surplus and the job's MW over the run.
2. Lowest forecast carbon intensity over the run (computed carbon, DS6).
3. Fewest moves (home hub first).
4. Earliest start.
5. Hub id alphabetical, so results are reproducible.

The P10 and P90 surplus give the band on the absorbed figure.

**Order of work (SC6).** Jobs are placed in order of least slack first (ties by earlier deadline, then by job id). A job placed earlier reserves headroom and surplus, so later jobs see what is left.

**No covered slot (SC7).** If no candidate passes the surplus-only test, the job is **not moved and not scheduled by GridFlex**. While it still has slack it is held and re-checked every hour, since a surplus window may open. At `latest_start` with nothing committed it runs at its home hub as normal load, exactly as it would without GridFlex. It does not appear in the ledger as absorbed, and its state is `home_run`. Deadlines always win. A job that cannot even run at home by its deadline is marked `missed` and reported, never silently dropped.

**Running jobs (SC8).** A non-interruptible job that has started runs to completion on its hub. If actual surplus falls short of the forecast, the uncovered part is recorded as `shortfall_mwh` in the ledger (energy the job drew that was not surplus). The P10 test in SC13 keeps this rare, and the shortfall figure shows how often it happens. An interruptible job runs only in hours the surplus covers. It is paused at an hour boundary when the next hour is not covered, and resumed in a later covered hour with a fixed overhead of 0.25 hours of redone work *(placeholder)*.

**Cooling and filler (SC9).** After jobs are placed for an hour, any surplus left on the grid and any hub headroom left goes to:

1. **Pre-chill:** charge the hub's tank. Charge per hour is limited by the chiller capacity, the free tank room and the remaining headroom. Electricity used is `thermal MWh / COP`, with COP 4 *(placeholder)*.
2. **Filler:** a synthetic backlog of low-priority tasks per hub, up to a filler cap in MW *(placeholder)*.

Each hub has a tank size in thermal MWh and a chiller capacity in MW *(both placeholders)*. The tank discharges in hours without surplus, which lowers that hour's chiller electricity. It is a gauge, not thermodynamics, as before. Heat load equals IT power.

**Unabsorbed (SC10).** The remaining surplus is recorded with exactly one reason: `headroom_full`, `tank_full` or `no_eligible_work`. Where several apply, the first one reached in the cascade order wins.

**Ledger (SC11).** One row per grid and hour in `ledger_hourly`:

`grid_id, hour_utc, surplus_mw_p10, surplus_mw_p50, surplus_mw_p90, jobs_mwh, cooling_mwh, filler_mwh, unabsorbed_mwh, unabsorbed_reason, shortfall_mwh, data_quality`

- `shortfall_mwh` is outside the invariant. It records job energy that was not covered by surplus.
- Invariant: `jobs_mwh + cooling_mwh + filler_mwh + unabsorbed_mwh = surplus (P50) x 1 hour`, checked after every run. A failed check stops the write.
- `data_quality` carries the measured, proxy, estimate or simulated label (A3). Every row is labeled "what-if", not metered.
- Absorbed figures are **simulated** (the scheduler's plan against forecast or replayed surplus), never measured.
- **Move accounting:** the counterfactual for each job is "run at `home_hub` at submission". A move adds load on the destination grid and removes it from the home grid. The ledger reports both sides and the net (DM1).

**Storage (SC12).** New tables in the Postgres store: `jobs`, `placements` (job, hub, start hour, hours, MW, absorbed MWh p10/p50/p90), `ledger_hourly`, `tank_state` (hub, hour, level). The API design (section 12b) adds `plan_runs` (run id, status, failed check, latest-successful pointer), `replay_runs` and `idempotency_keys`. Each run is idempotent: it deletes and rewrites its own plan rows for the horizon (DS9).

**Surplus-only rule (SC13).** GridFlex moves or shifts a job only when surplus alone can power it. The hub's own baseline capacity belongs to the people and workloads of that region, and GridFlex never takes it.

- **Test:** for every hour of the run, using the job's typical MW and its maximum duration, the P10 surplus remaining on the grid (after earlier jobs this plan) is at least the job's MW, and the hub headroom (extra capacity above baseline) is at least the job's MW. P10 is the config default *(coverage quantile, placeholder)*, chosen so the job is rarely left without surplus once started.
- **Cooling and filler** follow the same rule: they draw only surplus left after jobs.
- **Fail:** the job is not moved. It stays with the user's normal path (SC7).
- **Time shift at home** also counts as a GridFlex action, so it needs the same test on the home grid.

### Running modes

- **Live:** an hourly Airflow DAG reads the latest forecasts and demand, runs the scheduler, writes the plan and ledger. Jobs come from the job box and the synthetic generator.
- **Replay:** the same scheduler runs over past hours using the *actual* surplus, to report what would have been absorbed.
- Both modes call the same plain Python function (DS8).

### Synthetic job population

The estimator makes jobs for hubs with no real users (EE12). The generator draws arrivals per hub per hour, job types and sizes from config distributions, and sets deadlines as a random multiple of the duration. The total flexible load is scaled to each hub's flexible share (H5). All values are placeholders and labeled simulated.

### Evaluation

| Policy | Description |
|---|---|
| Run now | Every job starts at submission on its home hub (the counterfactual) |
| Greedy (this design) | S2 as above |
| Oracle | Same algorithm but given the actual surplus instead of forecasts, an upper bound |

Metrics: absorbed MWh and share of surplus absorbed, carbon, moves, deadline misses and constraint violations. Deadline misses and constraint violations must be zero, and the ledger check must pass every run, or the run fails. The gap between Greedy and Oracle measures how much forecast error costs.

### Limits

- The P10 test is strict because surplus bands are wide, so many jobs will stay `home_run`. The share of jobs moved is a reported metric, not a target.
- Greedy does not look ahead across jobs, so it can be beaten by an optimizer. The upgrade path (optimizer, then a learned policy) stays in section 9.
- Surplus is shared by every hub on the grid (three PJM hubs see the same PJM surplus), because free data cannot separate local congestion.
- Headroom, tank, chiller, filler, bandwidth and resume overhead values are placeholders.

---

## 10. Grid operator model (component 9)

**G1 (Locked):** v1 has two states, **Normal** and **Oversupply**.

- It computes baseline curtailment, then recomputes it with our added load. The difference is reported as absorbed.
- CAISO's baseline is measured. Other grids' baselines are modeled estimates.
- Thresholds start as fixed numbers in config. Real signals (demand against the grid's own forecast) come later.
- **Stress state (Deferred):** load backs off when the grid is overloaded. Later milestone.

### Demand layers (DM1)

| Layer | Meaning | Source | Use |
|---|---|---|---|
| Grid demand | Everything the whole balancing area consumes | Measured (EIA, plus direct CAISO/ERCOT/MISO feeds) | Deciding whether there is surplus |
| Hub baseline load | What the hub's data centers draw | Synthetic (H5) | Headroom and cooling load |
| Job load | Extra load we add | Simulated | The scheduler's effect |

- **DM1 (Locked):** surplus detection uses measured grid demand. EIA reports hourly demand for every balancing authority about an hour after the hour ends. Hub load is synthetic and used only for headroom and cooling. Hub baseline load is already inside grid demand.
- **Move accounting (Locked):** when a job moves from grid A to grid B, the model recomputes both grids. Load rises on B and falls on A, and the ledger reports the net. If A also had surplus, moving the job away makes A's surplus larger.
- Scale: hubs are small next to grids. Surplus can be thousands of MW while a hub's headroom is hundreds, so most surplus will be "unabsorbed: headroom full". That is expected.

### Surplus rule (S3 and S3a, Locked)

First-order oversupply per grid and hour:

`surplus_mw = max(0, solar + wind + hydro + nuclear + F - demand - exports)`

- `exports` is net interchange from EIA (sign convention to confirm).
- **`F` is computed the same way for every grid (S3a, Locked).** `F_g` is the p-th percentile of that grid's own hourly fossil generation (coal + natural gas + oil + other, from EIA `fuel-type-data`) over the trailing 365 days. It stands for the output thermal plants rarely go below, a technical-minimum proxy. The fuel codes are *(unverified, the probe lists what each grid reports)*.
- **One global parameter:** the percentile `p` (start at 5 *(placeholder)*). It is tuned once against CAISO's measured curtailment, then frozen and used unchanged for every grid, CAISO included. There is no per-grid hand tuning.
- `F_g` is recomputed nightly and stored as metric `f_floor_mw`, with its window and `p`, so every surplus value can be reproduced.
- Surplus is **measured** only where it can be checked against measured curtailment (CAISO). Everywhere else it is a **proxy**.
- If a grid reports no fossil generation, or too little history (under 90 days), `F_g` is unavailable and the grid falls back under SY1.
- Hydro is treated as available clean supply. Reservoir hydro can be held back, so this overstates surplus on hydro-heavy grids such as GCPD.
- Forecast surplus uses forecast supply and forecast demand, and carries the uncertainty band through. Surplus is a small difference between large numbers, so the band is wide.
- The grid operator, not GridFlex, decides to curtail. Surplus we do not absorb is recorded as unabsorbed.

### Grid operator model detail (G2 to G7, Locked)

The model does not control anything. It answers two questions per grid and hour: is the grid in oversupply, and how much of the surplus would have been wasted without us.

**G2, state.** A grid is in **Oversupply** in an hour when `surplus_mw_p50 >= max(T_abs, T_pct x demand_mw)`, otherwise **Normal**. `T_abs = 50 MW` and `T_pct = 0.5 percent` *(both placeholders)*, set so forecast noise does not flip the state. Stress is deferred.

**G3, baseline curtailment.** What would be wasted with no GridFlex load.
- CAISO: measured `curtailment_mwh`.
- Every other grid: `baseline_curtailment = surplus_mwh` from S3, an **upper bound**, not a measurement. The UI says "surplus available (proxy)", never "curtailed". The grid may have exported, stored or throttled some of it already.

**G4, with-load recomputation.** Add the scheduled load to grid demand and recompute surplus: `surplus_with_load = max(0, surplus - added_load_mw)`.

**G5, absorbed.** `absorbed_mwh = baseline_curtailment - curtailment_with_load` per grid and hour. Because jobs, cooling and filler draw only surplus (SC13), absorbed equals the ledger's `jobs + cooling + filler` and the two are cross-checked every run. A mismatch fails the run.

**G6, move side effect.** When a job leaves its home grid, home demand falls by the job's MW. In an Oversupply hour at home, that raises home surplus. It is reported as a separate line and is **not** counted as absorbed.

**G7, CAISO calibration and checks.** Fit the single global percentile `p` (S3a) against measured CAISO curtailment (correlation and mean absolute error on a time-ordered holdout), then freeze it. Every grid uses the same rule and the same `p`. If the fit is poor, the proxy label stays on every other grid and the CAISO error is shown next to it.

**Outputs.** Table `grid_state(grid_id, hour_utc, state, surplus_mw_p10, p50, p90, baseline_curtailment_mwh, with_load_mwh, absorbed_mwh, data_quality)`.

---

## 11. Forecast engine (component 4)

Revised design. The provider chain (D1) is Locked, since it was the owner's suggestion. Details (FM1 to FM11) are now Locked as well.

- **D1 (Locked):** forecast **supply**, and use the official forecast where one exists. Where one does not, build a model. For each grid and metric the system tries providers in order: official forecast, then our model, then persistence. This also applies at run time, so a failed or stale official feed falls back to the model.
  - Forecast metrics: `gen_solar_mw`, `gen_wind_mw` (hydro and nuclear use persistence) and `demand_mw` (EIA's operator demand forecast, coverage of all eight grids unverified).
  - Surplus is **derived** from forecast supply and demand (S3), not predicted by a separate model trained on proxy labels.
  - Carbon intensity is derived from the forecast mix. The split of remaining demand between gas and coal uses recent shares, a simplifying assumption.
  - Our model: gradient boosting on weather (irradiance, cloud cover, wind speed), hour, day of week and lagged readings. It learns MW directly from history and needs no plant capacity data. Needed mainly for grids without an official feed.
  - Every forecast row records its provider, and every provider is scored against actuals using as-of queries (DS5). Scored against persistence and a perfect-hindsight schedule.
  - Optional: run the model in the background on grids that have official forecasts, to compare the two.
- **Phase 1 (Locked):** XGBoost (LightGBM is an acceptable swap) trained on EIA-930 history and Open-Meteo weather. This is the only model built for now. Data is small (about 17,000 hourly rows per grid and fuel over two years), so it trains on a laptop with no GPU.
- **Phase 2 (Deferred):** a Temporal Fusion Transformer (for example with PyTorch Forecasting) for the 24 to 48 hour forecasts, keeping the gradient-boosted model for fast intraday updates. Revisit only after Phase 1 has been evaluated.
- **Pretrained time-series model (Deferred):** an optional extra provider for comparison, after Phase 1.
- **Targets note:** EIA-930 supplies both load and generation by fuel. Per D1 the main targets are solar and wind output. Load is a fallback target (FM1), used only when EIA's demand forecast is missing.

#### Phase 1 model details (Locked)

| # | Decision |
|---|---|
| FM1 | Targets: solar and wind MW, hourly, up to 48 hours ahead of the last known actual. A temperature-and-calendar demand model is the fallback if EIA's demand forecast is missing. |
| FM2 | Weather is sampled at 3 to 5 points per grid near its generation, not at the hub coordinates. Chosen by hand in v1. |
| FM3 | Features: weather forecast (irradiance, cloud cover, 100 m wind speed, temperature), hour, day of year, day of week, holiday flag, sun height, lagged actuals, capacity level. |
| FM4 | The model predicts share of recent peak (trailing 30 to 90 days), then scales to MW. No plant capacity data needed. |
| FM5 | XGBoost with p10, p50 and p90 outputs (details in FB1). One model per grid and fuel. Horizon is an input. |
| FM6 | Every feature is built as of the issue time, with each grid's real data lag (DS5). Prevents leakage. |
| FM7 | Walk-forward evaluation on two years of history. Baselines: persistence, typical-hour average, official forecast where one exists, perfect hindsight. Metrics: MAE in MW, p10 to p90 coverage (about 80 percent expected), and surplus-hour detection after the surplus rule. No accuracy target until we have data. |
| FM8 | Training weather starts as historical actuals. Archive our own weather forecasts from day one, then compare. Open-Meteo archived forecasts are unverified. |
| FM9 | Retrain weekly through Airflow, version every model, fall back to persistence if error gets too high. |
| FM10 | A grid with no wind or solar series in EIA gets no model. GCPD is likely one (nearly all hydro), so its surplus signal is "not modeled". |
| FM11 | A pretrained time-series model is an optional later provider. The LLM (hosted API, LL1) is used only for the job box and explanations (D4), never for forecasting. |
- Headline AI metric: the share of a perfect-hindsight schedule's benefit that the forecast-driven schedule captured.
- **Uncertainty:** our model outputs quantiles (p10, p90). Official forecasts usually give none, so those fields are empty for them. Where two providers disagree, show the disagreement and make the scheduler more cautious. Blending providers is a later option.
- **Nowcast:** for slow-tier grids, estimate the current hour from the last known fuel mix, EIA demand and weather. Marked "estimated".
- The scheduler plans from forecasts only. The replay scores against actuals, using as-of queries (DS5).

---

### Phase 1 build design (XGBoost)

Status: Locked (FB1 to FB11). Items marked *(checked)* were read from documentation during this session. Items marked *(unverified)* come from memory or third-party descriptions and need the probe or a docs check.

#### Where the data comes from

| Data | Source and route | Notes |
|---|---|---|
| Labels: hourly solar and wind output per grid | EIA API v2, `https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/`. Facets `respondent` (EIA code) and `fueltype` (`SUN`, `WND`; other codes `WAT`, `NG`, `COL`, `NUC`, `OTH`, `OIL`). Parameters `frequency=hourly`, `start`, `end`, up to 5000 rows per request, `offset` for paging. Free API key. *(checked, via a third-party client's README)* | Values are MWh per hour, so about average MW. EIA-930 history starts in 2019. A two-year backfill is a few pages per series. |
| Demand actual and operator demand forecast | EIA `electricity/rto/region-data/data/`, `type` facet `D` (demand) and `DF` (forecast) *(unverified: from memory and the probe script)* | Fallback target (FM1) and an input to the surplus rule (S3) |
| Weather, hours 1 to 12 ahead (training) | Open-Meteo Historical Forecast API, `https://historical-forecast-api.open-meteo.com`, data from about 2022 *(checked)* | Stitches together the first hours of successive model runs, so it behaves like a short-lead forecast, not a 24 to 48 hour one |
| Weather, 24 and 48 hours ahead (training) | Open-Meteo Previous Model Runs API, `https://previous-runs-api.open-meteo.com/v1/forecast`. Variables take a `_previous_day1` to `_previous_day7` suffix. Most models archived from January 2024 *(checked)* | The only source of lead-time-realistic history. It limits full-lead training to about 2.8 years. |
| Weather, live | Open-Meteo Forecast API (`api.open-meteo.com/v1/forecast`) | Every fetch is saved into `weather` with `issued_at` (FM8) |
| Weather, comparison run only | Open-Meteo ERA5 archive (`archive-api.open-meteo.com`, base URL *(unverified)*) | Actual conditions, optimistic. Used once to measure how much a model trained on perfect weather degrades on real forecasts. |

Weather variables per sample point: solar radiation (GHI), direct normal irradiance, cloud cover, temperature, 100 m wind speed, 100 m wind direction. Parameter names are inferred from the documentation's labels and need confirming.

Terms: Open-Meteo offers Non-Commercial, Commercial and Self-Hosted licenses. Its free limits were not found. Personal use looks like the non-commercial case, but read the terms before any hosted or public use.

#### Training table

- **One row per issue time and horizon.** Issue times every 6 hours, horizons 1 to 48 hours. That is about 200,000 rows per grid and fuel over 2.8 years, which is small for XGBoost.
- **Label:** actual output at the target hour divided by `cap`, where `cap` is the 98th percentile of hourly output over the trailing 60 days, computed as of the issue time minus the grid's data lag. A percentile avoids EIA's occasional anomalous values.
- **Weather features at the target hour,** averaged over the grid's sample points, plus the spread across points. Source by horizon: 1 to 12 hours from the Historical Forecast API, 13 to 36 from `previous_day1`, 37 to 48 from `previous_day2`. The lead bucket is itself a feature. One Open-Meteo weather model is pinned so history and live use the same one.
- **Time features:** hour and day of year as sine/cosine, day of week, holiday flag, sun elevation, and clear-sky index (radiation divided by clear-sky radiation).
- **Lag features:** the last known actual share, same hour one day before, and the 24-hour mean of known actuals. Only actuals published by issue time minus lag `L` are allowed. `L` is set per grid from the probe (about a day for slow grids).
- **Horizon** as a feature.

#### Training and validation

- **Model:** `xgboost` 2.0 or later, objective `reg:quantileerror`, `quantile_alpha = [0.1, 0.5, 0.9]`, `tree_method = hist`, `QuantileDMatrix`. One model returns all three quantiles *(checked)*. Quantile crossing can occur, so predictions are sorted after the fact *(checked)*.
- **Starting parameters** (starting points, not tuned results): `max_depth` 6, learning rate 0.05, subsample 0.8, column sample 0.8, early stopping on validation pinball loss.
- **Post-processing:** clip to a sensible range, force solar to zero when the sun is below the horizon, multiply by `cap` to get MW.
- **Validation:** rolling-origin folds by quarter, then a final holdout of the most recent 6 months that includes spring. No tuning on the holdout.
- **Calibration:** measure p10 to p90 coverage by horizon bucket. If it is materially off from about 80 percent, apply a per-bucket widening factor fitted on validation data.
- **Baselines and metrics:** as FM7.

#### Serving and retraining (Airflow)

| DAG | Schedule | Steps |
|---|---|---|
| Forecast | Every 6 hours | Fetch the latest weather forecast at sample points and archive it. Build features as of now. Predict. Write `forecasts` rows with `provider = model` and `model_version`. |
| Scoring | Daily | When actuals arrive, compare every provider's past forecasts with actuals using as-of queries. Write metrics. |
| Training | Weekly | Rebuild the table, refit, evaluate against the current model and the baselines. Promote only if not worse, otherwise keep the current model. Fall back to persistence if error is too high (FM9). |

Artifacts per model: `models/<grid>/<fuel>/<version>/` with the model file, the feature list and a metrics file.

#### Build decisions

| # | Decision |
|---|---|
| FB1 | XGBoost 2.0 or later, `reg:quantileerror`, quantiles 0.1, 0.5, 0.9, one multi-quantile model per grid and fuel. Sort quantiles after prediction. |
| FB2 | Labels come from EIA `fuel-type-data` (`SUN`, `WND`). Targets are shares of a trailing 60-day 98th percentile. |
| FB3 | Weather feeds are mapped to lead buckets (1 to 12 hours, 13 to 36, 37 to 48). One Open-Meteo weather model is pinned. |
| FB4 | 3 to 5 sample points per grid, listed in config. Features are the mean and spread across points. |
| FB5 | Training rows: issue every 6 hours, horizons 1 to 48. |
| FB6 | Lag features may only use actuals published by issue time minus the grid's lag. |
| FB7 | Post-processing: clip, zero solar at night, scale by `cap`. |
| FB8 | Validation: rolling-origin by quarter plus a 6-month holdout that includes spring. |
| FB9 | Calibrate the p10 to p90 band per horizon bucket if coverage is materially off. |
| FB10 | Three Airflow DAGs: forecast, scoring and weekly training, with versioned artifacts and a do-not-regress promotion rule. |
| FB11 | Build order: SRP (solar), PACE (wind and solar) and SOCO (solar) first, then other grids as the probe dictates. The code is generic over a config of grids, fuels and sample points. |

## 12. LLM job box

Locked (D4, LL1 to LL4).

- A user types a plain-English job. The LLM turns it into a structured job (runtime, power, deadline, flexibility, allowed grids) and writes a one-line explanation of the placement.
- The scheduler makes the decision. The LLM can never change the numbers.
- **LL1 (Locked):** the LLM runs through a **hosted API**, not a local model. The call sits behind one function (`llm_complete`), so the provider can change without touching other code. The provider is not chosen yet.
- **LL2:** the API key lives in an environment variable on the server. It never appears in a response, a log or the frontend.
- **LL3:** a usage cap in config (calls per hour and a maximum tokens per call) so a loop or a stuck chat cannot run up a bill. Over the cap, the form parser takes over.
- **LL4:** the regex or form parser stays as the fallback. It handles a missing key, a timeout, the cap, or an invalid LLM answer (AP, parse cases).
- Because the API is hosted, job text leaves the machine. The UI says so next to the chat box, and jobs with a privacy constraint are noted as such in the prompt-free form path (the user can choose "form only").

---

## 12b. API layer (component 7)

Locked (AP1 to AP22), the user moved on to the frontend after reading it. The API is a thin read layer over Postgres. It does not schedule, forecast or estimate on its own. It calls the same plain Python functions the Airflow DAGs call (DS8).

| # | Decision |
|---|---|
| AP1 | Stack: Python and FastAPI, Pydantic models, Postgres through a single data-access module. Same language as the pipeline, so functions are shared. Runs in Docker Compose beside Airflow and Postgres on the Mac, later on AWS. |
| AP2 | Single user, localhost only, no login in v1. Add auth before any hosted use. |
| AP3 | JSON under `/v1`. All times are UTC ISO 8601 (DS3). The frontend converts to local time. |
| AP4 | Every data response carries `asof_utc` and a `quality` label (measured, proxy, estimate, simulated, assumption), so the honesty rule A3 reaches the screen. |
| AP5 | Read-mostly. Data changes hourly, so the frontend polls. No websockets. |
| AP6 | Job flow is four separate calls so the user sees and can correct each step: parse, estimate, preview, submit. |
| AP7 | Preview is a read-only dry run of the scheduler (SC4 to SC7) for one job against current forecasts. It commits nothing and says plainly whether the job passes the surplus-only test. |
| AP8 | The scheduler runs in the hourly Airflow DAG, not in a request. Submitted jobs are picked up at the next run, or immediately if the user presses "plan now", which calls the same function. |
| AP9 | Replay runs are asynchronous. A request returns a `run_id`, results are written under that id and never mix with live rows. |
| AP10 | Errors use one JSON shape with a code and a message. Missing or stale data returns the last good value with its age and `quality: "stale"`, never a silent gap. |

### Conventions (AP11 to AP20)

| # | Decision |
|---|---|
| AP11 | **Success envelope:** `{"data": ..., "meta": {"asof_utc", "quality", "stale", "request_id", "api_version"}}`. `quality` is one of measured, proxy, estimate, simulated, assumption. Rows inside `data` also carry their own `quality` where they differ from the response default. |
| AP12 | **Error envelope:** `{"error": {"code", "message", "details", "request_id"}}`. `code` is a stable machine string (catalog below). The HTTP status follows the code. The frontend switches on `code`, never on message text. |
| AP13 | **Time ranges:** `from` is inclusive and `to` is exclusive, both UTC and aligned to the hour. A misaligned value returns `422 invalid_time_range` with the nearest valid hour in `details`. Default window is the last 48 hours. Maximum is 14 days per request. |
| AP14 | **Lists:** cursor pagination (`limit` default 50, maximum 200, `cursor`). Responses include `next_cursor` or null. |
| AP15 | **Idempotency:** `POST /v1/jobs`, `POST /v1/plan/run` and `POST /v1/replay` accept an `Idempotency-Key` header. A repeat with the same key and body returns the original result. The same key with a different body returns `409 idempotency_conflict`. |
| AP16 | **Consistent reads:** the scheduler writes a plan under a `plan_run_id` and flips a "latest successful run" pointer in one transaction. Plan, ledger and grid-state reads use that pointer, so a user never sees half a plan. A failed run leaves the previous plan in place. |
| AP17 | **Caching:** data changes hourly, so GETs send `ETag` and `Cache-Control: max-age=60`. The frontend sends `If-None-Match` and gets `304` when nothing changed. Estimate and parse results are not cached. |
| AP18 | **Limits:** request body at most 32 KB, `text` at most 2,000 characters, parse timeout 15 s, other requests 5 s. Over the limit returns `413` or `504`. |
| AP19 | **Versioning:** URL prefix `/v1`. Changes within a version only add fields. Removing or renaming a field means `/v2`. The estimator record carries `estimator_version` and `constants_version` so old estimates stay explainable. |
| AP20 | **Validation:** Pydantic rejects unknown enum values and out-of-range numbers before any logic runs (`422 validation_failed`, with per-field details). Ranges are in config and are placeholders. |

### Job states

`pending` (held, waiting for a covered window), `scheduled` (committed slot in the future), `running`, `done`, `home_run` (not covered by surplus, ran at home, SC7), `missed` (could not finish by deadline), `cancelled`. Allowed transitions: pending to scheduled, home_run, missed or cancelled; scheduled to running, pending (if the plan is revised before the start hour) or cancelled; running to done or missed. No other transitions. A job in `running` cannot be cancelled in v1.

### Endpoints in detail

#### Registry and state (read)

| Call | Parameters | Returns | Failure cases |
|---|---|---|---|
| `GET /v1/grids` | none | Per grid: id, name, freshness tier, surplus signal type, `modeled` flag, latest state, latest data age | Never fails on a single bad grid: that grid shows `modeled: false` or `stale: true` with a `reason` |
| `GET /v1/hubs` | `grid_id?` | Per hub: grid, headroom (placeholder label), tank level, attribution label | Unknown `grid_id`: `404 grid_not_found` |
| `GET /v1/grids/{id}/state` | `from`, `to` | `grid_state` rows (G2 to G7) | Unknown id: `404`. Not modeled: `200` with empty rows and `modeled: false`. Window partly missing: rows returned with gaps listed in `meta.missing_hours` |
| `GET /v1/grids/{id}/forecast` | `asof?`, `horizon_h?` (default 48) | Supply, demand and surplus with P10/P50/P90, and `provider` per row (official, own model, persistence) | `asof` in the future: `422`. No forecast at all: `200`, empty, `reason: "no_forecast"`. Persistence provider: bands are null and `quality: "proxy"` |
| `GET /v1/ledger` | `grid?`, `from`, `to` | `ledger_hourly` rows, `invariant_ok` per row | Row failing the sum check never appears in the table (the write is refused). If a gap results, it is listed in `missing_hours` |
| `GET /v1/health` | none | Per source: newest reading, age, verdict; DB reachable; last scheduler run and status; LLM available | Always `200`. Problems are fields, not errors, so the UI can show them. Only a dead process fails |

#### Job flow (write)

The order is **parse, estimate, preview, submit**. Each step is a separate call so the user sees and can correct the result. Steps are independent: the frontend may skip parse and send fields from a form.

**`POST /v1/jobs/parse`**
- Request: `{"text": "..."}`.
- Response: `{"fields": {...}, "assumptions": [...], "needs_input": [...], "parser": "llm" | "form", "confidence"}`.
- `needs_input` lists required fields it could not fill (for example `model_params` for a fine-tune).
- Cases:
  - LLM unreachable or timed out: use the form parser, set `parser: "form"`, return `200` (never fail the job flow because the LLM is down).
  - LLM returns invalid or off-schema JSON: retry once, then fall back to the form parser.
  - LLM returns a value outside configured ranges or an unknown enum: drop the field and add it to `needs_input`. The parser can only fill listed input fields (EE10). It cannot set constants such as MFU, power fraction or PUE. Such keys are ignored and logged.
  - Text that contains instructions aimed at the model: treated as plain data. Output is validated the same way, so it cannot change behavior.
  - Empty or too-long text: `422 validation_failed`.

**`POST /v1/jobs/estimate`**
- Request: the structured fields (parsed or from a form).
- Response: the estimator record (section 7) with min, typical and max, `assumptions[]`, `confidence`, `estimator_version`, `constants_version`, and `warnings[]`.
- Deterministic: the same input returns the same output.
- Cases:
  - Missing required field for the job type: `422 missing_fields` with the list.
  - Unknown GPU type (not A100 or H100): `422 unsupported_hardware`.
  - Unsupported job type (mixture-of-experts, image or video, EE2): `422 unsupported_job_type`.
  - Deadline already past: `422 deadline_in_past`.
  - Weights probably do not fit GPU memory (EE7): `200` with a warning, not an error.
  - Direct GPU-hours given along with N and D: the direct value wins and a warning notes the conflict.
  - Implausible size (more GPUs than any hub's headroom could power): `200` with a warning. The scheduler will find no candidate.

**`POST /v1/jobs/preview`**
- Request: the estimator record (or fields), plus `home_hub`, `latency_class`, `allowed_grids`, `interruptible`.
- Response: `{"verdict", "reasons": [...], "best_slot": {hub, start_utc, end_utc, absorbed_mwh {p10, p50, p90}, carbon_intensity}, "alternatives": [...], "plan_basis_asof", "valid_until"}`.
- Verdicts:

| Verdict | Meaning |
|---|---|
| `covered` | A slot passes the surplus-only test (SC13). Best slot returned |
| `held` | No slot now, but there is slack and a covered window may open. Latest start returned |
| `not_covered` | No slot and no realistic window. The job would run at home |
| `infeasible` | Cannot finish by the deadline even at home using maximum duration |
| `data_unavailable` | Forecast missing or stale for all allowed grids, so the test cannot run. Treated like `not_covered` for safety, with the reason shown |

- Preview is advice, not a reservation. It is read-only and commits nothing. `valid_until` is the next scheduler run. A later submit may get a different verdict, and the response says so.
- Cases: `allowed_grids` empty or all unmodeled: `not_covered` with reason `no_modeled_grid`. Data size makes transfer too long to meet the deadline: that candidate is dropped with reason `transfer_too_slow`.

**`POST /v1/jobs`**
- Request: estimator record, placement inputs, `Idempotency-Key` header.
- Response: `201` with the job (`state: pending`, `job_id`) and the preview verdict at submit time.
- Cases: same key and body returns the original job (`200`). Same key with a different body returns `409 idempotency_conflict`. Estimator record version older than the current one: accepted, flagged `estimate_version_old`. Database unavailable: `503 store_unavailable`, nothing stored, safe to retry.

**`GET /v1/jobs`** and **`GET /v1/jobs/{id}`**
- Job state, placement, absorbed MWh band, shortfall, and the one-line explanation. List filters: `state`, `from`, `to`.
- The explanation is generated from structured scheduler output (the LLM only phrases it). If the LLM is down, a template sentence is used.
- Unknown id: `404 job_not_found`.

**`DELETE /v1/jobs/{id}`** (cancel)
- Allowed in `pending` or `scheduled`. A `running` job returns `409 job_running`. A finished job returns `409 job_final`. Cancelling twice is safe and returns the same result.

#### Plan and replay

**`GET /v1/plan`** returns placements for the latest successful run over the horizon, with `plan_run_id` and `run_time`. If no run has succeeded yet, `200` with empty placements and `reason: "no_plan_yet"`.

**`POST /v1/plan/run`** ("plan now")
- Runs the scheduler once, or returns the run already in progress.
- A run in progress returns `202` with its `plan_run_id` (not a second run). A Postgres advisory lock prevents two runs at once.
- A run that fails leaves the previous plan active and returns `500 plan_failed` with the failed check named (for example `ledger_invariant`).
- Poll `GET /v1/plan/runs/{id}` for status: queued, running, succeeded, failed.

**`POST /v1/replay`**
- Request: `{"from", "to", "policies": ["run_now", "greedy", "oracle"]}`.
- Response: `202` with `run_id`.
- Cases: range over 31 days: `422`. Range with no stored actuals: `422 no_data_for_range`. Another replay running: `409 replay_in_progress`. A policy failing midway: run status `failed` with partial results marked incomplete. Results are immutable under their `run_id` and never mix with live rows.
- **`GET /v1/replay/{run_id}`**: status, progress, results. **`DELETE /v1/replay/{run_id}`** cancels a running replay or removes a finished one.

**`GET /v1/metrics`** returns the evaluation table: absorbed MWh and share by policy, share of jobs moved, carbon, deadline misses, constraint violations, shortfall. Deadline misses or violations above zero are flagged `alert: true`.

### Error catalog

| Code | HTTP | When |
|---|---|---|
| `validation_failed` | 422 | Schema or range check failed |
| `missing_fields` | 422 | Required job field absent |
| `unsupported_hardware`, `unsupported_job_type` | 422 | Outside v1 scope |
| `deadline_in_past` | 422 | Deadline earlier than now |
| `invalid_time_range` | 422 | Misaligned or too wide a window |
| `grid_not_found`, `job_not_found`, `run_not_found` | 404 | Unknown id |
| `idempotency_conflict` | 409 | Same key, different body |
| `job_running`, `job_final` | 409 | Cancel not allowed |
| `replay_in_progress` | 409 | A replay is already running |
| `plan_failed` | 500 | Scheduler run failed a check |
| `store_unavailable` | 503 | Database unreachable. Safe to retry |
| `upstream_timeout` | 504 | LLM or other call over the limit and no fallback |
| `payload_too_large` | 413 | Over the size limit |

Data problems (stale, missing, unmodeled) are **not** errors. They come back as `200` with `stale`, `modeled` or `reason` fields, so the UI can always draw something honest.

### Flows (sequences)

1. **First screen load:** `GET /health`, `GET /grids`, `GET /hubs`, `GET /plan`, then `GET /grids/{id}/state` for the selected grid. The calls are independent and run in parallel.
2. **Submit a job:** parse, estimate (user edits fields and assumptions), preview (user sees verdict and band), submit, then poll `GET /jobs/{id}` every minute until it leaves `pending`.
3. **Cancel:** `DELETE /jobs/{id}`, then refresh the plan.
4. **Live refresh:** poll `/health` and `/grids` every 5 minutes and on tab focus, using `ETag`. The plan changes at most hourly.
5. **Replay:** `POST /replay`, poll status every 5 seconds, then `GET /metrics`.

### Failure and edge-case matrix

| Situation | What the API does | What the user sees |
|---|---|---|
| A source feed is stale | Last good value with age, `stale: true`, quality unchanged | "Estimated, data 3 h old" badge |
| Slow-tier grid, no daily fuel mix yet | Nowcast rows with `quality: "estimate"` | "Estimated" badge |
| Grid not modeled (for example GCPD if the probe says so) | `modeled: false` with reason | Greyed marker with explanation |
| Forecast provider chain falls to persistence | Bands null, `provider: "persistence"` | "Basic forecast, no band" |
| LLM down | Form parser, template explanation | Form-style job box, notice |
| Database down | `503 store_unavailable`, `/health` still `200` | "Data store unavailable, retrying" |
| Scheduler run fails | Previous plan kept, run marked failed | Banner with the failed check |
| Ledger sum check fails | Run refused, nothing written | Same banner |
| Two users or tabs click "plan now" | One run, both get the same `plan_run_id` | Same result |
| Network retry on submit | Idempotency key returns the same job | No duplicate job |
| Preview says covered, submit later says held | Both responses have `plan_basis_asof` | "Forecast changed since preview" note |
| Surplus falls short after a job starts | `shortfall_mwh` on the job and ledger | Shortfall figure on the job card |
| No grid has surplus | `held` or `not_covered` verdicts, no error | "No surplus window found" with the best later option |
| Clock or timezone mismatch | All times UTC. Misaligned input rejected | Local time shown by the frontend |

### Security and operations

- CORS allows only the local frontend origin in v1.
- No secrets (EIA key, ERCOT credentials, LLM key) in any response or log.
- LLM text is treated as untrusted. It is validated against the field schema and escaped before display.
- Each request gets a `request_id`, returned in the response and written to structured logs with duration and status.
- Slow-query and error counts are logged for later review. No external monitoring in v1.

### Iteration plan (AP21)

The API is built in small steps. Each step is usable on its own, and each ends with tests.

| Iteration | Scope | Done when |
|---|---|---|
| I0 | App skeleton, `/health`, envelopes, error handling, request IDs | Health shows real DB and source ages |
| I1 | Registry and state reads: `/grids`, `/hubs`, `/grids/{id}/state`, `/forecast` | Frontend can draw the map and charts from real rows |
| I2 | Job flow: parse (form parser first), estimate, preview, submit, get, cancel | A job goes from text to a verdict end to end |
| I3 | Plan and ledger: `/plan`, `/plan/run`, `/ledger`, consistent reads, locks | Re-running does not duplicate or tear data |
| I4 | LLM parser and explanations with fallbacks | Pulling the LLM out changes nothing but the wording |
| I5 | Replay and metrics | Greedy against oracle table renders |
| I6 | Hardening: caching, limits, idempotency, failure injection | Failure matrix tests pass |

### Testing (AP22)

- **Contract tests** generated from the OpenAPI document: every endpoint, every error code in the catalog.
- **Golden tests** for the estimator: the worked example and the Llama 2 sanity check.
- **Failure injection:** stale source, LLM timeout, bad LLM JSON, database down, scheduler failure, duplicate submit, concurrent "plan now".
- **Invariant tests:** a ledger row that fails its sum never appears. A failed plan run never replaces the previous plan.
- **No mocking of the surplus-only rule:** preview and the scheduler call the same function, and a test asserts they agree.

---

## 13. Frontend (component 8)

Locked (FE1 to FE30), confirmed by the user. Re-decided for the personal project from the user's description. Marks: *(unverified)* means from memory, check before building.

### Screen layout

```
+--------------------------------------------------------------------+
| Space background (dark, stars)                      [Globe | Flat] |
| +-----------+                                          +---------+ |
| | LEFT      |         MAP: globe or flat US            |  CHAT   | |
| | dashboard |    nodes = hubs, red to green            |  with   | |
| | (or node  |    dotted arcs when a job moves          |  the    | |
| |  detail)  |                                          |  LLM    | |
| +-----------+                                          +---------+ |
|              [ time scrubber: now ... +48 h forecast ]            |
+--------------------------------------------------------------------+
        Pop-up (centered): job summary, estimate, destination
```

| # | Decision |
|---|---|
| FE1 | Full-screen dark page with a space background (starfield, soft glow). A "reduce motion" setting turns off the drifting stars and arc animation, and a static gradient is the low-power fallback. |
| FE2 | One map area with two views, **Globe** and **Flat**, switched by a toggle. Both read the same data and the same selection, so switching keeps the selected node, time and open job. The choice is remembered. |
| FE3 | Scope is the US. Globe opens framed on the US and can be rotated. Flat is a US map only. |
| FE4 | **Nodes** are the ten modeled hubs. Their color shows how much extra energy the node can take *now* (or at the scrubbed hour), from red (none) through amber to green (plenty). |
| FE5 | Color value is **absorbable surplus** = `min(remaining grid surplus, remaining hub headroom)` as a share of the hub's headroom. Red is 0 percent and green is 100 percent or more. The three PJM hubs share one grid surplus, so their colors differ only by headroom. |
| FE6 | Color is never the only signal. Each node also has a size or pulse that grows with absorbable MW, and a number on hover and in the legend. A colorblind-safe palette (blue to orange) is a setting. |
| FE7 | Node outline shows data quality: solid for measured, dashed for proxy, dotted for estimated, hatched for synthetic (SY1). A stale feed adds a small clock icon. |
| FE8 | **Time scrubber** at the bottom: now, plus the next 48 hours of forecast. Node colors and the left panel follow the scrubbed hour. Forecast hours are labeled with their band. |
| FE9 | **Left panel** shows the dashboard by default and switches to node detail when a node is selected. Clicking empty space or pressing Escape returns to the dashboard. |
| FE10 | **Right panel** is the chat with the LLM job box. It can be collapsed. |
| FE11 | **Pop-up** after the estimate: job, estimate, destination and time (see below). |
| FE12 | **Dotted animated arcs** show a job moving from its origin node to its destination node, then a confirmation card. |

### Left panel, dashboard (nothing selected)

All numbers carry quality badges (A3).

- **Surplus now** across modeled grids (proxy for most, measured for CAISO), and the same at the scrubbed hour.
- **Absorbed today** in MWh and as a share of surplus, labeled *simulated*, split into jobs, cooling, filler and unabsorbed with reasons (the ledger).
- **Jobs**: moved, held, ran at home, deadline misses (must be 0), shortfall.
- **Top grids** by absorbable surplus, as a ranked bar list.
- **Estimated carbon avoided**, labeled *estimate*, grid-average attribution (H6).
- **Data freshness** table: each source with its age and verdict.
- **Forecast vs actual** for the grid last clicked.
- A footer line: "Hubs are modeled clusters, not any company's sites or capacity. Absorbed figures are simulated what-ifs."

### Left panel, node detail (a node selected)

- Name, grid, state badge (Normal or Oversupply), freshness and quality badge.
- **Surplus** at the selected hour: P50 with the P10 to P90 band, and a 48-hour chart with the band.
- **Absorbable now**: grid surplus remaining, hub headroom remaining (labeled *placeholder*), and which one limits.
- **Cooling tank** gauge and chiller state.
- **Jobs on this node**: running, scheduled, with start and end times.
- **This node's ledger** for the grid: jobs, cooling, filler, unabsorbed with the reason, and the sum check.
- Buttons: "Set as my location" (sets the chat's home hub), "Send a job from here".

### Chat and job flow

The user first picks where they are. The home hub comes from a dropdown, or from "Set as my location" on a node. The app never reads browser location without being asked, and v1 does not need it.

1. The user describes the job in the chat.
2. **Parse** (API `/jobs/parse`). The chat shows a **"What I understood" card** with each field, editable inline, and each filled-in default tagged *assumed*.
3. If something is missing or unclear, the chat asks (see the vague-input rules below).
4. **Estimate** (`/jobs/estimate`), then **Preview** (`/jobs/preview`).
5. The **pop-up** opens.
6. The user clicks **Confirm**, and the app calls `POST /jobs`.
7. The arc animation plays, then the confirmation card.
8. The job appears on the destination node and in the left panel.

#### Handling vague or confusing input (FE13 to FE22)

| # | Rule |
|---|---|
| FE13 | **One question at a time**, in plain words, with **quick-reply chips** (for example "Model size? 1B, 7B, 13B, 70B, Not sure"). No technical jargon without a short explanation. |
| FE14 | **At most three clarifying questions.** After that the app proceeds with defaults, tags each *assumed*, and says what it assumed. The user is never stuck in a question loop. |
| FE15 | **"Not sure" is always an option.** It picks a typical default for that job type, widens the estimate range, and lowers the confidence badge. |
| FE16 | **Ask in the user's terms.** If they do not know tokens, ask about dataset size ("about how many documents, or how many GB?") and convert with a stated assumption (about 4 characters per token for English text *(rule of thumb, unverified)*). The conversion is shown. |
| FE17 | **Shortcut for experts:** "I know my GPU-hours" accepts GPU-hours directly (direct mode, high confidence). |
| FE18 | **Contradictions are named, not guessed.** If the deadline is shorter than the minimum runtime ("finish in 1 hour" for a 6-hour job), the app says so and offers: extend the deadline, change the GPU count (user-chosen, since the scheduler does not trade GPUs for time in v1, EE8), or run at home. |
| FE19 | **Out of scope** (image or video generation, mixture-of-experts): the app says it is not supported in v1 and offers the closest supported job type, or the raw GPU-hours route. |
| FE20 | **Not a job** (greetings, questions about the app): a short answer, then a prompt to describe a job. The chat can explain verdicts and terms but cannot change numbers. |
| FE21 | **Multiple jobs in one message**: handle one at a time, and say "I'll start with the first, then the second." |
| FE22 | **Everything is correctable.** Both the understood-card and the pop-up have editable fields. Editing re-runs estimate and preview, and the old verdict is greyed out until the new one arrives. |

If the LLM is down, the same flow runs from a form (parse falls back, AP and D4). The chat shows a notice and presents the fields as a form.

### Pop-up (FE11 in detail)

Shown after the estimate and preview. Its content:

- **Job:** type, model size, data size, deadline in local time (UTC shown on hover).
- **Estimate:** duration (min, typical, max), energy range in kWh, GPUs, confidence badge. Assumptions listed with *assumed* tags, each editable.
- **Verdict and destination**, one of:

| Verdict | Pop-up shows | Buttons |
|---|---|---|
| `covered` | Destination hub and grid, start and end times (local and UTC), expected surplus coverage with the P10 to P90 band, carbon, transfer time, and the destination highlighted on the map | Confirm and send; Edit; Run at home instead; Cancel |
| `held` | "No surplus window right now. Earliest chance, if the forecast holds: ..." with the latest start | Wait for a window (submit as held); Run at home now; Edit; Cancel |
| `not_covered` | "No surplus window found before your deadline. It will run at your home hub as usual." | Run at home; Edit deadline; Cancel |
| `infeasible` | Why it cannot finish by the deadline, and the options from FE18 | Edit; Cancel |
| `data_unavailable` | Which data is missing or stale, treated as not covered | Run at home; Retry; Cancel |

- A line reads "This is a preview, not a reservation. Forecasts can change before the job starts."
- Quality badges appear on every number.

### Data movement animation (FE12 in detail)

- On **Confirm**, a **dotted line animates from the origin node to the destination node** (dashes flowing along an arc on the globe, along a curve on the flat map).
- Dotted means in transit. When the dots reach the destination the line turns solid, then fades, and a **confirmation card** appears: "Job moved to <hub> (<grid>). Starts <time>, estimated to finish <time>, estimated duration <range>."
- The animation is a few seconds long and is **not** real transfer time. It is labeled *simulated* on the confirmation card, which also gives the computed transfer hours.
- If the job is `scheduled` for a later hour, the arc plays now and the node shows a "scheduled" badge. The node pulses at the actual start time.
- If the job stays at home (`home_run`, `not_covered`), no arc plays and the confirmation says "Running at your home hub."
- While jobs are in flight or running, thin persistent dotted lines can be shown for active moves (toggle).
- A **simulated clock** control (live, or speed up through a replay) lets scheduled jobs be watched without waiting hours. It uses the replay API and is labeled *simulated*.

### Rendering and tools (FE23 to FE30)

| # | Decision |
|---|---|
| FE23 | React, TypeScript and Vite. Hot reload makes UI changes visible instantly. |
| FE24 | **Globe view:** `react-globe.gl` (three.js). It supports points, arcs with animated dashes, and rings *(from memory, verify dashed-arc support before building)*. The globe has a dark surface with US state outlines instead of a photo texture, which avoids texture licensing. |
| FE25 | **Flat view:** an SVG or canvas US map drawn with `d3-geo` (Albers USA projection) from open US state boundaries, with animated `stroke-dasharray` for the dotted lines. No map tiles are needed, so no tile-provider terms apply. |
| FE26 | Both views draw from one shared data store: nodes, arcs, selected hour, selected node. A node or arc is defined once and rendered by each view. |
| FE27 | Data fetching with polling and `ETag` (AP5, AP17): `/health` and `/grids` every 5 minutes and on tab focus, job status every minute while a job is pending. A small store holds UI state (view, selection, scrubber hour, chat). |
| FE28 | Design tokens (colors, glow, arc speed, panel width) live in one file so they can be tweaked live (see tools below). |
| FE29 | Desktop first. Mobile layout is deferred. |
| FE30 | States designed for: loading, stale feed, API down (last data kept, banner), empty (no jobs), no surplus anywhere ("No surplus window found" and the best later option), grid not modeled (greyed node with the reason). |

### Tools to play with the UI

| Tool | Use |
|---|---|
| A clickable mock built by Claude as an interactive page with fake data | Fastest way to try layouts, colors and the pop-up flow before any real code. Tell me the change and I update it. I recommend starting here. |
| Vite with hot reload (FE23) | Edit code and see it change instantly in the browser. |
| Leva or Tweakpane *(from memory)* | Adds on-screen sliders and color pickers to the running app, so glow, arc speed and node size can be tuned live. |
| Storybook | Shows the pop-up, cards and chat bubbles in isolation with a controls panel for every state (covered, held, not covered, error). |
| Browser DevTools | Edit CSS live on the running page. |
| Figma | Static layouts and clickable prototypes, if you want to draw rather than describe. |
| v0, Lovable or Bolt *(from memory)* | AI tools that generate UI from a prompt. Handy for ideas, but the output needs checking against FE1 to FE30 and the API contract. |

### Limits and open items

- Red to green is what you asked for, so FE6 adds backup signals for colorblind users.
- Absorbable surplus uses placeholder headroom values, so node colors are illustrative until those are sourced.
- Globe dashed-arc support, the d3 US boundary data source and its license, and the exact library versions are unverified.
- All animation timing and colors are starting values to tune with the tools above.

---

## 14. Decision register

| # | Decision | Status |
|---|---|---|
| A1 | Product and scope (personal, US, live) | Locked |
| A3 | Honesty rule | Locked |
| H1 to H4 | Registry method, US first, ten hubs on eight grids, scheduler chooses grids | Locked |
| H5, H6 | Synthetic hub load, grid-average attribution | Locked |
| I1, I3, I4 | Two-tier ingestion, per-grid freshness, EIA demand plus nowcast | Locked |
| DS1 | Postgres store | Locked |
| DS2 to DS6 | Long table, hourly UTC, fixed metrics, append-only, computed carbon | Locked |
| DS7 to DS11 | Airflow, thin DAGs, idempotent writes, parallel extract, store interface | Locked |
| S1 | Hourly cascade per grid | Locked |
| S2, SC1 to SC13 | Greedy scheduler: rolling hourly plan, job record, latency classes, candidate slots, scoring and tie-breaks, least-slack order, deadline fallback, running jobs, cooling and filler, unabsorbed reasons, ledger, tables, surplus-only rule | Locked |
| G1 | Grid model v1: Normal and Oversupply | Locked |
| D1 | Supply forecasting with provider chain: official, then our model, then persistence. Surplus derived. | Locked |
| Phase 1 | XGBoost on EIA-930 and Open-Meteo is the only forecast model built for now | Locked |
| Phase 2 | Temporal Fusion Transformer, plus the boosted model for intraday updates | Deferred |
| FM1 to FM11 | Phase 1 model details (targets, weather sampling, features, evaluation, retraining) | Locked |
| FB1 to FB11 | Phase 1 build design: data routes, training table, XGBoost settings, validation, Airflow DAGs, build order | Locked |
| I5, I6, I7 | CAISO in core pipeline; PJM Data Miner optional and private; `gridstatus` as helper | Locked |
| F1 | `official_forecast_source` field per grid, unverified leads tested by the probe | Locked |
| DM1 | Three demand layers: measured grid demand, synthetic hub load, simulated job load | Locked |
| PJM1, SY1 | PJM uses available real data (EIA); synthetic grid data only as a labeled last resort after the probe, never trained on or counted as measured | Locked |
| S3, S3a | Surplus rule. `F` computed the same way for every grid (percentile of trailing fossil generation), one global percentile tuned on CAISO then frozen | Locked |
| EE1 to EE12 | Job energy estimator: record with min/typ/max, v1 job types, FLOPs rules, two GPUs, MFU ranges, power model, defaults, constant power profile, interruptible jobs, LLM fills fields only, calibration plan, one estimator for single and synthetic jobs | Locked |
| D4, LL1 to LL4 | LLM job box through a hosted API, key in environment, usage cap, form parser fallback | Locked |
| FE1 to FE30 | Frontend: space background, globe and flat views, red-to-green nodes with backup signals, time scrubber, left dashboard and node detail, chat job flow with vague-input rules, pop-up, dotted-arc movement and confirmation, rendering stack, tooling | Locked |
| AI1 | Roles: LLM reads input only, plain code estimates, an algorithm schedules, a trained model forecasts. One model for all three was rejected: math and constraints must be exact, testable and cheap. | Locked |
| G2 to G7 | Grid model detail: state thresholds, baseline curtailment (CAISO measured, others upper-bound proxy), with-load recomputation, absorbed, move side effect, CAISO calibration | Locked |
| D6 | No reinforcement learning in v1 | Locked |
| B5, AP1 to AP22 | API system design: FastAPI stack, envelopes, time ranges, pagination, idempotency, consistent plan reads, job states, endpoint detail, error catalog, flows, failure matrix, iterations, tests | Locked |

---

## 15. Open items and risks

- **Run `probe.py`.** It settles which feeds work, how stale each is, the EIA hour convention and whether EIA codes are right.
- **Airflow image compatibility** on Apple Silicon (M-series Mac confirmed).
- **Headroom values** are placeholders and need sources.
- **EIA fuel-mix lag** may be about a day, which makes five of eight grids "estimated" most of the time. The nowcast quality matters a lot.
- **Proxy surplus** for seven of eight grids is weaker than CAISO's measured curtailment. The hardest honesty problem in the project.
- **PJM terms** limit use of PJM's own API to private use.
- **MISO and CAISO access** claims conflict or are third-party only.
- **LLM provider and key** are not chosen yet (LL1). Until then the form parser runs the job box.
- **Surplus attribution inside a grid:** free data cannot show local congestion, so hubs on the same grid look identical on the supply side. Zone-level demand might separate the PJM hubs on the demand side.
- **The floor `F`** is a technical-minimum proxy from past fossil output. It is a consistent rule, not each grid's true must-run level. Only CAISO can check it against measured curtailment.
- **Surplus error:** a few percent error in solar or wind moves surplus a lot, because surplus is a small difference between large numbers. The band must be shown.
- **Exports sign convention** in EIA interchange data needs checking.
- **Open-Meteo terms:** the free-use limits were not found, and the non-commercial license applies to personal use only. Read before any hosted or public use.
- **Weather model pinning:** history and live must come from the same Open-Meteo model, and the available models and their archive start dates differ. The choice is not made yet.
- **Training history is short for full-lead weather:** about 2.8 years (from January 2024) means only a few spring seasons. Spring is when curtailment is highest, so the holdout has little data for it.
- **Sample points** per grid are not chosen. EIA's plant inventory (EIA-860) may give plant coordinates, which is *(unverified)*.
- **EIA `type` facet codes** for demand (`D`, `DF`) are unconfirmed.
- **Scheduler constants:** latency rule, bandwidth, tank size, chiller capacity, COP, filler cap and resume overhead are placeholders.
- **Estimator constants:** power fraction, host overhead, PUE, GPU-count defaults and resume overhead are placeholders. GPU specs came from a third-party page. The Llama 2 GPU-hours figure is from memory.
- **Hosting cost on AWS** unverified.
- **Synthetic fallback (SY1)** is used only after the probe shows a gap. Which grids need it is unknown until the probe runs.
- **Frontend:** globe dashed-arc support, the US boundary data source and its license, and library versions are unverified (section 13).

## 16. Next steps and plan

### Spec work (in order)

| Step | Component | Content | Status |
|---|---|---|---|
| 1 | Job energy estimator (5) | EE1 to EE12 | Done, Locked |
| 2 | Scheduler and ledger (6) | S1, S2, SC1 to SC13 | Done, Locked |
| 3 | Grid operator model (9) | G2 to G7 | Done, Locked |
| 4 | API layer (7) | AP1 to AP22, stack (B5) | Done, Locked |
| 5 | Frontend (8) | FE1 to FE30 | Done, Locked |
| 6 | Final pass | Lock the remaining items (I5 to I7, F1, FM, FB, S3, D4), align text across sections | Done |

### Build plan (the specs are done, so this starts now)

Order follows data dependencies. Each step ends with a check.

1. **Probe.** On your Mac, set the key in the terminal (`export EIA_API_KEY=...`, so it stays out of files and chats) and run `python probe.py` next to `hubs.json`. Keep the key out of this file and out of git. Record feed freshness, EIA codes, hour convention and which grids report solar and wind. Check: every grid has a verdict (fresh, slow or not modeled).
2. **Store and orchestration.** `schema.sql`, Docker Compose for Postgres and Airflow, idempotent writes. Check: re-running a load changes nothing.
3. **Ingestion.** EIA first for all grids, then the CAISO, ERCOT and MISO direct feeds. Check: the readings table fills hourly with correct UTC periods.
4. **Surplus (S3).** Compute `F_g` for every grid with the same rule (S3a), tune the single global percentile on CAISO, then compute surplus from measured data. Check: CAISO surplus tracks measured curtailment.
5. **Forecast (FB1 to FB11).** Training table, XGBoost quantile models, scoring DAG. Check: beats persistence on a time-ordered holdout, with calibrated bands.
6. **Estimator.** A pure function with tests on the worked example and the Llama 2 check. Check: reproduces the hand-calculated numbers.
7. **Scheduler and ledger.** Replay mode first on past hours with actual surplus, then live mode. Check: ledger sum is exact, zero deadline misses, zero constraint violations.
8. **Grid operator model.** Baseline versus with-load curtailment.
9. **API and frontend.**
10. **Calibration.** Measure real GPU power for the estimator (EE11) and source the headroom values.

### Open decisions

None block the probe or the store. They matter later.

- LLM provider and API key (hosted API is decided, LL1). Needed at API iteration I4. Until then the form parser runs the job box.
- The probe's verdict per grid (which grids have usable data and which need the SY1 fallback).
