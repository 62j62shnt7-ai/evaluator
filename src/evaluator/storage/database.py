"""Transactions that can be shared by nested application services."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import sqlite3

_active = ContextVar('evaluator_database', default=None)

@contextmanager
def connection(path):
    path = str(Path(path).resolve())
    active = _active.get()
    if active and active[0] == path:
        yield active[1]
        return
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    token = _active.set((path, db))
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        _active.reset(token)
        db.close()
