from __future__ import annotations

from face_and_names.ui.faces_page import FacesPage


class _DummyService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def create_person(self, first: str, last: str, short_name: str | None = None) -> int:
        self.calls.append((first, last, short_name))
        return 99


class _DummyPage:
    def __init__(self) -> None:
        self.people_service = _DummyService()


def test_faces_page_create_person_signature_matches_tile_callback() -> None:
    dummy = _DummyPage()
    # Call unbound method directly with dummy self
    result = FacesPage._create_person(dummy, "Jane", "Doe", None)  # type: ignore[arg-type]
    assert result == 99
    assert dummy.people_service.calls == [("Jane", "Doe", None)]
