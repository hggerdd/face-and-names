"""
Default configuration values scaffold.
"""

from __future__ import annotations

DEFAULTS: dict[str, object] = {
    "ui": {
        "theme": "system",
        "density": "comfortable",
    },
    "device": {"preferred": "auto"},
    "workers": {"cpu_max": 2, "gpu_max": 1},
    "logging": {"level": "info"},
}
