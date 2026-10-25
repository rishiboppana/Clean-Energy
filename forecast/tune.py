"""Ray Tune search for one (grid, fuel): python -m forecast.tune SRP SUN [trials]. Minimizes validation pinball loss, then retrains with the best params."""
import json
import os
import sys

import ray
import xgboost as xgb
from ray import train, tune

from forecast import train as T
from pipeline import store

SPACE = {
    "max_depth": tune.randint(3, 10),
    "learning_rate": tune.loguniform(0.02, 0.2),
    "min_child_weight": tune.loguniform(1, 100),
    "subsample": tune.uniform(0.5, 1.0),
    "colsample_bytree": tune.uniform(0.5, 1.0),
    "reg_lambda": tune.loguniform(0.1, 30),
    "gamma": tune.loguniform(1e-3, 1),
}


def trial(config, data):
    tr, va = data
    dtr = xgb.QuantileDMatrix(tr[T.FEATURES], tr["label"])
    dva = xgb.QuantileDMatrix(va[T.FEATURES], va["label"], ref=dtr)
    bst = xgb.train({**T.PARAMS, **config, "nthread": 2}, dtr, 3000, evals=[(dva, "val")], early_stopping_rounds=50, verbose_eval=False)
    train.report({"val_pinball": bst.best_score, "best_iteration": bst.best_iteration})


def main(grid, fuel, trials=30):
    data = T.prepare(grid, fuel, "seasonal")
    _, tr, va, _ = data
    ray.init(num_cpus=10, include_dashboard=False, logging_level="ERROR")
    out = os.path.join(store.ROOT, "models", "_tune", f"{grid}_{fuel}")
    tuner = tune.Tuner(
        tune.with_parameters(trial, data=(tr, va)),
        param_space=SPACE,
        tune_config=tune.TuneConfig(metric="val_pinball", mode="min", num_samples=trials, max_concurrent_trials=5),
        run_config=train.RunConfig(storage_path=os.path.abspath(out), verbose=0))
    res = tuner.fit()
    best = res.get_best_result()
    ray.shutdown()
    print(f"best of {trials}: val_pinball {best.metrics['val_pinball']:.5f}", {k: round(v, 4) if isinstance(v, float) else v for k, v in best.config.items()})
    base = T.run(grid, fuel, data=data)          # untuned starting params, same split, for an honest before/after
    tuned = T.run(grid, fuel, params=best.config, data=data)
    json.dump({"best_params": best.config, "untuned_val_pinball": base["val_pinball"], "tuned_val_pinball": tuned["val_pinball"]},
              open(os.path.join(store.ROOT, "models", "_tune", f"{grid}_{fuel}.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 30)
