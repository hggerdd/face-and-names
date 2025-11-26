"""
Headless training pipeline for Face-and-Names.

Steps:
1) Load verified faces from SQLite (person_id present; optional verified flag).
2) Decode blobs to RGB, compute embeddings via reusable embedder.
3) Train classifier with per-class-aware split and balanced SVC by default.
4) Persist artifacts under top-level `model/`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Tuple

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from face_and_names.models.db import connect
from face_and_names.training.data_loader import load_verified_faces
from face_and_names.training.embedding import EmbeddingConfig, EmbeddingModel, FacenetEmbedder
from face_and_names.training.model_io import save_artifacts

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    model_dir: Path = Path("model")
    test_size: float = 0.2
    random_state: int = 42
    min_class_size: int = 2
    metrics_min_samples: int = 50
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)


def _default_classifier_factory() -> SVC:
    return SVC(kernel="linear", probability=True, class_weight="balanced", random_state=42)


def _split_per_person(
    labels: list[int], cfg: TrainingConfig
) -> Tuple[list[int], list[int], set[int]]:
    """
    Split indices into train/test per person.
    - Persons with > metrics_min_samples get 80/20 split (or cfg.test_size).
    - Persons with <= threshold go entirely to train.
    Returns (train_indices, test_indices, eligible_ids_for_metrics)
    """
    train_idx: list[int] = []
    test_idx: list[int] = []
    eligible: set[int] = set()
    rng = np.random.default_rng(cfg.random_state)
    # group indices by person
    by_person: dict[int, list[int]] = {}
    for idx, pid in enumerate(labels):
        by_person.setdefault(pid, []).append(idx)
    for pid, idxs in by_person.items():
        if len(idxs) > cfg.metrics_min_samples:
            eligible.add(pid)
            idxs_copy = idxs[:]
            rng.shuffle(idxs_copy)
            split_at = max(1, int(len(idxs_copy) * (1 - cfg.test_size)))
            train_idx.extend(idxs_copy[:split_at])
            test_idx.extend(idxs_copy[split_at:])
        else:
            train_idx.extend(idxs)
    return train_idx, test_idx, eligible


def train_model_from_db(
    db_path: Path,
    *,
    config: TrainingConfig | None = None,
    embedder: EmbeddingModel | None = None,
    classifier_factory: Callable[[], object] | None = None,
    progress: Callable[[str, int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    """
    Train a classifier from verified faces and persist artifacts.
    Evaluation (confusion matrix) is computed only for persons with > metrics_min_samples images.
    For those, an 80/20 per-person split (or cfg.test_size) is used: 80% train, 20% test for metrics.
    Persons with <= threshold go entirely to the training set and do not appear in metrics.
    Returns metrics dict.
    """
    cfg = config or TrainingConfig()
    embedder = embedder or FacenetEmbedder(cfg.embedding)
    classifier_factory = classifier_factory or _default_classifier_factory

    conn = connect(db_path)
    samples = load_verified_faces(conn)
    if progress:
        progress("loaded", len(samples), len(samples))
    if not samples:
        raise RuntimeError("No verified faces available for training")

    # Drop classes with insufficient samples when a split is needed
    counts: dict[int, int] = {}
    for s in samples:
        counts[s.person_id] = counts.get(s.person_id, 0) + 1
    dropped = {pid for pid, cnt in counts.items() if cnt < cfg.min_class_size}
    if dropped:
        logger.warning(
            "Dropping %d classes with < %d samples: %s",
            len(dropped),
            cfg.min_class_size,
            sorted(dropped),
        )
        samples = [s for s in samples if s.person_id not in dropped]
        if not samples:
            raise RuntimeError("All classes were dropped due to insufficient samples")

    labels = [s.person_id for s in samples]
    train_idx, val_idx, eligible_ids = _split_per_person(labels, cfg)

    if should_stop and should_stop():
        raise RuntimeError("Training cancelled before embedding")
    embeddings = []
    total = len(samples)
    for idx, sample in enumerate(samples, start=1):
        if should_stop and should_stop():
            raise RuntimeError("Training cancelled during embedding")
        vec = embedder.embed_images([sample.image])
        if vec.size == 0:
            continue
        embeddings.append(vec[0])
        if progress:
            progress(f"embedding {sample.source}", idx, total)
    if not embeddings:
        raise RuntimeError("No embeddings produced")
    embeddings = np.stack(embeddings, axis=0)
    scaler = StandardScaler()
    X_train = scaler.fit_transform(np.array([embeddings[i] for i in train_idx]))
    y_train = np.array([labels[i] for i in train_idx])

    if should_stop and should_stop():
        raise RuntimeError("Training cancelled before classifier fit")
    clf = classifier_factory()
    clf.fit(X_train, y_train)

    acc = None
    cm = None
    cm_norm = None
    cm_labels: list[int] = []
    y_true = []
    y_pred = []
    if val_idx:
        X_val = scaler.transform(np.array([embeddings[i] for i in val_idx]))
        y_val = np.array([labels[i] for i in val_idx])
        preds = clf.predict(X_val)
        acc = float(accuracy_score(y_val, preds))
        y_true = y_val.tolist()
        y_pred = preds.tolist()
        # Only include eligible IDs
        cm_labels = sorted(list(eligible_ids))
        if cm_labels:
            cm = confusion_matrix(y_true, y_pred, labels=cm_labels)
            with np.errstate(all="ignore"):
                cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)

    metrics = {
        "samples": len(samples),
        "classes": len(set(labels)),
        "dropped_classes": sorted(dropped),
        "train_size": len(train_idx),
        "val_size": len(val_idx),
        "val_accuracy": acc,
        "eligible_for_metrics": sorted(list(eligible_ids)),
        "confusion_matrix": cm.tolist() if cm is not None else None,
        "confusion_matrix_normalized": cm_norm.tolist() if cm_norm is not None else None,
        "confusion_labels": cm_labels,
        "y_true": y_true,
        "y_pred": y_pred,
    }

    # Persist artifacts
    person_ids_order = list(clf.classes_) if hasattr(clf, "classes_") else sorted(set(labels))
    save_artifacts(
        cfg.model_dir,
        embed_config=cfg.embedding,
        classifier=clf,
        scaler=scaler,
        person_ids=[int(pid) for pid in person_ids_order],
        metrics=metrics,
    )

    logger.info(
        "Training complete: %d samples, %d classes, val_accuracy=%s",
        metrics["samples"],
        metrics["classes"],
        metrics["val_accuracy"],
    )
    return metrics
