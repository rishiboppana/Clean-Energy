"""Season-stratified block split: every season appears in train, validation and test, and no label or lag feature crosses a boundary."""
import numpy as np
import pandas as pd

SEASON = {12: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2}  # winter, spring, summer; anything else is autumn (3)


def seasonal_block_split(issue, block_days=14, buffer_days=3, frac=0.15, seed=0):
    """Whole 14-day blocks go to one set, drawn per season so each season gets ~frac in val and in test.
    Rows within buffer_days of a boundary between different sets are dropped (labels reach 48 h ahead, lag features 3 days back).
    Returns an object array of 'train' / 'val' / 'test' / None (dropped)."""
    t = pd.to_datetime(pd.Series(np.asarray(issue)))
    start = t.min().normalize()
    day = (t - start).dt.total_seconds().values / 86400
    block = (day // block_days).astype(int)
    rng = np.random.default_rng(seed)
    assign = {}
    for s in range(4):
        bs = [int(b) for b in np.unique(block)
              if SEASON.get((start + pd.Timedelta(days=b * block_days + block_days // 2)).month, 3) == s]
        rng.shuffle(bs)
        n = max(1, round(frac * len(bs)))
        for i, b in enumerate(bs):
            assign[b] = "test" if i < n else "val" if i < 2 * n else "train"
    split = np.array([assign[b] for b in block], dtype=object)
    pos = day - block * block_days
    prev = np.array([assign.get(b - 1, assign[b]) != assign[b] for b in block])
    nxt = np.array([assign.get(b + 1, assign[b]) != assign[b] for b in block])
    split[(prev & (pos < buffer_days)) | (nxt & (pos >= block_days - buffer_days))] = None
    return split
