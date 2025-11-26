from __future__ import annotations

from unittest.mock import MagicMock

from face_and_names.services.data_reset import reset_image_data


def test_reset_image_data():
    conn = MagicMock()

    reset_image_data(conn)

    # Verify DELETE statements
    assert conn.execute.call_count == 6
    conn.execute.assert_any_call("DELETE FROM face")
    conn.execute.assert_any_call("DELETE FROM image")
    conn.commit.assert_called_once()
