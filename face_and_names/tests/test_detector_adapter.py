from pathlib import Path

import pytest

from face_and_names.services.detector_adapter import DetectorAdapter

pytest.importorskip("ultralytics")


def test_load_raises_when_weights_missing(tmp_path: Path) -> None:
    adapter = DetectorAdapter(weights_path=tmp_path / "missing.pt")
    with pytest.raises(FileNotFoundError):
        adapter.load()


def test_detect_batch_requires_load(tmp_path: Path) -> None:
    # Even with a placeholder path, detect_batch should fail until load() is called.
    adapter = DetectorAdapter(weights_path=tmp_path / "missing.pt")
    with pytest.raises(RuntimeError):
        adapter.detect_batch([])
