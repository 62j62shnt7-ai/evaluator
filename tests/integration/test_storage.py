import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from evaluator.storage.repository import Repository, StaleRevisionError
from evaluator.domain.models import ChangeSet
from evaluator.storage.sources import register_source

class StorageTests(unittest.TestCase):
    def test_transaction_advances_revision_and_rejects_stale_write(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Repository(Path(td) / "db.sqlite")
            self.assertEqual(repo.transact(0, ChangeSet("note", "x")).number, 1)
            with self.assertRaises(StaleRevisionError):
                repo.transact(0, ChangeSet("note", "y"))

    def test_source_registration_is_hash_idempotent_and_backup_restores(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); incoming = root / "report.xlsx"; incoming.write_bytes(b"immutable")
            repo = Repository(root / "project" / "project.sqlite")
            first = repo.register_source(incoming)
            second = repo.register_source(incoming)
            self.assertEqual(first.sha256, second.sha256)
            self.assertEqual(first.stored_path, second.stored_path)
            self.assertEqual(first.stored_path.read_bytes(), b"immutable")
            backup = repo.backup(root / "backup.zip")
            restored = Repository.restore_backup(backup.path, root / "restored")
            self.assertEqual(restored.revision(), repo.revision())
            self.assertEqual(len(restored.sources()), 1)


class CustodyRegressionTests(unittest.TestCase):
    def test_identical_bytes_with_different_upload_names_have_one_stored_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=root/'first.xlsx';b=root/'second.xlsx'
            a.write_bytes(b'identical');b.write_bytes(b'identical')
            repo=Repository(root/'project'/'project.sqlite')
            first=repo.register_source(a);second=repo.register_source(b)
            self.assertEqual(first.stored_path,second.stored_path)
            self.assertEqual(len(list(first.stored_path.parent.iterdir())),1)
            first.stored_path.write_bytes(b'corrupted')
            with self.assertRaises(ValueError):repo.register_source(a)

class BackupBoundaryTests(unittest.TestCase):
    def test_future_schema_is_rejected_without_migration(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'future.sqlite'
            db=sqlite3.connect(path);db.execute('CREATE TABLE schema_info(version INTEGER)');db.execute('INSERT INTO schema_info VALUES(999)');db.commit();db.close()
            with self.assertRaises(ValueError):Repository(path)
            db=sqlite3.connect(path)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='sources'").fetchone());db.close()

    def test_unsafe_and_corrupt_backups_leave_destination_absent(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);archive=root/'unsafe.zip';dest=root/'restored'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape','bad')
            with self.assertRaises(ValueError):Repository.restore_backup(archive,dest)
            self.assertFalse(dest.exists());self.assertFalse((root/'escape').exists())
            source=root/'source.xlsx';source.write_bytes(b'original')
            repo=Repository(root/'project'/'project.sqlite');record=repo.register_source(source)
            with self.assertRaises(ValueError):repo.backup(record.stored_path)
            good=repo.backup(root/'backup.zip')
            corrupt=root/'corrupt.zip'
            with zipfile.ZipFile(good.path) as old,zipfile.ZipFile(corrupt,'w') as new:
                for name in old.namelist():new.writestr(name,b'corrupt' if name.startswith('sources/') else old.read(name))
            with self.assertRaises(ValueError):Repository.restore_backup(corrupt,dest)
            self.assertFalse(dest.exists());self.assertEqual(source.read_bytes(),b'original')

if __name__ == "__main__": unittest.main()
