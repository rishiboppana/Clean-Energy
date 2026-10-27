import unittest
from datetime import datetime, timedelta, timezone

from pipeline.scheduler import (H1, LedgerError, actual_from, check_row, load_hubs, make_job, preview, replay, set_state, synthetic_surplus)

T0 = datetime(2026, 10, 26, 0, tzinfo=timezone.utc)
HUBS = load_hubs()


def rec(mw=10.0, typ=2.0, mx=3.0, deadline_h=30, interruptible=False, grids="all", data_gb=0):
    return {"power_kw": {"typ": mw * 1000}, "duration_h": {"typ": typ, "max": mx}, "energy_kwh": {"typ": mw * typ * 1000},
            "deadline_utc": (T0 + deadline_h * H1).isoformat(), "allowed_grids": grids, "data_gb": data_gb, "interruptible": interruptible}


def job(home="dfw", jid="j", cls="batch", **kw):
    return make_job(rec(**kw), home, T0, cls, jid)


def flat(grid_mw, hours=48, p10_share=1.0):
    """{grid: {hour: (p10, p50, p90)}} with a constant surplus."""
    return {g: {T0 + i * H1: (mw * p10_share, mw, mw) for i in range(hours)} for g, mw in grid_mw.items()}


def run(jobs, surplus, hours=30, forecast=None):
    return replay(jobs, [T0 + i * H1 for i in range(hours)], surplus, forecast, HUBS)


