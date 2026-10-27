"""Scheduler and energy ledger (specs.md section 9, SC1-SC13). Plain Python with no I/O (DS8): the same functions serve replay
and live mode, and an Airflow task or the API only has to feed them surplus and jobs.

Each hour `tick` re-plans every open job over a 48 h horizon (SC1), commits the starts due now, runs the cascade jobs -> pre-chill ->
filler -> unabsorbed (S1, SC9, SC10) against the grid's surplus and writes one ledger row per grid. A job is moved or time-shifted only
when surplus alone powers it (SC13: P10 surplus >= its typical MW for every hour of its maximum duration); otherwise it stays with the
user's normal path and runs at home at its latest start (SC7, `home_run`). Deadlines always win.

Inputs
  surplus  {grid: {hour_utc: (p10, p50, p90) MW}}; a forecast for planning and the actual for settling (replay). Real surplus needs
           the surplus rule (specs D6), which is not built, so `synthetic_surplus` makes a labeled stand-in (SY1).
  jobs     `make_job(estimator_record, home_hub, submitted_at, ...)`.
Shortcuts (each is a limit, upgrade when it bites): planning is O(jobs x hubs x horizon x run length) per hour; the forecast is one static table, not
an as-of series; an interruptible job is planned to run only in covered hours but, like others, records a shortfall if actual surplus
falls short instead of pausing mid-run; tank, chiller and filler sizes are placeholders.
"""
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

H1 = timedelta(hours=1)
EPS = 1e-9
REGIONS = ["east", "central", "mountain", "west"]  # SC3 chain; regional = own region or a neighbour in this chain
Q = {"p10": 0, "p50": 1, "p90": 2}
# All placeholders (specs SC3, SC8, SC9, SC13)
CFG = {"horizon_h": 48, "coverage": "p10", "bandwidth_gbps": 10, "resume_overhead_h": 0.25, "cop": 4.0,
       "chiller_share": 0.10, "tank_hours": 4.0, "filler_share": 0.10}  # per hub, as shares of its headroom_mw
STATES = {"pending": {"scheduled", "home_run", "missed", "cancelled"}, "scheduled": {"running", "pending", "cancelled"},
          "running": {"done", "missed"}, "done": set(), "home_run": set(), "missed": set(), "cancelled": set()}
HUBS_PATH = Path(__file__).parent.parent / "data" / "hubs.json"


class LedgerError(AssertionError):
    pass


def floor_h(dt):
    return dt.replace(minute=0, second=0, microsecond=0)


def utc(s):
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def load_hubs(cfg=CFG):
    out = {}
    for h in json.loads(HUBS_PATH.read_text())["hubs"]:
        chill = cfg["chiller_share"] * h["headroom_mw"]
        out[h["id"]] = {"id": h["id"], "grid": h["grid"], "region": h["latency_region"], "headroom": h["headroom_mw"], "chiller_mw": chill,
                        "tank_cap": cfg["tank_hours"] * chill * cfg["cop"], "filler_mw": cfg["filler_share"] * h["headroom_mw"]}
    return out


# ---- Jobs (SC2) ----------------------------------------------------------------------------------------------------

def make_job(rec, home_hub, submitted_at, latency_class="regional", job_id=None):
    """Scheduler job from an estimator record. Plans with typical power and duration, checks deadlines with the maximum (SC2)."""
    return {"job_id": job_id or rec.get("job_id") or f"job-{id(rec)}", "mw": rec["power_kw"]["typ"] / 1000, "dur_typ": rec["duration_h"]["typ"],
            "dur_max": rec["duration_h"]["max"], "energy_mwh": rec["energy_kwh"]["typ"] / 1000, "deadline": utc(rec["deadline_utc"]),
            "allowed_grids": rec.get("allowed_grids") or "all", "data_gb": rec.get("data_gb") or 0, "interruptible": bool(rec.get("interruptible")),
            "home_hub": home_hub, "latency_class": latency_class, "submitted_at": submitted_at, "state": "pending", "placed_hub": None,
            "start_hour": None, "hours_left": rec["duration_h"]["typ"], "plan": None, "draws": {}}


def set_state(job, new):
    if new != job["state"]:
        if new not in STATES[job["state"]]:
            raise ValueError(f"illegal job transition {job['state']} -> {new}")
        job["state"] = new


