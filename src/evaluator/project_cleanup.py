"""Recoverable workbook deletion and clean-project actions."""
from pathlib import Path
import shutil
import sqlite3
import tempfile
from uuid import uuid4
from datetime import datetime, timezone
from evaluator.storage.database import connection
from evaluator.storage.repository import Repository
from evaluator.workflow import _LOCK


def backup_dir(service):
    return service.project_dir.parent/(service.project_dir.name+'-cleanup-backups')


def latest_backup(service):
    files=list(backup_dir(service).glob('cleanup-*.zip'))
    return max(files,key=lambda p:p.name) if files else None


def _check(service, revision):
    if int(revision)!=service.workflow.revision():
        raise ValueError('Project changed. Refresh before clearing data.')


def cleanup(service, revision, kind, confirmation):
    with _LOCK:
        _check(service,revision)
        if kind=='reset':
            if confirmation!='RESET':raise ValueError('Type RESET to start clean.')
        elif kind=='delete':
            if confirmation not in {s['source_id'] for s in service.sources()}:raise ValueError('Select an existing workbook.')
        else:raise ValueError('Unknown cleanup action')
        path=backup_dir(service)/('cleanup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-'+uuid4().hex[:8]+'.zip')
        service.repository.backup(path)
        if kind=='delete':
            service.delete_source(confirmation,_expected_revision=int(revision))
        else:
            with connection(service.repository.path) as db:
                db.execute('BEGIN IMMEDIATE')
                tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                for table in tables:
                    if table not in {'schema_info','metadata','wf_meta'}:db.execute('DELETE FROM "'+table.replace('"','""')+'"')
                db.execute('UPDATE metadata SET value=? WHERE key=?',(str(int(revision)+1),'revision'))
                db.execute('UPDATE wf_meta SET revision=? WHERE id=1',(int(revision)+1,))
            service.__init__(service.project_dir)
        return dict(comparison_id=None,reset_workspace=True,backup=str(path),message='Workbook deleted.' if kind=='delete' else 'Project cleared. Import a workbook to begin.')


def restore(service, revision):
    with _LOCK:
        _check(service,revision)
        archive=latest_backup(service)
        if archive is None:raise ValueError('No cleanup backup available.')
        service.repository.backup(backup_dir(service)/('before-restore-'+uuid4().hex+'.zip'))
        with tempfile.TemporaryDirectory() as temp:
            restored=Repository.restore_backup(archive,Path(temp)/'restored')
            source_dir=restored.path.parent/'sources'
            if source_dir.exists():shutil.copytree(source_dir,service.project_dir/'sources',dirs_exist_ok=True)
            source=sqlite3.connect(restored.path);destination=sqlite3.connect(service.repository.path)
            try:source.backup(destination)
            finally:source.close();destination.close()
        with connection(service.repository.path) as db:
            db.execute("UPDATE metadata SET value=? WHERE key='revision'",(str(int(revision)+1),))
            db.execute('UPDATE wf_meta SET revision=? WHERE id=1',(int(revision)+1,))
        service.__init__(service.project_dir)
        return dict(reset_workspace=True,message='Project restored from the latest cleanup backup.')
