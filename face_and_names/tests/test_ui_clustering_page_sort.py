from face_and_names.ui.clustering_page import _person_sort_key


def test_person_sort_key_prefers_short_name_case_insensitive() -> None:
    people = [
        {"id": 1, "short_name": "Zed", "display_name": "Zed Alpha"},
        {"id": 2, "short_name": "beta", "display_name": "Beta"},
        {"id": 3, "display_name": "alpha"},
        {"id": 4, "short_name": None, "display_name": "Delta"},
    ]

    ordered = sorted(people, key=_person_sort_key)

    # Sorted by short_name (case-insensitive), falling back to display/primary.
    assert [p["id"] for p in ordered] == [3, 2, 4, 1]
