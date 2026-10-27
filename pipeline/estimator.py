"""Job energy estimator (specs.md section 7, EE1-EE12). Pure function: job fields in, min/typ/max record out."""
import json
from datetime import datetime, timezone
from pathlib import Path

ESTIMATOR_VERSION = "1"
CONSTANTS_VERSION = "2"

GPUS = {"A100": {"tdp_w": 400, "peak_flops": 312e12, "mem_gb": 80}, "H100": {"tdp_w": 700, "peak_flops": 990e12, "mem_gb": 80}}

# (min, typ, max). Duration uses the high MFU for the shortest time.
MFU = {"pretrain": (0.25, 0.40, 0.55), "finetune": (0.25, 0.40, 0.50), "prefill": (0.30, 0.40, 0.50), "decode": (0.08, 0.10, 0.12)}
# Node power, calibrated on LBNL/Brookhaven measurements of an 8-GPU H100 node (rated 10.2 kW): training averaged ~76% of
# rating (~7.75 kW), peak ~8.4 kW, i.e. 1.38x and 1.5x the 5.6 kW of GPU TDP. Typical 0.85 x 1.6 = 1.36 matches the average.
# The min/max corners are wider than the measurement on purpose. Inference fraction is still unsourced.
POWER_FRAC = {"train": (0.6, 0.85, 0.95), "inference": (0.3, 0.5, 0.7)}
HOST_OVERHEAD = (1.3, 1.6, 1.8)  # DGX H100 rated 10.2 kW / 5.6 kW GPU TDP = 1.82
# PUE: Google fleet 1.09 (2024 TTM), AWS 1.15 (2024), Uptime Institute industry average 1.56 (2024). Typical 1.2 is my pick.
PUE = (1.09, 1.2, 1.56)
SERVER_KW = (0.3, 0.5, 0.8)  # unsourced guess, non-ML jobs
RESUME_OVERHEAD_H = 0.25  # unsourced, EE9
GPU_COUNT_BY_PARAMS = [(2e9, 1), (15e9, 8), (80e9, 64), (float("inf"), 256)]  # unsourced, EE7
# Per-hub GPU fleet (made up, see the file's note). Used to flag jobs no hub could run.
HUB_GPUS = json.loads((Path(__file__).parent.parent / "data" / "hub_gpus.json").read_text())["hubs"]

FLOPS_PER_PARAM_TOKEN = {"pretrain": 6, "finetune_full": 6, "finetune_adapter": 4}
# bytes of GPU memory per parameter: bf16 weights (2) vs weights + grads + Adam state (16)
MEM_BYTES_PER_PARAM = {"pretrain": 16, "finetune_full": 16, "finetune_adapter": 2, "inference": 2}
JOB_TYPES = {*FLOPS_PER_PARAM_TOKEN, "inference", "batch_cpu", "gpu_hours"}
UNSUPPORTED = {"moe", "image_generation", "video_generation"}
REQUIRED = {"pretrain": ("n_params", "tokens"), "finetune_full": ("n_params", "tokens"), "finetune_adapter": ("n_params", "tokens"),
            "inference": ("n_params", "input_tokens", "output_tokens", "requests"), "batch_cpu": ("server_hours",), "gpu_hours": ("gpu_hours",)}


class EstimateError(ValueError):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def _tmm(lo, typ, hi):
    return {"min": lo, "typ": typ, "max": hi}


def estimate_many(jobs, now=None):
    """One result per job; a bad job yields {"error", "detail"} instead of failing the batch."""
    out = []
    for j in jobs:
        try:
            out.append(estimate(j, now))
        except EstimateError as e:
            out.append({"error": e.code, "detail": e.detail})
        except (TypeError, ValueError, AttributeError):
            out.append({"error": "validation_failed", "detail": None})
    return out


