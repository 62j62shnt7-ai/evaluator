"""Location for optional original workbooks and code PDFs used by acceptance tests."""
from __future__ import annotations
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(os.environ.get("UT_EVALUATOR_SOURCES", PROJECT_ROOT / "sources")).expanduser().resolve()



def original_workbook(filename: str) -> Path:
    import pytest

    path = SOURCE_ROOT / "workbooks" / filename
    if not path.is_file():
        pytest.skip(f"Original source unavailable: {filename}")
    return path
