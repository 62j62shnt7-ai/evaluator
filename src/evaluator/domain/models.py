from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    sha256: str
    original_name: str
    stored_path: Path
    size_bytes: int


@dataclass(frozen=True)
class ChangeSet:
    kind: str
    payload: str


@dataclass(frozen=True)
class Revision:
    number: int


@dataclass(frozen=True)
class BackupRecord:
    path: Path
    sha256: str
