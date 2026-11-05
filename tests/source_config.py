"""Location for optional original workbooks and code PDFs used by acceptance tests."""
from __future__ import annotations
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(os.environ.get("UT_EVALUATOR_SOURCES", PROJECT_ROOT / "sources")).expanduser().resolve()
