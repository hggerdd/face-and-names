"""Pytest configuration shared across the test suite.

On Windows with Python 3.14, ``torch``'s DLL loading is sensitive to the
process state. Importing ``torch`` early (before pytest's collection and
assertion-rewrite machinery touches other modules) avoids
``WinError 1114`` ("A DLL initialization routine failed") when ``torch``
is imported transitively during test collection.
"""

import torch  # noqa: F401  (import side-effect is intentional)