def estimate(job, now=None):
    """Raises EstimateError with the API error code (422 cases of POST /v1/jobs/estimate)."""
    jt = job.get("job_type")
    if jt in UNSUPPORTED or jt not in JOB_TYPES:
        raise EstimateError("unsupported_job_type")
    if not job.get("deadline_utc"):
        raise EstimateError("missing_fields", ["deadline_utc"])
    deadline = datetime.fromisoformat(job["deadline_utc"].replace("Z", "+00:00"))
    if deadline.tzinfo is None:  # a naive time from the parser or a form means UTC
        deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline <= (now or datetime.now(timezone.utc)):
        raise EstimateError("deadline_in_past")
    direct = job.get("gpu_hours") is not None
    need = REQUIRED["gpu_hours"] if direct else REQUIRED[jt]
    if missing := [k for k in need if job.get(k) is None]:
        raise EstimateError("missing_fields", missing)

    assumptions, warnings = [], []
    if direct and jt not in ("gpu_hours", "batch_cpu") and job.get("tokens") is not None:
        warnings.append("gpu_hours given along with model size and tokens; the direct value is used")

    interruptible = job.get("interruptible")
    if interruptible is None:
        interruptible = False
        assumptions.append("interruptible=false")
    allowed = job.get("allowed_grids")
    if allowed is None:
        allowed = "all"
        assumptions.append("allowed_grids=all")

    if jt == "batch_cpu" and not direct:
        servers = job.get("servers")
        if servers is None:
            servers = 1
            assumptions.append("servers=1")
        dur = _tmm(*[job["server_hours"] / servers] * 3)
        power = _tmm(*(servers * k * p for k, p in zip(SERVER_KW, PUE)))
        gpu_type = gpu_count = None
        conf = "low"
    else:
        gpu_type = job.get("gpu_type")
        if gpu_type is None:
            gpu_type = "H100"
            assumptions.append("gpu_type=H100")
        if gpu_type not in GPUS:
            raise EstimateError("unsupported_hardware", gpu_type)
        g = GPUS[gpu_type]
        gpu_count = job.get("gpu_count")
        if gpu_count is None:
            # no model size (e.g. a GPU-hours budget): one 8-GPU node, not 1 GPU, which would stretch the duration absurdly
            gpu_count = next(c for lim, c in GPU_COUNT_BY_PARAMS if job["n_params"] <= lim) if job.get("n_params") else 8
            assumptions.append(f"gpu_count={gpu_count}")
        rate = lambda mfu: gpu_count * g["peak_flops"] * mfu * 3600  # FLOPs per hour

        if direct:
            h = job["gpu_hours"] / gpu_count
            dur, conf = _tmm(h, h, h), "high"
        elif jt == "inference":
            n, req = job["n_params"], job["requests"]
            pre, dec = 2 * n * job["input_tokens"] * req, 2 * n * job["output_tokens"] * req
            hrs = lambda i: pre / rate(MFU["prefill"][i]) + dec / rate(MFU["decode"][i])
            dur, conf = _tmm(hrs(2), hrs(1), hrs(0)), "low"
        else:
            flops = FLOPS_PER_PARAM_TOKEN[jt] * job["n_params"] * job["tokens"]
            mfu = MFU["pretrain" if jt == "pretrain" else "finetune"]
            dur, conf = _tmm(flops / rate(mfu[2]), flops / rate(mfu[1]), flops / rate(mfu[0])), "medium"

        pf = POWER_FRAC["inference" if jt == "inference" else "train"]
        power = _tmm(*(gpu_count * g["tdp_w"] / 1000 * f * h * p for f, h, p in zip(pf, HOST_OVERHEAD, PUE)))

        if gpu_count > max((f["gpu_count"] for f in HUB_GPUS.values() if f["gpu_type"] == gpu_type), default=0):
            warnings.append(f"more {gpu_type}s than any hub has; the scheduler will find no candidate")
        if job.get("n_params") and job["n_params"] * MEM_BYTES_PER_PARAM.get(jt, 2) > gpu_count * g["mem_gb"] * 1e9:
            warnings.append("weights probably do not fit in GPU memory")

    # min energy = all-low corner, max = all-high corner (EE6)
    energy = _tmm(power["min"] * dur["min"], power["typ"] * dur["typ"], power["max"] * dur["max"])
    hours_left = (deadline - (now or datetime.now(timezone.utc))).total_seconds() / 3600
    if dur["max"] > hours_left:
        warnings.append("in the worst case (max duration) this would not finish before the deadline")
    return {
        "hours_to_deadline": round(hours_left, 1), "job_id": job.get("job_id"), "job_type": jt, "gpu_type": gpu_type, "gpu_count": gpu_count,
        "duration_h": dur, "power_kw": power, "energy_kwh": energy,
        "interruptible": interruptible, "resume_overhead": RESUME_OVERHEAD_H if interruptible else 0,
        "deadline_utc": job["deadline_utc"], "allowed_grids": allowed, "data_gb": job.get("data_gb"),
        "assumptions": assumptions, "confidence": conf, "warnings": warnings,
        "estimator_version": ESTIMATOR_VERSION, "constants_version": CONSTANTS_VERSION,
    }
