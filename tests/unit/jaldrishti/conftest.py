"""Expose the shared JalDrishti src tree to focused unit tests."""

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "packages" / "jaldrishti" / "src"))
