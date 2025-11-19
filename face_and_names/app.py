"""
PyQt application entry point (scaffold).
Wires the main window shell; business logic to be added later.
"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from face_and_names.ui.main_window import MainWindow


def main() -> int:
    """Start the PyQt application with a placeholder main window."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
