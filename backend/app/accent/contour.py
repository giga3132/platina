"""How natives actually move their pitch for a phrase with a given accent.

A small regressor learned from native recordings (tools/train_contour.py)
predicts 5 pitch points per mora, in units of the speaker's pitch range and
relative to the phrase's mean, from the phrase length, accent, mora
position, syllable structure and context (previous phrase had a drop,
sentence-final, question). Used for the expected line in the pitch chart
and, optionally, the tutor's pitch (tutor.shape_pitch).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL = Path(__file__).with_name("contour_model.joblib")
POINTS = 5


def mora_inputs(n: int, accent: int, special: list[bool], prev_drop: bool, final: bool,
                question: bool) -> np.ndarray:
    """[n, F] regressor inputs, one row per mora."""
    flat = accent in (0, n)
    rows = []
    for i in range(n):
        rows.append([
            n, i, i / max(n - 1, 1), float(flat), accent / n if not flat else 1.0,
            (i - accent + 1) if not flat else i - n,  # position relative to the nucleus
            float(not flat and i < accent), float(accent == 1), float(special[i]),
            float(i > 0 and special[i - 1]), float(prev_drop), float(final), float(question),
            float(i == n - 1),
        ])
    return np.asarray(rows, dtype=np.float32)


def available() -> bool:
    return MODEL.exists()


@lru_cache(maxsize=1)
def _model():
    import joblib
    return joblib.load(MODEL)


def predict(n: int, accent: int, special: list[bool] | None = None, prev_drop: bool = False,
            final: bool = False, question: bool = False) -> np.ndarray:
    """[n, POINTS] native-like pitch, speaker-range units, phrase mean 0."""
    special = special or [False] * n
    y = _model().predict(mora_inputs(n, accent, special, prev_drop, final, question)).reshape(n, POINTS)
    return y - y.mean()
