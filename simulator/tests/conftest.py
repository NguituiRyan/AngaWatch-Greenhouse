"""Make the ``simulator`` package importable when pytest is run from the repo
root (e.g. ``backend\\.venv\\Scripts\\python.exe -m pytest simulator\\tests``).

The package lives at ``simulator/simulator/`` (nested, matching the Dockerfile's
``python -m simulator.run``). We add ``simulator/`` to ``sys.path`` so
``import simulator`` resolves regardless of the current working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

# This file: simulator/tests/conftest.py -> the package root is its grandparent.
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))