def latest_start(job):
    return floor_h(job["deadline"] - timedelta(hours=job["dur_max"]))


def _draws(job, hours):
    """MW drawn in each of the hours the job runs; the last hour is partial (typical duration)."""
    left, out = job["dur_typ"], []
    for h in hours:
        out.append((h, job["mw"] * min(1.0, left)))
        left -= 1
        if left <= EPS:
            break
    return out


def allowed_hub(job, hub, home, cfg=CFG):
    if job["allowed_grids"] != "all" and hub["grid"] not in job["allowed_grids"]:
        return False
    if job["latency_class"] == "local":
        return hub["id"] == home["id"]
    if job["latency_class"] == "regional":
        return abs(REGIONS.index(hub["region"]) - REGIONS.index(home["region"])) <= 1
    return True  # batch: anywhere in allowed_grids


def transfer_h(job, cfg=CFG):
    return math.ceil(job["data_gb"] * 8 / (cfg["bandwidth_gbps"] * 3600) - EPS)  # SC3


# ---- Remaining surplus and headroom over the horizon ---------------------------------------------------------------

class Book:
    def __init__(self, surplus, hubs, t0, cfg=CFG):
        end = t0 + cfg["horizon_h"] * H1
        self.q = Q[cfg["coverage"]]
        self.s = {g: {h: list(v) for h, v in hrs.items() if t0 <= h < end} for g, hrs in surplus.items()}
        self.room = {k: {t0 + i * H1: hub["headroom"] for i in range(cfg["horizon_h"])} for k, hub in hubs.items()}

    def covered(self, hub, hour, mw):  # SC13: surplus alone powers it, and the hub has the headroom
        s, room = self.s.get(hub["grid"], {}).get(hour), self.room[hub["id"]].get(hour)
        return s is not None and room is not None and s[self.q] >= mw - EPS and room >= mw - EPS

    def margin(self, hub, hour, mw):
        return self.s[hub["grid"]][hour][self.q] - mw

    def take(self, hub, hour, mw):
        s = self.s.get(hub["grid"], {}).get(hour)
        if s:
            s[:] = [max(0.0, x - mw) for x in s]
        if hour in self.room[hub["id"]]:
            self.room[hub["id"]][hour] -= mw


# ---- Candidate slots and scoring (SC4, SC5) ------------------------------------------------------------------------

def _score(job, hub, home, book, hours, carbon):
    """Lower is better: widest margin, lowest carbon, fewest moves, earliest start, hub id (SC5)."""
    margin = min(book.margin(hub, h, job["mw"]) for h in hours)
    ci = [carbon.get(hub["grid"], {}).get(h, 0.0) for h in hours]
    return (-margin, sum(ci) / len(ci), hub["id"] != home["id"], hours[0], hub["id"])


def best_slot(job, t, book, hubs, carbon=None, cfg=CFG):
    """-> (score, hub, reserved draws [(hour, mw)]) or None. The covered test runs over the maximum duration (SC13)."""
    carbon, home, ls = carbon or {}, hubs[job["home_hub"]], latest_start(job)
    n_test = math.ceil(job["dur_max"] - EPS)
    best = None
    for hub in hubs.values():
        if not allowed_hub(job, hub, home, cfg):
            continue
        moved = hub["id"] != home["id"]
        # Moving data takes time and counts before the latest_start check (SC3). It starts at submission, so re-planning each hour
        # must not keep pushing the start back. shortcut: assumes the transfer can begin at submission, whichever hub wins.
        first = max(t, floor_h(job["submitted_at"]) + transfer_h(job, cfg) * H1) if moved else t
        if job["interruptible"]:
            options = [c for c in [_interruptible(job, hub, first, book, cfg)] if c]
        else:  # SC4: every (hub, start) pair that passes the test is a candidate
            options, h = [], first
            while h <= ls:
                hours = [h + i * H1 for i in range(n_test)]
                if all(book.covered(hub, x, job["mw"]) for x in hours):
                    options.append(_draws(job, hours))
                h += H1
        for cand in options:
            score = _score(job, hub, home, book, [h for h, _ in cand], carbon)
            if best is None or score < best[0]:
                best = (score, hub, cand)
    return best


