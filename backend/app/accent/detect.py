"""Which accent did the speaker produce?

Every boundary "fall after mora a" in the phrase is scored by a gradient-
boosted classifier over pitch features (features.py), trained on native read
speech (tools/train_detector.py).
Those per-boundary probabilities are combined into a posterior over the
phrase's distinguishable accent classes:

    P(accent a)  ∝  p_a · Π_{b≠a} (1 − p_b)
    P(no fall)   ∝  Π_b (1 − p_b)        — heiban, or odaka with no particle

so the caller can ask "how likely is it that the speaker said what the
dictionary expects?" instead of trusting a single best guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from .notation import pitch_pattern
from .features import boundary_features, mora_levels, possible

MODEL = Path(__file__).with_name("detector_model.joblib")
MIN_VOICED = 0.3  # a mora with less voiced pitch than this is not evidence


@dataclass
class Detection:
    accent: int | None  # most likely accent (0 = no fall in the phrase); None = can't tell
    confidence: float  # posterior of that accent class
    classes: list[list[int]] = field(default_factory=list)  # accents per class
    posterior: list[float] = field(default_factory=list)

    @property
    def candidates(self) -> list[int]:
        """Accents indistinguishable from the detected one."""
        for accents, _ in zip(self.classes, self.posterior):
            if self.accent in accents:
                return accents
        return []

    def prob_of(self, accents: list[int]) -> float:
        """Probability the speaker produced any of `accents`."""
        return float(sum(p for cls, p in zip(self.classes, self.posterior)
                         if set(cls) & set(accents)))


@lru_cache(maxsize=1)
def _model():
    import joblib
    return joblib.load(MODEL)


def boundary_probs(features: np.ndarray) -> np.ndarray:
    return _model().predict_proba(features)[:, 1]


def posterior(p: np.ndarray, ok: np.ndarray, n: int) -> tuple[list[list[int]], list[float]]:
    """Accent classes and their probabilities from boundary probabilities."""
    p = np.clip(p, 1e-4, 1 - 1e-4)
    log_none = np.sum(np.log1p(-p[ok]))
    classes = [[0, n] + [a for a in range(1, n) if not ok[a - 1]]]
    logs = [log_none]
    for a in range(1, n):
        if ok[a - 1]:
            classes.append([a])
            logs.append(log_none - np.log1p(-p[a - 1]) + np.log(p[a - 1]))
    logs = np.array(logs)
    probs = np.exp(logs - logs.max())
    return classes, (probs / probs.sum()).tolist()


def distinguishable(n: int, a: int, b: int, observable: np.ndarray) -> bool:
    """Can the audio tell accent a from accent b? Only if some pair of
    observable moras stands in a different high/low relation under the two
    patterns (one mora's level alone says nothing: there is no reference)."""
    pa, pb = pitch_pattern(n, a), pitch_pattern(n, b)
    idx = [i for i in range(n) if observable[i]]
    for x in range(len(idx)):
        for y in range(x + 1, len(idx)):
            i, j = idx[x], idx[y]
            if (pa[i] - pa[j]) != (pb[i] - pb[j]):
                return True
    return False


def class_groups(classes: list[list[int]], n: int, observable: np.ndarray) -> list[int]:
    """Group id per class; classes the audio can't tell apart share one."""
    parent = list(range(len(classes)))

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i

    for i in range(len(classes)):
        for j in range(i + 1, len(classes)):
            if root(i) != root(j) and not distinguishable(n, classes[i][0], classes[j][0], observable):
                parent[root(j)] = root(i)
    return [root(i) for i in range(len(classes))]


def merge_classes(classes: list[list[int]], post: list[float], n: int,
                  observable: np.ndarray) -> tuple[list[list[int]], list[float]]:
    """Merge accent classes the audio can't tell apart (devoiced or
    unaligned moras, a final boundary rise), summing their probability, so
    a verdict never rests on moras that weren't measured."""
    groups: dict[int, tuple[list[int], float]] = {}
    for g, cls, p in zip(class_groups(classes, n, observable), classes, post):
        accs, total = groups.get(g, ([], 0.0))
        groups[g] = (accs + cls, total + p)
    merged = sorted(groups.values(), key=lambda g: -g[1])
    return [g[0] for g in merged], [g[1] for g in merged]


def detect_accent(times: np.ndarray, st: np.ndarray, spans: list[tuple[float, float]],
                  special: list[bool] | None = None, final: bool = False,
                  reliable: list[bool] | None = None, merge: bool = True) -> Detection:
    """times/st: the recording's pitch track (semitones, NaN = unvoiced);
    spans: (start, end) of each mora; special: syllable tails
    (kana.special_moras); final: the phrase ends the sentence;
    reliable: per mora, False where its pitch must not count as evidence
    (badly aligned, or a final boundary rise)."""
    n = len(spans)
    special = special or [False] * n
    if n < 2:
        return Detection(None, 0.0)
    levels, voiced = mora_levels(times, st, spans)
    if voiced.mean() < 0.2:  # whispered / devoiced / misaligned
        return Detection(None, 0.0)
    ok = possible(n, special)
    p = boundary_probs(boundary_features(levels, voiced, special, final))
    classes, post = posterior(p, ok, n)
    if merge:
        observable = voiced >= MIN_VOICED
        if reliable is not None:
            observable &= np.asarray(reliable, dtype=bool)
        classes, post = merge_classes(classes, post, n, observable)
    best = int(np.argmax(post))
    if len(classes) == 1:  # nothing can be told apart
        return Detection(None, 0.0, classes, post)
    return Detection(classes[best][0], post[best], classes, post)
