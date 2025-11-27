from pathlib import Path

import cv2  # noqa: F401
import pytest
import ultralytics  # noqa: F401

from face_and_names.services.detector_adapter import DetectorAdapter


def test_detector_dependencies_present() -> None:
    assert ultralytics is not None
    assert cv2 is not None


def test_load_raises_when_weights_missing(tmp_path: Path) -> None:
    adapter = DetectorAdapter(weights_path=tmp_path / "missing.pt")
    with pytest.raises(FileNotFoundError):
        adapter.load()


def test_detect_batch_requires_load(tmp_path: Path) -> None:
    # Even with a placeholder path, detect_batch should fail until load() is called.
    adapter = DetectorAdapter(weights_path=tmp_path / "missing.pt")
    with pytest.raises(RuntimeError):
        adapter.detect_batch([])
