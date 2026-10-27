import unittest
from datetime import datetime, timezone

from pipeline.estimator import EstimateError, estimate

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
DEADLINE = "2026-10-25T20:00:00Z"


def run(**kw):
    return estimate({"deadline_utc": DEADLINE, **kw}, now=NOW)


class EstimatorTest(unittest.TestCase):
    def test_worked_example(self):  # 7B full fine-tune, 150M tokens, 8 H100; durations as specs.md section 7, power with the sourced constants
        r = run(job_type="finetune_full", n_params=7e9, tokens=1.5e8, gpu_type="H100", gpu_count=8)
        d, p, e = r["duration_h"], r["power_kw"], r["energy_kwh"]
        self.assertAlmostEqual(d["min"] * 60, 26.5, delta=0.5)
        self.assertAlmostEqual(d["typ"] * 60, 33.1, delta=0.5)
        self.assertAlmostEqual(d["max"] * 60, 53.0, delta=0.5)
        self.assertAlmostEqual(p["typ"], 9.139, places=2)  # 8 x 0.7 kW x 0.85 x 1.6 x 1.2
        self.assertAlmostEqual(e["min"], 2.11, delta=0.05)
        self.assertAlmostEqual(e["typ"], 5.05, delta=0.05)
        self.assertAlmostEqual(e["max"], 13.2, delta=0.2)
        self.assertEqual((r["confidence"], r["assumptions"]), ("medium", ["interruptible=false", "allowed_grids=all"]))

    def test_llama2_gpu_hours(self):  # 184,320 A100-hours reported; formula should be within 5%
        r = run(job_type="pretrain", n_params=7e9, tokens=2e12, gpu_type="A100", gpu_count=1000)
        self.assertAlmostEqual(r["duration_h"]["typ"] * 1000 / 184320, 1, delta=0.05)

    def test_direct_gpu_hours_wins(self):
        r = run(job_type="finetune_full", n_params=7e9, tokens=1.5e8, gpu_count=8, gpu_hours=64)
        self.assertEqual((r["duration_h"]["typ"], r["confidence"]), (8, "high"))
        self.assertTrue(r["warnings"])

    def test_inference_decode_dominates(self):
        r = run(job_type="inference", n_params=7e9, input_tokens=2000, output_tokens=500, requests=1000, gpu_count=1)
        self.assertEqual(r["confidence"], "low")
        self.assertLess(r["duration_h"]["min"], r["duration_h"]["typ"])

    def test_batch_cpu(self):
        r = run(job_type="batch_cpu", server_hours=40)
        self.assertEqual((r["gpu_type"], r["duration_h"]["typ"]), (None, 40))

    def test_warns_when_weights_do_not_fit(self):
        r = run(job_type="finetune_full", n_params=70e9, tokens=1e9, gpu_count=1)
        self.assertIn("weights probably do not fit in GPU memory", r["warnings"])

    def test_errors(self):
        for kw, code in [({"job_type": "moe"}, "unsupported_job_type"),
                         ({"job_type": "finetune_full", "n_params": 7e9}, "missing_fields"),
                         ({"job_type": "gpu_hours", "gpu_hours": 1, "gpu_type": "V100"}, "unsupported_hardware"),
                         ({"job_type": "gpu_hours", "gpu_hours": 1, "deadline_utc": "2026-10-01T00:00:00Z"}, "deadline_in_past")]:
            with self.assertRaises(EstimateError) as cm:
                run(**kw)
            self.assertEqual(cm.exception.code, code)

    def test_gpu_hours_budget_defaults_to_one_node(self):
        r = run(job_type="gpu_hours", gpu_hours=64)
        self.assertEqual((r["gpu_count"], r["duration_h"]["typ"]), (8, 8))

    def test_warns_when_worst_case_misses_deadline(self):
        r = run(job_type="gpu_hours", gpu_hours=800, gpu_count=8, deadline_utc="2026-10-24T12:00:00Z")  # 100 h of work, 12 h left
        self.assertTrue(any("deadline" in w for w in r["warnings"]))
        self.assertEqual(run(job_type="gpu_hours", gpu_hours=8, gpu_count=8)["warnings"], [])

    def test_flags_more_gpus_than_any_hub(self):
        r = run(job_type="gpu_hours", gpu_hours=1e7, gpu_count=1_000_000)
        self.assertTrue(any("any hub" in w for w in r["warnings"]))


class ApiTest(unittest.TestCase):
    def test_concurrent_calls(self):
        import json, threading, urllib.error, urllib.request
        from concurrent.futures import ThreadPoolExecutor
        from pipeline.estimator_api import make_server
        srv = make_server(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:%d/v1/jobs/estimate" % srv.server_address[1]

        def post(body):
            req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as f:
                    return f.status, json.load(f)
            except urllib.error.HTTPError as e:
                return e.code, json.load(e)

        job = lambda i: {"job_type": "finetune_full", "n_params": 7e9, "tokens": 1e8 * (i % 5 + 1), "gpu_count": 8, "deadline_utc": "2099-01-01T00:00:00Z"}
        try:
            with ThreadPoolExecutor(32) as ex:
                singles = list(ex.map(lambda i: post(job(i)), range(200)))
                bad = ex.submit(post, {"job_type": "moe"}).result()
            batch = post({"jobs": [job(i) for i in range(5)] + [{"job_type": "moe"}]})
        finally:
            srv.shutdown()
        self.assertTrue(all(c == 200 for c, _ in singles))
        for i, (_, r) in enumerate(singles):  # each caller got the answer for its own job
            self.assertAlmostEqual(r["duration_h"]["typ"], singles[i % 5][1]["duration_h"]["typ"])
        self.assertEqual(bad, (422, {"error": "unsupported_job_type", "detail": None}))
        self.assertEqual(batch[0], 200)
        self.assertEqual([x.get("error") for x in batch[1]["results"]], [None] * 5 + ["unsupported_job_type"])


if __name__ == "__main__":
    unittest.main()
