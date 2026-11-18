import hashlib
import json
import sys
import tempfile
import unittest

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from evaluator.storage.sources import register_source
from evaluator.importing.package_inventory import inventory
from tests.source_config import SOURCE_ROOT


RECORDS = json.loads((ROOT / "evidence/source_inventory.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("record", RECORDS, ids=[record["copy"] for record in RECORDS])
def test_source_matches_inventory(record):
    path = SOURCE_ROOT / Path(record["copy"]).relative_to("sources")
    if not path.is_file():
        pytest.skip(f"Original source unavailable: {path.name}")
    assert path.stat().st_size == record["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


class SourceAcceptance(unittest.TestCase):
    def test_intake_preserves_hash_and_leading_sheet_whitespace(self):
        source = SOURCE_ROOT / "workbooks/TL-B from SAG Gas MFD to GP.xlsx"
        if not source.is_file():
            self.skipTest("Original TL-B workbook is unavailable")
        with tempfile.TemporaryDirectory() as td:
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            copied = register_source(source, Path(td))
            self.assertEqual(original, copied.sha256)
            self.assertEqual(original, hashlib.sha256(source.read_bytes()).hexdigest())
            names = [s.name for s in inventory(source).sheets]
            self.assertIn(" 2021", names)


if __name__ == "__main__":
    unittest.main()