def _interruptible(job, hub, first, book, cfg):
    """Run only in covered hours; each resume after a gap costs resume_overhead_h of redone work (EE9, SC8). Feasible if the
    maximum work fits before the deadline; reserves the hours the typical work needs."""
    need_max, need_typ, prev = job["dur_max"], job["dur_typ"], None
    reserved, h = [], first
    while h + H1 <= job["deadline"] and need_max > EPS and h in book.room[hub["id"]]:
        if book.covered(hub, h, job["mw"]):
            if prev is not None and h != prev + H1:
                need_max += cfg["resume_overhead_h"]
                need_typ += cfg["resume_overhead_h"]
            prev = h
            need_max -= 1
            if need_typ > EPS:
                reserved.append(h)
                need_typ -= 1
        h += H1
    return _draws({**job, "dur_typ": job["dur_typ"] + cfg["resume_overhead_h"] * max(0, _gaps(reserved))}, reserved) if need_max <= EPS else None


def _gaps(hours):
    return sum(1 for a, b in zip(hours, hours[1:]) if b != a + H1)


# ---- Planning and the hourly tick ----------------------------------------------------------------------------------

def plan(t, jobs, forecast, hubs, carbon=None, cfg=CFG):
    """Re-plan every open job (least slack first, SC6). Running jobs keep their committed hours. Mutates job["plan"]."""
    book = Book(forecast, hubs, t, cfg)
    for j in jobs:
        if j["state"] == "running":
            for h, mw in j["draws"].items():
                if h >= t:
                    book.take(hubs[j["placed_hub"]], h, mw)
    open_ = sorted((j for j in jobs if j["state"] in ("pending", "scheduled") and j["submitted_at"] <= t),
                   key=lambda j: (latest_start(j), j["deadline"], j["job_id"]))
    for j in open_:
        slot = best_slot(j, t, book, hubs, carbon, cfg)
        j["plan"] = None
        if slot:
            _, hub, draws = slot
            for h, mw in draws:
                book.take(hub, h, mw)
            j["plan"] = {"hub": hub["id"], "draws": draws}
    return open_


def tick(t, jobs, forecast, actual, hubs, tanks, carbon=None, cfg=CFG):
    """One hour: plan, commit starts due now, settle each grid. -> (ledger rows, tank rows, move rows)."""
    for j in plan(t, jobs, forecast, hubs, carbon, cfg):
        p = j["plan"]
        if p and p["draws"][0][0] == t:  # commit only the starts due this hour (SC1)
            if j["state"] == "pending":
                set_state(j, "scheduled")
            set_state(j, "running")
            j["placed_hub"], j["start_hour"], j["draws"] = p["hub"], t, dict(p["draws"])
        elif p:
            if j["state"] == "pending":
                set_state(j, "scheduled")
        else:
            if j["state"] == "scheduled":
                set_state(j, "pending")  # plan revised before the start hour
            ls = latest_start(j)
            if t > ls:
                set_state(j, "missed")  # cannot finish even at home (reported, never dropped)
            elif t == ls:
                set_state(j, "home_run")  # SC7: runs at home as normal load, not in the ledger
    by_hub = {}
    moves = []
    for j in jobs:
        if j["state"] == "running" and t in j["draws"]:
            by_hub[j["placed_hub"]] = by_hub.get(j["placed_hub"], 0.0) + j["draws"][t]
            if j["placed_hub"] != j["home_hub"]:  # move accounting (DM1): load added at the destination, removed at home
                moves.append({"job_id": j["job_id"], "hour_utc": t, "to_grid": hubs[j["placed_hub"]]["grid"],
                              "from_grid": hubs[j["home_hub"]]["grid"], "mw": j["draws"][t]})
    rows, tank_rows = [], []
    for grid in sorted(actual):
        if t not in actual[grid]:
            continue
        row, trows = settle(grid, t, actual[grid][t], by_hub, hubs, tanks, cfg)
        check_row(row)
        rows.append(row)
        tank_rows += trows
    for j in jobs:  # finish or miss
        if j["state"] == "running":
            if t >= max(j["draws"]):
                set_state(j, "done")
            elif t + H1 >= j["deadline"]:
                set_state(j, "missed")
    return rows, tank_rows, moves


