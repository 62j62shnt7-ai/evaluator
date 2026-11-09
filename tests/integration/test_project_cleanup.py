from pathlib import Path
import pytest
from openpyxl import Workbook
from evaluator.app_services import ProjectService
from evaluator.project_cleanup import cleanup, restore, latest_backup


def test_cleanup_and_restore(tmp_path):
    file=tmp_path/'original.xlsx';Workbook().save(file)
    service=ProjectService(tmp_path/'project');source=service.add_source(file)
    with pytest.raises(ValueError):cleanup(service,0,'reset','wrong')
    assert service.sources()
    result=cleanup(service,service.workflow.revision(),'delete',source.sha256)
    assert not service.sources()
    assert file.exists()
    assert Path(result['backup']).is_file()
    restore(service,service.workflow.revision())
    assert service.sources()[0]['source_id']==source.sha256
    before=service.workflow.revision()
    cleanup(service,before,'reset','RESET')
    assert service.workflow.revision()==before+1
    assert service.sources()==[]
    assert service.workflow.comparisons()==[]
    assert latest_backup(service)
    restore(service,service.workflow.revision())
    assert service.sources()[0]['source_id']==source.sha256


def test_reset_requires_confirmation_and_current_revision(tmp_path):
    service=ProjectService(tmp_path/'project')
    with pytest.raises(ValueError):cleanup(service,service.workflow.revision(),'reset','')
    with pytest.raises(ValueError):cleanup(service,-1,'reset','RESET')
