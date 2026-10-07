"""Per-mora speech-model features for the accent model (optional input).

A self-supervised Japanese HuBERT (ReazonSpeech, 35k h) gives one vector per
20 ms frame and layer; each mora gets the mean of its frames for a few
layers, projected to a small PCA basis fitted on training data (stored in
the accent model's checkpoint). They carry what the pitch track can miss:
voice quality, devoicing, how clearly a mora was said.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from .pitch import SAMPLE_RATE

MODEL_ID = "reazon-research/japanese-hubert-base-k2"
LAYERS = (3, 6, 9, 12)
FRAME_S = 0.02


@lru_cache(maxsize=1)
def _model():
    import torch
    from transformers import AutoModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModel.from_pretrained(
        MODEL_ID, dtype=torch.float16 if device == "cuda" else torch.float32
    ).to(device).eval()
    return model, device


def layer_frames(wav: np.ndarray) -> np.ndarray:
    """[len(LAYERS), T, 768] hidden states of the chosen layers."""
    import torch

    model, device = _model()
    x = (wav - wav.mean()) / (wav.std() + 1e-7)  # the model's feature extractor does this
    with torch.inference_mode():
        out = model(torch.from_numpy(x.astype(np.float32))[None].to(device, model.dtype),
                    output_hidden_states=True)
    return np.stack([out.hidden_states[k][0].float().cpu().numpy() for k in LAYERS])


def pool(frames: np.ndarray, spans) -> np.ndarray:
    """[n_moras, len(LAYERS), 768]: mean of the frames whose centre falls in
    each mora (the nearest frame for very short moras)."""
    T = frames.shape[1]
    centres = np.arange(T) * FRAME_S + FRAME_S / 2
    out = np.zeros((len(spans), frames.shape[0], frames.shape[2]), dtype=np.float32)
    for i, (s, e) in enumerate(spans):
        sel = (centres >= s) & (centres < e)
        if sel.any():
            out[i] = frames[:, sel].mean(axis=1)
        else:
            out[i] = frames[:, min(T - 1, int(np.argmin(np.abs(centres - (s + e) / 2))))]
    return out


def project(pooled: np.ndarray, pca: dict) -> np.ndarray:
    """[n_moras, len(LAYERS) * k] in the stored PCA basis (per layer)."""
    z = np.einsum("nld,ldk->nlk", pooled - pca["mean"][None], pca["comp"]) / pca["scale"][None]
    return z.reshape(len(pooled), -1).astype(np.float32)


def mora_features(wav: np.ndarray, spans, pca: dict) -> np.ndarray:
    return project(pool(layer_frames(wav), spans), pca)
