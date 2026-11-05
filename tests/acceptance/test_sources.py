import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from evaluator.storage.sources import register_source
from evaluator.importing.package_inventory import inventory
from tests.source_config import SOURCE_ROOT


class SourceAcceptance(unittest.TestCase):
    def test_all_ten_source_hashes_match_inventory(self):
        records = json.loads((ROOT / "evidence/source_inventory.json").read_text())
        self.assertEqual(len(records), 10)
        for record in records:
            path = SOURCE_ROOT / Path(record["copy"]).relative_to("sources")
            self.assertEqual(path.stat().st_size, record["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])

    def test_intake_preserves_hash_and_leading_sheet_whitespace(self):
        source = SOURCE_ROOT / "workbooks/TL-B from SAG Gas MFD to GP.xlsx"
        with tempfile.TemporaryDirectory() as td:
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            copied = register_source(source, Path(td))
            self.assertEqual(original, copied.sha256)
            self.assertEqual(original, hashlib.sha256(source.read_bytes()).hexdigest())
            names = [s.name for s in inventory(source).sheets]
            self.assertIn(" 2021", names)


if __name__ == "__main__":
    unittest.main()
