"""
Model artifact read/write helpers.

Artifacts live under top-level `model/`:
- classifier.pkl (classifier + scaler bundle)
- person_id_mapping.json (ordered mapping of indices -> person_id)
- embedding_config.json (config used to build embedder)
- metrics.json (train/val stats)
- version.txt (timestamp/app version marker)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib

from face_and_names.training.embedding import EmbeddingConfig, FacenetEmbedder, EmbeddingModel

logger = logging.getLogger(__name__)


@dataclass
class ModelBundle:
    embed_config: EmbeddingConfig
    embedder: EmbeddingModel
    classifier: Any
    scaler: Any
    person_ids: list[int]
    metrics: dict[str, Any]


def save_artifacts(
    model_dir: Path,
    *,
    embed_config: EmbeddingConfig,
    classifier: Any,
    scaler: Any,
    person_ids: list[int],
    metrics: dict[str, Any],
) -> None:
    """Persist model artifacts to `model_dir`."""
    model_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump({"classifier": classifier, "scaler": scaler}, model_dir / "classifier.pkl")

    (model_dir / "person_id_mapping.json").write_text(
        json.dumps({"person_ids": person_ids}, indent=2), encoding="utf-8"
    )

    (model_dir / "embedding_config.json").write_text(
        json.dumps(embed_config.__dict__, indent=2), encoding="utf-8"
    )

    (model_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    version = datetime.now(timezone.utc).isoformat()
    (model_dir / "version.txt").write_text(version, encoding="utf-8")


def load_artifacts(
    model_dir: Path,
    *,
    embedder_factory: Callable[[EmbeddingConfig], EmbeddingModel] | None = None,
) -> ModelBundle:
    """Load artifacts and construct an embedder."""
    embedder_factory = embedder_factory or FacenetEmbedder
    cls_file = model_dir / "classifier.pkl"
    mapping_file = model_dir / "person_id_mapping.json"
    embed_cfg_file = model_dir / "embedding_config.json"
    metrics_file = model_dir / "metrics.json"

    if not cls_file.exists() or not mapping_file.exists() or not embed_cfg_file.exists():
        raise FileNotFoundError(f"Model artifacts missing in {model_dir}")

    cls_data = joblib.load(cls_file)
    classifier = cls_data["classifier"]
    scaler = cls_data["scaler"]

    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    person_ids = mapping.get("person_ids") or []

    cfg_dict = json.loads(embed_cfg_file.read_text(encoding="utf-8"))
    embed_config = EmbeddingConfig(**cfg_dict)
    embedder = embedder_factory(embed_config)

    metrics = {}
    if metrics_file.exists():
        try:
            metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - defensive
            logger.warning("Failed to parse metrics.json in %s", model_dir)

    return ModelBundle(
        embed_config=embed_config,
        embedder=embedder,
        classifier=classifier,
        scaler=scaler,
        person_ids=person_ids,
        metrics=metrics,
    )
