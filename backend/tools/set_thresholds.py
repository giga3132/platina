"""Store verdict thresholds (from tools/tune_thresholds.py) in a checkpoint.

Usage (from backend/):
  ../.venv/bin/python -m tools.set_thresholds CHECKPOINT.pt ERROR_P_FLAT ERROR_P_ACCENTED HEARD_P
"""

import sys
from pathlib import Path

import torch

path = Path(sys.argv[1])
ckpt = torch.load(path, map_location="cpu", weights_only=False)
ckpt["thresholds"] = dict(zip(["ERROR_P_FLAT", "ERROR_P_ACCENTED", "HEARD_P"], map(float, sys.argv[2:5])))
torch.save(ckpt, path)
print(path, ckpt["thresholds"])