def settle(grid, t, surplus, draws_by_hub, hubs, tanks, cfg=CFG):
    """One ledger row for one grid and hour (SC9-SC11). Jobs, then pre-chill, then filler, each only from surplus left over."""
    p10, p50, p90 = surplus
    gh = sorted((h for h in hubs.values() if h["grid"] == grid), key=lambda h: h["id"])
    wanted = sum(draws_by_hub.get(h["id"], 0.0) for h in gh)
    jobs_mwh = min(wanted, p50)
    shortfall = wanted - jobs_mwh  # job energy that surplus did not cover (SC8); outside the invariant
    avail = min(max(0.0, p50 - jobs_mwh), max(0.0, surplus[Q[cfg["coverage"]]] - wanted))  # cooling and filler obey SC13 too
    cooling = filler = 0.0
    room, tank_rows = {}, []
    for h in gh:
        room[h["id"]] = h["headroom"] - draws_by_hub.get(h["id"], 0.0)
        level = tanks.setdefault(h["id"], 0.0)
        e = min(h["chiller_mw"], (h["tank_cap"] - level) / cfg["cop"], room[h["id"]], avail)  # electricity; thermal charge = e x COP
        e = max(0.0, e)
        tanks[h["id"]] = level + e * cfg["cop"] if e > EPS else max(0.0, level - 0.5 * h["chiller_mw"] * cfg["cop"])  # gauge, not thermodynamics
        cooling, avail, room[h["id"]] = cooling + e, avail - e, room[h["id"]] - e
        tank_rows.append({"hub_id": h["id"], "hour_utc": t, "level_mwh_th": tanks[h["id"]]})
    for h in gh:
        f = max(0.0, min(h["filler_mw"], room[h["id"]], avail))
        filler, avail, room[h["id"]] = filler + f, avail - f, room[h["id"]] - f
    unabsorbed = p50 - jobs_mwh - cooling - filler
    reason = None
    if unabsorbed > EPS:  # first reason reached in cascade order wins (SC10)
        if all(r <= EPS for r in room.values()):
            reason = "headroom_full"
        elif all(tanks[h["id"]] >= h["tank_cap"] - EPS for h in gh):
            reason = "tank_full"
        else:
            reason = "no_eligible_work"
    return ({"grid_id": grid, "hour_utc": t, "surplus_mw_p10": p10, "surplus_mw_p50": p50, "surplus_mw_p90": p90, "jobs_mwh": jobs_mwh,
             "cooling_mwh": cooling, "filler_mwh": filler, "unabsorbed_mwh": max(0.0, unabsorbed), "unabsorbed_reason": reason,
             "shortfall_mwh": shortfall, "data_quality": "simulated"}, tank_rows)


def check_row(r):
    """Every MWh of surplus lands in exactly one bucket (SC11). A failed check stops the write."""
    if abs(r["jobs_mwh"] + r["cooling_mwh"] + r["filler_mwh"] + r["unabsorbed_mwh"] - r["surplus_mw_p50"]) > 1e-6:
        raise LedgerError(f"ledger does not sum for {r['grid_id']} {r['hour_utc']}")


# ---- Replay, metrics, preview --------------------------------------------------------------------------------------

def replay(jobs, hours, actual, forecast=None, hubs=None, carbon=None, cfg=CFG):
    """Run the scheduler hour by hour over `hours`. Plans from `forecast` (Greedy) or from `actual` when None (Oracle). Settles against
    `actual`. Mutates the jobs. -> {"ledger", "tanks", "moves", "metrics"}"""
    hubs, forecast, tanks = hubs or load_hubs(cfg), forecast or actual, {}
    ledger, tank_rows, moves = [], [], []
    for t in hours:
        r, tr, mv = tick(t, jobs, forecast, actual, hubs, tanks, carbon, cfg)
        ledger += r
        tank_rows += tr
        moves += mv
    return {"ledger": ledger, "tanks": tank_rows, "moves": moves, "metrics": metrics(jobs, ledger, hubs, cfg)}


