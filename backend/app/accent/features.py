"""Features for the learned accent detector.

For a phrase of n moras, every boundary "fall after mora a" (a = 1..n-1) is
a candidate accent nucleus. Each candidate gets a feature vector describing
the pitch around it; a logistic model scores how likely the fall is there.
"""

from __future__ import annotations

import numpy as np

N_FEATURES = 22


def mora_levels(times: np.ndarray, st: np.ndarray,
                spans: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    """Pitch at the start / middle / end third of every mora, relative to the
    phrase's median, NaN-free (gaps interpolated). Returns (levels [n, 3],
    voiced fraction [n])."""
    n = len(spans)
    lv = np.full((n, 3), np.nan)
    voiced = np.zeros(n)
    for i, (s, e) in enumerate(spans):
        sel = (times >= s) & (times < e)
        seg = st[sel]
        voiced[i] = np.mean(~np.isnan(seg)) if len(seg) else 0.0
        for k in range(3):
            lo, hi = s + k * (e - s) / 3, s + (k + 1) * (e - s) / 3
            v = st[(times >= lo) & (times < hi)]
            v = v[~np.isnan(v)]
            if len(v):
                lv[i, k] = np.median(v)
    flat = lv.reshape(-1)
    ok = ~np.isnan(flat)
    if ok.sum() == 0:
        return np.zeros((n, 3)), voiced
    idx = np.arange(len(flat))
    flat = np.interp(idx, idx[ok], flat[ok])
    flat -= np.median(flat)
    return flat.reshape(n, 3), voiced


def _next_head(a: int, special: list[bool]) -> int:
    """First mora at or after index a that starts a syllable."""
    while a < len(special) and special[a]:
        a += 1
    return a


def boundary_features(levels: np.ndarray, voiced: np.ndarray, special: list[bool],
                      final: bool) -> np.ndarray:
    """[n-1, N_FEATURES]: row a-1 describes accent a, i.e. a fall after the
    syllable whose head is mora a."""
    n = len(levels)
    mid = levels[:, 1]
    rows = []
    for a in range(1, n):
        p = a - 1  # nucleus mora
        q = min(_next_head(a, special), n - 1)  # where the fall shows up
        r = min(q + 1, n - 1)
        before = levels[:q].reshape(-1)
        after = levels[q:].reshape(-1)
        rows.append([
            levels[p, 1], levels[p, 2],
            levels[q, 0], levels[q, 1], levels[q, 2],
            levels[r, 1],
            levels[q, 1] - levels[p, 1],
            levels[q, 2] - levels[p, 2],
            levels[r, 1] - levels[p, 1],
            levels[q, 2] - levels[q, 0],  # slope inside the first mora after
            before.max() - after.min(),
            after.mean() - before.mean(),
            mid[:q].max() - mid[q:].max(),
            float(q - p > 1),  # nucleus syllable is heavy
            float(r < n - 1 and special[r]),
            float(a == 1),
            a / n,
            float(a == n - 1),
            float(final),
            voiced[p], voiced[q],
            float(n),
        ])
    return np.array(rows, dtype=float).reshape(-1, N_FEATURES)


def possible(n: int, special: list[bool]) -> np.ndarray:
    """Accents 1..n-1 that can be told apart inside the phrase: the nucleus
    can't be a special mora (ー ン ッ, diphthong tail), and the fall must
    land on a mora inside the phrase (else it looks like heiban)."""
    return np.array([not special[a - 1] and _next_head(a, special) < n
                     for a in range(1, n)], dtype=bool)
