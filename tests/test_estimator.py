import unittest
from datetime import datetime, timezone

from pipeline.estimator import EstimateError, estimate

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
DEADLINE = "2026-10-25T20:00:00Z"


def run(**kw):
    return estimate({"deadline_utc": DEADLINE, **kw}, now=NOW)


class EstimatorTest(unittest.TestCase):
    def test_worked_example(self):  # specs.md section 7: 7B full fine-tune, 150M tokens, 8 H100
        r = run(job_type="finetune_full", n_params=7e9, tokens=1.5e8, gpu_type="H100", gpu_count=8)
        d, p, e = r["duration_h"], r["power_kw"], r["energy_kwh"]
        self.assertAlmostEqual(d["min"] * 60, 26.5, delta=0.5)
        self.assertAlmostEqual(d["typ"] * 60, 33.1, delta=0.5)
        self.assertAlmostEqual(d["max"] * 60, 53.0, delta=0.5)
        self.assertAlmostEqual(p["typ"], 6.37, places=2)
        self.assertAlmostEqual(e["min"], 1.6, delta=0.1)
        self.assertAlmostEqual(e["typ"], 3.5, delta=0.1)
        self.assertAlmostEqual(e["max"], 10, delta=0.2)
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


if __name__ == "__main__":
    unittest.main()