def metrics(jobs, ledger, hubs, cfg=CFG):
    surplus = sum(r["surplus_mw_p50"] for r in ledger)
    absorbed = sum(r["jobs_mwh"] + r["cooling_mwh"] + r["filler_mwh"] for r in ledger)
    count = lambda s: sum(1 for j in jobs if j["state"] == s)
    bad = sum(1 for j in jobs if j["placed_hub"] and not allowed_hub(j, hubs[j["placed_hub"]], hubs[j["home_hub"]], cfg))
    return {"surplus_mwh": surplus, "absorbed_mwh": absorbed, "absorbed_share": absorbed / surplus if surplus else 0.0,
            "jobs_mwh": sum(r["jobs_mwh"] for r in ledger), "shortfall_mwh": sum(r["shortfall_mwh"] for r in ledger),
            "moved": sum(1 for j in jobs if j["placed_hub"] and j["placed_hub"] != j["home_hub"]), "done": count("done"),
            "home_run": count("home_run"), "missed": count("missed"),
            # missed jobs that could have run at home when submitted; must be 0 (the rest were infeasible inputs)
            "scheduler_misses": sum(1 for j in jobs if j["state"] == "missed" and latest_start(j) >= j["submitted_at"]), "open": count("pending") + count("scheduled") + count("running"),
            "constraint_violations": bad}


def preview(job, t, forecast, hubs=None, carbon=None, cfg=CFG, energy_kwh=None):
    """Read-only advice, commits nothing (AP preview). verdict: covered | held | not_covered | infeasible | data_unavailable."""
    hubs = hubs or load_hubs(cfg)
    if t + job["dur_max"] * H1 > job["deadline"]:
        return {"verdict": "infeasible", "reasons": ["cannot finish by the deadline even at home using the maximum duration"]}
    home = hubs[job["home_hub"]]
    grids = {h["grid"] for h in hubs.values() if allowed_hub(job, h, home, cfg)}
    if not grids:
        return {"verdict": "not_covered", "reasons": ["no_modeled_grid"]}
    if not any(forecast.get(g) for g in grids):
        return {"verdict": "data_unavailable", "reasons": ["no surplus forecast for any allowed grid"]}
    slot = best_slot({**job, "plan": None}, t, Book(forecast, hubs, t, cfg), hubs, carbon, cfg)
    if slot:
        _, hub, draws = slot
        e = energy_kwh or {"min": job["energy_mwh"] * 1000, "typ": job["energy_mwh"] * 1000, "max": job["energy_mwh"] * 1000}
        end = draws[-1][0] + H1
        return {"verdict": "covered", "reasons": ["surplus alone powers the job in every hour (P10 test)"],
                "best_slot": {"hub": hub["id"], "grid": hub["grid"], "start_utc": draws[0][0].isoformat(), "end_utc": end.isoformat(),
                              "absorbed_mwh": {k: e[k] / 1000 for k in ("min", "typ", "max")}, "moved": hub["id"] != home["id"]}}
    ls = latest_start(job)
    if ls > t:
        return {"verdict": "held", "reasons": ["no covered window now; one may open"], "latest_start_utc": ls.isoformat()}
    return {"verdict": "not_covered", "reasons": ["no covered window and no slack left; it would run at home"]}


# ---- Stand-ins until the surplus rule (D6) and real users exist ----------------------------------------------------

UTC_OFFSET = {"PJM": -5, "MISO": -6, "ERCOT": -6, "SOCO": -5, "PACE": -7, "SRP": -7, "CAISO": -8, "GCPD": -8}


def synthetic_surplus(grids, start, hours, seed=0):
    """Labeled-simulated surplus (SY1): a midday solar bump per grid with day-to-day amplitude. Not a forecast of anything real."""
    rng, out = random.Random(seed), {}
    for g in sorted(grids):
        amp, day = rng.uniform(300, 1500), None
        out[g] = {}
        for i in range(hours):
            t = start + i * H1
            if day != (t + timedelta(hours=UTC_OFFSET.get(g, -6))).date():
                day = (t + timedelta(hours=UTC_OFFSET.get(g, -6))).date()
                amp = rng.uniform(300, 1500) * rng.choice([0.2, 1, 1, 1.4])
            local = (t.hour + UTC_OFFSET.get(g, -6)) % 24
            p50 = max(0.0, amp * math.sin(math.pi * (local - 8) / 9)) if 8 <= local <= 17 else 0.0
            out[g][t] = (p50 * 0.6, p50, p50 * 1.3)
    return out


def actual_from(forecast, seed=1, noise=0.25):
    """A noisy 'what really happened' table around a forecast, to see what forecast error costs (Greedy vs Oracle)."""
    rng = random.Random(seed)
    out = {}
    for g, hrs in forecast.items():
        out[g] = {}
        for h, (_, p50, _) in hrs.items():
            a = max(0.0, p50 * rng.uniform(1 - noise, 1 + noise)) if p50 else 0.0
            out[g][h] = (a, a, a)
    return out