class SchedulerTest(unittest.TestCase):
    def test_covered_job_runs_and_ledger_sums(self):
        j = job()
        out = run([j], flat({"ERCOT": 100}))
        self.assertEqual((j["state"], j["placed_hub"], j["start_hour"]), ("done", "dfw", T0))
        self.assertAlmostEqual(out["metrics"]["jobs_mwh"], 20.0)  # 10 MW x 2 h typical
        for r in out["ledger"]:
            check_row(r)

    def test_surplus_only_rule_p10_must_cover(self):  # SC13: P10 below the job's MW means it is not moved or shifted
        j = job(mx=3.0, deadline_h=10)
        out = run([j], flat({"ERCOT": 100}, p10_share=0.05), hours=12)  # P10 = 5 MW < 10 MW
        self.assertEqual(j["state"], "home_run")
        self.assertEqual(out["metrics"]["jobs_mwh"], 0)  # not in the ledger as absorbed

    def test_home_run_exactly_at_latest_start(self):
        j = job(mx=3.0, deadline_h=10)  # latest start = hour 7
        run([j], flat({"ERCOT": 1}), hours=12)
        self.assertEqual(j["state"], "home_run")

    def test_infeasible_job_is_missed_not_dropped(self):
        j = job(mx=5.0, deadline_h=3)
        out = run([j], flat({"ERCOT": 100}), hours=5)
        self.assertEqual((j["state"], out["metrics"]["scheduler_misses"]), ("missed", 0))  # infeasible input, not the scheduler's miss

    def test_moves_to_the_grid_with_the_widest_margin(self):
        j = job(home="dfw", cls="batch")
        out = run([j], flat({"ERCOT": 20, "CAISO": 500}))
        self.assertEqual(j["placed_hub"], "svalley")
        self.assertEqual(out["metrics"]["moved"], 1)
        mv = out["moves"][0]  # DM1: load added at the destination, removed at home
        self.assertEqual((mv["to_grid"], mv["from_grid"]), ("CAISO", "ERCOT"))

    def test_picks_the_widest_margin_even_if_later(self):  # SC5 ranks margin above earliest start
        s = flat({"ERCOT": 30})
        for i in range(6, 12):
            s["ERCOT"][T0 + i * H1] = (400, 400, 400)
        j = job(cls="local", deadline_h=30)
        run([j], s)
        self.assertEqual(j["start_hour"], T0 + 6 * H1)

    def test_latency_class_and_allowed_grids_are_hard(self):
        local = job(cls="local")
        priv = job(jid="p", grids=["ERCOT"])
        run([local, priv], flat({"ERCOT": 20, "CAISO": 500}))
        self.assertEqual((local["placed_hub"], priv["placed_hub"]), ("dfw", "dfw"))
        regional = job(home="dfw", cls="regional")  # central reaches east and mountain, never west (CAISO)
        run([regional], flat({"ERCOT": 20, "CAISO": 500, "PJM": 300}))
        self.assertEqual(HUBS[regional["placed_hub"]]["grid"], "PJM")

    def test_transfer_time_delays_the_start(self):
        j = job(home="dfw", data_gb=36000)  # 36 TB at 10 Gbps = 8 h
        run([j], flat({"CAISO": 500}))
        self.assertEqual(j["placed_hub"], "svalley")
        self.assertGreaterEqual(j["start_hour"], T0 + 8 * H1)

    def test_least_slack_first_and_reservations(self):
        urgent, relaxed = job(jid="a", deadline_h=6), job(jid="b", deadline_h=40)
        run([relaxed, urgent], flat({"ERCOT": 10}))  # only one 10 MW job fits at a time
        self.assertEqual(urgent["start_hour"], T0)
        self.assertGreaterEqual(relaxed["start_hour"], T0 + 2 * H1)

    def test_headroom_limits_a_hub(self):
        big = job(mw=2000, typ=1.0, mx=1.0)  # hub headroom is 850 MW
        run([big], flat({"ERCOT": 5000}), hours=30)
        self.assertEqual(big["state"], "home_run")

    def test_interruptible_job_skips_uncovered_hours(self):
        s = flat({"ERCOT": 100}, hours=48)
        for h in (T0 + 1 * H1,):
            s["ERCOT"][h] = (0, 0, 0)
        j = job(interruptible=True, typ=2.0, mx=2.0)
        run([j], s)
        self.assertEqual(j["state"], "done")
        self.assertNotIn(T0 + 1 * H1, j["draws"])  # paused in the uncovered hour

    def test_forecast_error_becomes_shortfall_not_a_broken_ledger(self):
        fc = flat({"ERCOT": 100})
        actual = flat({"ERCOT": 4})  # the forecast was far too optimistic
        out = run([job()], actual, forecast=fc)
        self.assertGreater(out["metrics"]["shortfall_mwh"], 0)
        for r in out["ledger"]:
            check_row(r)

    def test_cascade_cooling_filler_unabsorbed_with_reason(self):
        out = run([], flat({"ERCOT": 400}), hours=3)  # no jobs: surplus goes to cooling, then filler, rest unabsorbed
        r = out["ledger"][0]
        self.assertGreater(r["cooling_mwh"], 0)
        self.assertGreater(r["filler_mwh"], 0)
        self.assertGreater(r["unabsorbed_mwh"], 0)
        self.assertIn(r["unabsorbed_reason"], ("tank_full", "no_eligible_work", "headroom_full"))

    def test_ledger_check_rejects_a_bad_row(self):
        r = run([], flat({"ERCOT": 50}), hours=1)["ledger"][0]
        with self.assertRaises(LedgerError):
            check_row({**r, "unabsorbed_mwh": r["unabsorbed_mwh"] + 1})

    def test_ledger_always_sums_on_a_big_noisy_run(self):
        fc = synthetic_surplus({"PJM", "ERCOT", "CAISO", "MISO", "SRP", "SOCO", "PACE", "GCPD"}, T0, 72, seed=3)
        jobs = [make_job(rec(mw=5 + i % 40, typ=1 + i % 4, mx=2 + i % 5, deadline_h=30 + i % 30), h, T0 + (i % 20) * H1, "batch", f"j{i}")
                for i, h in zip(range(60), list(HUBS) * 6)]
        out = replay(jobs, [T0 + i * H1 for i in range(72)], actual_from(fc), fc, HUBS)  # raises LedgerError on any bad row
        m = out["metrics"]
        self.assertEqual((m["scheduler_misses"], m["constraint_violations"]), (0, 0))
        self.assertGreater(m["absorbed_mwh"], 0)

    def test_illegal_transition_is_refused(self):
        j = job()
        with self.assertRaises(ValueError):
            set_state(j, "done")

    def test_preview_verdicts(self):
        s = flat({"ERCOT": 100})
        self.assertEqual(preview(job(), T0, s, HUBS)["verdict"], "covered")
        self.assertEqual(preview(job(mx=5.0, deadline_h=3), T0, s, HUBS)["verdict"], "infeasible")
        self.assertEqual(preview(job(), T0, {}, HUBS)["verdict"], "data_unavailable")
        self.assertEqual(preview(job(), T0, flat({"ERCOT": 0}), HUBS)["verdict"], "held")
        self.assertEqual(preview(job(mx=3.0, deadline_h=3), T0, flat({"ERCOT": 0}), HUBS)["verdict"], "not_covered")


if __name__ == "__main__":
    unittest.main()
