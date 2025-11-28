"""
Default configuration values scaffold.
"""

from __future__ import annotations

DEFAULTS: dict[str, object] = {
    "ui": {"theme": "system", "density": "comfortable", "confirm_delete_face": True},
    "db": {"path": "faces.db"},
    "device": {"preferred": "auto"},
    "workers": {"cpu_max": 2, "gpu_max": 1},
    "logging": {"level": "info"},
    "detector": {
        "default": "yolo",
        "crop_expand_pct": 0.13,
        "face_target_size": 224,
        "yolo": {"weights_path": "yolov11n-face.pt"},
    },
}
