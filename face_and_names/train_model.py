"""
Command-line entry point to train the prediction model from verified faces.

Usage:
    uv run python -m face_and_names.train_model [--db PATH] [--model-dir DIR]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from face_and_names.app_context import initialize_app
from face_and_names.training.trainer import TrainingConfig, train_model_from_db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train face recognition classifier from verified faces."
    )
    parser.add_argument("--db", type=Path, help="SQLite database path (defaults to configured DB).")
    parser.add_argument(
        "--model-dir", type=Path, default=Path("model"), help="Output directory for artifacts."
    )
    args = parser.parse_args(argv)

    context = initialize_app(db_path=args.db)
    cfg = TrainingConfig(model_dir=args.model_dir)
    metrics = train_model_from_db(context.db_path, config=cfg)
    print(json.dumps(metrics, indent=2))
    # Pretty print confusion matrix if available
    if metrics.get("confusion_matrix"):
        labels = metrics.get("confusion_labels", [])
        print("\nConfusion matrix (rows=true, cols=pred, labels=person_id):")
        cm = metrics["confusion_matrix"]
        header = "     " + " ".join(f"{lbl:>6}" for lbl in labels)
        print(header)
        for lbl, row in zip(labels, cm):
            print(f"{lbl:>4} " + " ".join(f"{int(v):>6}" for v in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
