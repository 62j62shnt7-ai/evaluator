import json
import sqlite3
import hashlib
import zipfile
import tempfile
import os
import shutil
from pathlib import PurePosixPath
from pathlib import Path
from evaluator.storage.database import connection

from evaluator.domain.models import BackupRecord, ChangeSet, Revision, SourceRecord
from evaluator.storage.sources import register_source as copy_source


class StaleRevisionError(RuntimeError):
    pass


class Repository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with connection(self.path) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_info'").fetchone():
                versions=[r[0] for r in db.execute('SELECT version FROM schema_info')]
                if versions != [1]: raise ValueError('Unsupported database schema version; open with the matching app version')
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO metadata VALUES ('revision', '0');
                CREATE TABLE IF NOT EXISTS changes (
                  revision INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources (
                  sha256 TEXT PRIMARY KEY, original_name TEXT NOT NULL,
                  stored_path TEXT NOT NULL, size_bytes INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL);
                INSERT INTO schema_info SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_info);
                CREATE TABLE IF NOT EXISTS regions (
                  source_id TEXT NOT NULL, region_id TEXT NOT NULL, status TEXT NOT NULL,
                  reason TEXT NOT NULL, PRIMARY KEY(source_id, region_id));
                CREATE TABLE IF NOT EXISTS observations (
                  source_id TEXT NOT NULL, observation_id TEXT NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(source_id, observation_id));
            """)

    def revision(self) -> int:
        with connection(self.path) as db:
            return int(db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0])

    def transact(self, expected_revision: int, changes: ChangeSet) -> Revision:
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            actual = int(db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0])
            if actual != expected_revision:
                raise StaleRevisionError(f"expected revision {expected_revision}, found {actual}")
            nxt = actual + 1
            db.execute("INSERT INTO changes VALUES (?, ?, ?)", (nxt, changes.kind, changes.payload))
            db.execute("UPDATE metadata SET value=? WHERE key='revision'", (str(nxt),))
        return Revision(nxt)

    def register_source(self, path: Path) -> SourceRecord:
        record = copy_source(path, self.path.parent)
        with connection(self.path) as db:
            db.execute("INSERT OR IGNORE INTO sources VALUES (?, ?, ?, ?)",
                       (record.sha256, record.original_name, str(record.stored_path.relative_to(self.path.parent)), record.size_bytes))
            stored=db.execute('SELECT original_name,stored_path,size_bytes FROM sources WHERE sha256=?',(record.sha256,)).fetchone()
        registered=SourceRecord(record.sha256,record.sha256,stored[0],self.path.parent/stored[1],stored[2])
        if not registered.stored_path.resolve().is_relative_to((self.path.parent/'sources').resolve()): raise ValueError('Invalid registered source path')
        if hashlib.sha256(registered.stored_path.read_bytes()).hexdigest()!=registered.sha256:
            raise ValueError('Registered source integrity failure')
        return registered

    def sources(self) -> list[SourceRecord]:
        with connection(self.path) as db:
            rows = db.execute("SELECT sha256, original_name, stored_path, size_bytes FROM sources ORDER BY sha256").fetchall()
        return [SourceRecord(sha, sha, name, self.path.parent / stored, size) for sha, name, stored, size in rows]

    def backup(self, destination: Path) -> BackupRecord:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if any(destination.resolve()==r.stored_path.resolve() for r in self.sources()): raise ValueError('Backup cannot overwrite a source file')
        if destination.resolve()==self.path.resolve(): raise ValueError('Backup cannot overwrite the project database')
        temp = destination.with_suffix(destination.suffix + '.tmp')
        try:
            with tempfile.TemporaryDirectory() as td:
                snapshot=Path(td)/'project.sqlite'
                with connection(self.path) as db:
                    target=sqlite3.connect(snapshot)
                    try: db.backup(target)
                    finally: target.close()
                records=self.sources()
                with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
                    archive.write(snapshot,'project.sqlite')
                    for record in records:
                        root=(self.path.parent/'sources').resolve()
                        if root not in record.stored_path.resolve().parents: raise ValueError('Invalid source custody path')
                        if hashlib.sha256(record.stored_path.read_bytes()).hexdigest()!=record.sha256: raise ValueError('Source integrity failure')
                        archive.write(record.stored_path,record.stored_path.relative_to(self.path.parent).as_posix())
            os.replace(temp,destination)
        finally: temp.unlink(missing_ok=True)
        return BackupRecord(destination,hashlib.sha256(destination.read_bytes()).hexdigest())

    @classmethod
    def restore_backup(cls, archive_path: Path, destination: Path) -> 'Repository':
        destination=Path(destination).resolve()
        if destination.exists(): raise ValueError('Restore destination must be a new folder')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.ut-restore-',dir=destination.parent) as td:
            stage=Path(td)/'project'; stage.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                entries=archive.infolist()
                if len(entries)>10000 or sum(x.file_size for x in entries)>2_000_000_000: raise ValueError('Backup exceeds restore limits')
                for member in entries:
                    name=member.filename
                    path=PurePosixPath(name)
                    if name.startswith('/') or '\\' in name or ':' in name or '..' in path.parts or ((member.external_attr >> 16)&0o170000)==0o120000:
                        raise ValueError('Backup contains an unsafe path')
                    if not (stage/name).resolve().is_relative_to(stage.resolve()): raise ValueError('Backup path escapes destination')
                if 'project.sqlite' not in archive.namelist(): raise ValueError('Backup is missing project.sqlite')
                archive.extractall(stage)
            repo=cls(stage/'project.sqlite')
            for record in repo.sources():
                if not record.stored_path.resolve().is_relative_to((stage/'sources').resolve()): raise ValueError('Invalid source path in backup')
                if not record.stored_path.is_file() or hashlib.sha256(record.stored_path.read_bytes()).hexdigest()!=record.sha256:
                    raise ValueError('Source hash mismatch during restore: '+record.original_name)
            os.replace(stage,destination)
        return cls(destination/'project.sqlite')
