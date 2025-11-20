"""
PyQt application entry point (scaffold).
Wires the main window shell; business logic to be added later.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _import_qt_app():
    """
    Import QApplication, adding PyQt6's bundled Qt DLL directory on Windows if import fails.
    This keeps the app runnable in uv-managed venvs without manual PATH tweaks.
    """
    try:
        from PyQt6.QtWidgets import QApplication
        return QApplication
    except ImportError:
        if sys.platform == "win32":
            import PyQt6

            qt_bin = Path(PyQt6.__file__).parent / "Qt6" / "bin"
            if qt_bin.exists():
                os.add_dll_directory(str(qt_bin))
                os.environ["PATH"] = f"{qt_bin}{os.pathsep}{os.environ.get('PATH', '')}"
                from PyQt6.QtWidgets import QApplication

                return QApplication
        raise


def main() -> int:
    """Start the PyQt application with a placeholder main window."""
    QApplication = _import_qt_app()

    from face_and_names.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
