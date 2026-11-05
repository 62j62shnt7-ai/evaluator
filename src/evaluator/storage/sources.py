import hashlib
from pathlib import Path

from evaluator.domain.models import SourceRecord


def register_source(path: Path, project_dir: Path) -> SourceRecord:
    path, project_dir = Path(path), Path(project_dir)
    if not path.is_file():
        raise OSError(f"source is not a readable file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    sha = digest.hexdigest()
    folder=project_dir / "sources" / sha[:2] / sha
    folder.mkdir(parents=True, exist_ok=True)
    existing=sorted(p for p in folder.iterdir() if p.is_file() and not p.name.endswith('.tmp'))
    stored=existing[0] if existing else folder / path.name
    if stored.exists() and hashlib.sha256(stored.read_bytes()).hexdigest()!=sha:
        raise ValueError('Source custody integrity failure; stored bytes do not match source hash')
    if not stored.exists():
        temporary = stored.with_suffix(stored.suffix + ".tmp")
        try:
            temporary.write_bytes(path.read_bytes())
            if hashlib.sha256(temporary.read_bytes()).hexdigest()!=sha:
                raise ValueError('Source changed during intake; retry with a stable source file')
            temporary.replace(stored)
        finally: temporary.unlink(missing_ok=True)
    return SourceRecord(sha, sha, path.name, stored, path.stat().st_size)
