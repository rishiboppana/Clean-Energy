"""Which features help? Correlations, model gain, and permutation importance on the forward holdout, per model.
python -m forecast.feature_report  ->  reports/features/*.png, importance.csv"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb
from matplotlib.colors import LinearSegmentedColormap

from forecast import train as T
from pipeline import store

OUT = os.path.join(store.ROOT, "reports", "features")
MODELS = [("SRP", "SUN"), ("SOCO", "SUN"), ("PACE", "SUN"), ("PACE", "WND")]
GROUPS = {
    "weather means": lambda f: f.endswith("_m") and not f.startswith("csi"),
    "weather spread": lambda f: f.endswith("_s"),
    "sun (elev, csi)": lambda f: f in ("elev", "csi"),
    "time of day/year": lambda f: f in ("hod_sin", "hod_cos", "doy_sin", "doy_cos", "dow", "holiday"),
    "lag actuals": lambda f: f.endswith("_share"),
    "horizon, lead": lambda f: f in ("horizon", "lead_bucket"),
}
DIV = LinearSegmentedColormap.from_list("div", ["#2b6cb0", "#f0efec", "#c0392b"])  # blue <-> red, gray midpoint
INK, MUTED = "#1f1f1e", "#6b6b66"


def mae(bst, df, fuel):
    mw = T.to_mw(T.predict(bst, df), df, fuel)[:, 1]
    m = (df["elev"] > 0).values if fuel == "SUN" else np.ones(len(df), bool)
    return float(np.abs(mw[m] - df["y_mw"].values[m]).mean())


def permute(bst, te, cols, fuel, base, rng, reps=3):
    out = []
    for _ in range(reps):
        d = te.copy()
        idx = rng.permutation(len(d))
        for c in cols:
            d[c] = d[c].values[idx]  # shuffle the columns together so a group keeps its internal relationships
        out.append(mae(bst, d, fuel) - base)
    return float(np.mean(out))


def analyse(grid, fuel):
    df, tr, va, te = T.prepare(grid, fuel, "time")
    cols = T.feats(fuel)
    dtr = xgb.QuantileDMatrix(tr[cols], tr["label"])
    dva = xgb.QuantileDMatrix(va[cols], va["label"], ref=dtr)
    bst = xgb.train(T.PARAMS, dtr, 3000, evals=[(dva, "v")], early_stopping_rounds=50, verbose_eval=False)
    day = df[df["elev"] > 0] if fuel == "SUN" else df  # night solar is a constant zero and would dilute every correlation
    corr = day[cols + ["label"]].corr(method="spearman")
    base = mae(bst, te, fuel)
    rng = np.random.default_rng(0)
    gain = pd.Series(bst.get_score(importance_type="gain")).reindex(cols).fillna(0)
    rows = [{"feature": c, "spearman_vs_output": corr.loc[c, "label"], "gain_share": gain[c] / gain.sum(),
             "mae_increase_mw": permute(bst, te, [c], fuel, base, rng)} for c in cols]
    groups = {g: permute(bst, te, [c for c in cols if fn(c)], fuel, base, rng) for g, fn in GROUPS.items()}
    return corr, pd.DataFrame(rows).set_index("feature"), groups, base


def heat(ax, m, labels_x, labels_y, title, fs=7):
    ax.imshow(m, cmap=DIV, vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(labels_x)), labels_x, rotation=90, fontsize=fs, color=MUTED)
    ax.set_yticks(range(len(labels_y)), labels_y, fontsize=fs, color=MUTED)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            ax.text(j, i, f"{m[i, j]:.2f}".replace("0.", ".").replace("-.", "-."), ha="center", va="center", fontsize=fs - 1,
                    color="white" if abs(m[i, j]) > 0.6 else INK)
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    for s in ax.spines.values():
        s.set_visible(False)


def main():
    os.makedirs(OUT, exist_ok=True)
    res = {f"{g} {f}": analyse(g, f) for g, f in MODELS}
    names = list(res)
    feats = list(res[names[0]][1].index)  # SUN feature list, a superset minus wind3
    allf = list(dict.fromkeys(f for n in names for f in res[n][1].index))

    # 1. each feature vs output, one column per model
    M = np.array([[res[n][1]["spearman_vs_output"].get(f, np.nan) for n in names] for f in allf])
    fig, ax = plt.subplots(figsize=(6.5, 8), dpi=150)
    heat(ax, np.nan_to_num(M), names, allf, "Rank correlation of each feature with output (share of capacity)", fs=8)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "corr_with_output.png")); plt.close(fig)

    # 2. feature-vs-feature matrices (redundancy), one panel per model
    fig, axes = plt.subplots(2, 2, figsize=(15, 14), dpi=130)
    for ax, n in zip(axes.ravel(), names):
        c = res[n][0].drop(index="label", columns="label")
        heat(ax, c.values, list(c.columns), list(c.index), n + ": feature vs feature", fs=6)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "corr_between_features.png")); plt.close(fig)

    # 3. shuffle test: how much worse the holdout MAE gets when a feature or group is scrambled
    fig, axes = plt.subplots(2, 4, figsize=(18, 9), dpi=130)
    for j, n in enumerate(names):
        corr, imp, grp, base = res[n]
        s = imp["mae_increase_mw"].sort_values()
        axes[0, j].barh(s.index, s.values, color="#2b6cb0", height=0.6)
        axes[0, j].set_title(f"{n}: one feature shuffled\n(holdout MAE {base:.0f} MW)", fontsize=9, loc="left", color=INK)
        g = pd.Series(grp).sort_values()
        axes[1, j].barh(g.index, g.values, color="#2b6cb0", height=0.6)
        axes[1, j].set_title(f"{n}: whole group shuffled", fontsize=9, loc="left", color=INK)
        for a in axes[:, j]:
            a.set_xlabel("MAE increase (MW)", fontsize=8, color=MUTED); a.tick_params(labelsize=7, colors=MUTED)
            a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "shuffle_importance.png")); plt.close(fig)

    tab = pd.concat({n: res[n][1] for n in names}, axis=1)
    tab.to_csv(os.path.join(OUT, "importance.csv"))
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print("MAE increase in MW when the feature is shuffled (higher = more useful):")
    print(tab.xs("mae_increase_mw", axis=1, level=1).round(1).to_string())
    print("\nSpearman correlation with output:")
    print(tab.xs("spearman_vs_output", axis=1, level=1).round(2).to_string())
    print("\nGroup shuffle, MAE increase in MW:")
    print(pd.DataFrame({n: res[n][2] for n in names}).round(1).to_string())


if __name__ == "__main__":
    main()
