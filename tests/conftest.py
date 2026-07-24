"""Root conftest: ensure src/backend is importable."""

import sys
from pathlib import Path

# Add src/backend to sys.path so tests can import `app.*`
backend_path = Path(__file__).parent.parent / "src" / "backend"
sys.path.insert(0, str(backend_path))
