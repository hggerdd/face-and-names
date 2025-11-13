import os
import platform
import subprocess
from pathlib import Path


def open_file(path: Path):
    """Open a file with the default application in a cross-platform manner."""
    resolved = str(Path(path).resolve())
    system = platform.system()

    if system == "Windows":
        os.startfile(resolved)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.run(["open", resolved], check=False)
    else:
        subprocess.run(["xdg-open", resolved], check=False)


def open_folder(path: Path):
    """Reveal a folder in the file manager."""
    resolved = str(Path(path).resolve())
    system = platform.system()

    if system == "Windows":
        os.startfile(resolved)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.run(["open", resolved], check=False)
    else:
        subprocess.run(["xdg-open", resolved], check=False)
