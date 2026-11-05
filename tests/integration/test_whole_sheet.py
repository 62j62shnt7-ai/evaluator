import hashlib
from openpyxl import Workbook
from openpyxl.comments import Comment
from evaluator.app_services import ProjectService
from tests.source_config import SOURCE_ROOT


def test_unknown_whole_sheet_preserves_cells_formulas_and_comments(tmp_path):
    path=tmp_path/'unfamiliar.xlsx'
    wb=Workbook(); ws=wb.active; ws.title='Inspection'
    ws.append(['CMLS','MIN','MAX','Nominal','Comments'])
    ws.append(['A',8,9,10,'historical evidence'])
    ws['F2']='=B2+C2'; ws['B2'].comment=Comment('original comment','Inspector')
    ws.merge_cells('A4:F4'); ws['A4']='NOZZLES'
    wb.save(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    service=ProjectService(tmp_path/'project'); source=service.add_source(path)
    result=service.extract(source.sha256,'Inspection')
    sheet=service.imported_sheet(source.sha256,'Inspection')
    assert result['imported']==0
    assert sheet['source_sha256']==digest
    assert sheet['cells']['C2']['value']=='9'
    assert sheet['cells']['F2']['formula']=='B2+C2'
    assert sheet['merged_regions']==['A4:F4']
    assert 'historical evidence' in sheet['worksheet_xml']
    assert any('comments' in part['part'] for part in sheet['related_parts'])
    assert sheet['sections'][0]['name']=='CMLS'
    assert service.imported_sheets()[0]['cell_count']==len(sheet['cells'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    service.delete_source(source.sha256)
    assert service.imported_sheets()==[]


def test_real_separator_full_evidence_and_reimport(tmp_path):
    from pathlib import Path
    from zipfile import ZipFile
    import xml.etree.ElementTree as ET
    path=SOURCE_ROOT/'workbooks/Separator-204 Inspection Report.xlsx'
    service=ProjectService(tmp_path/'project'); source=service.add_source(path)
    service.extract(source.sha256,'UT Jan 2026')
    sheet=service.imported_sheet(source.sha256,'UT Jan 2026')
    assert [s['name'] for s in sheet['sections']]==['CMLS','NOZZLES']
    assert sheet['cells']['E83']['value']=='MIN'
    assert sheet['cells']['F83']['value']=='MAX'
    assert sheet['cells']['N118']['value']=='Comments'
    assert all(a in sheet['cells'] for a in ('E84','F84','H84','I84','K84','L84','N121'))
    assert any('drawing' in p['part'] for p in sheet['related_parts'])
    with ZipFile(source.stored_path) as z:
        xml=z.read(sheet['worksheet_part']).decode('utf-8')
        assert sheet['worksheet_xml']==xml
        count=len(ET.fromstring(xml).findall('.//{*}sheetData/{*}row/{*}c'))
        assert len(sheet['cells'])==count
    service.extract(source.sha256,'UT Jan 2026')
    assert len(service.imported_sheets())==1
    assert service.imported_sheet(source.sha256,'UT Jan 2026')==sheet


def test_real_tlb_imports_every_section_and_package_dependency(tmp_path):
    from pathlib import Path
    path=SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx'
    service=ProjectService(tmp_path/'project'); source=service.add_source(path)
    service.extract(source.sha256,'UT-FEB 2025 Sec-1&2')
    sheet=service.imported_sheet(source.sha256,'UT-FEB 2025 Sec-1&2')
    assert {'SECTION 1','SECTION 2'} <= {s['name'] for s in sheet['sections']}
    assert {'R48','R54'} <= set(sheet['cells'])
    assert sheet['dependencies']
    assert sheet['related_parts']
    assert source.sha256==hashlib.sha256(source.stored_path.read_bytes()).hexdigest()


def test_whole_sheet_undo_export_and_original_bytes(tmp_path):
    import json
    import zipfile
    path=tmp_path/'Inspection.xlsx'
    wb=Workbook();wb.active.title='Full sheet';wb.active.append(['Nominal','MIN','MAX','Notes']);wb.active.append([10,8,9,'keep every column']);wb.save(path)
    original=path.read_bytes()
    service=ProjectService(tmp_path/'project');source=service.add_source(path)
    service.extract(source.sha256,'Full sheet')
    service.workflow.undo(service.workflow.revision(),'local test','undo whole import')
    assert service.imported_sheet(source.sha256,'Full sheet') is None
    service.extract(source.sha256,'Full sheet')
    with zipfile.ZipFile(service.workflow.export_revision()) as z:
        evidence=json.loads(z.read('whole_sheets.json'))
        assert evidence[0]['cells']['D2']['value']=='keep every column'
        original_member=next(n for n in z.namelist() if n.startswith('source_workbooks/'))
        assert z.read(original_member)==original
    assert path.read_bytes()==original


def test_simple_match_upgrades_legacy_partial_imports_automatically(tmp_path):
    from pathlib import Path
    from evaluator.quick_workflow import match
    from evaluator.storage.database import connection
    path=SOURCE_ROOT/'workbooks/Separator-204 Inspection Report.xlsx'
    service=ProjectService(tmp_path/'project');source=service.add_source(path)
    service.extract(source.sha256,'UT Jan 2026')
    with connection(service.repository.path) as db:db.execute('DELETE FROM imported_sheets')
    result=match(service,[source.sha256,'UT Jan 2026','2024-08-25'],[source.sha256,'UT Jan 2026','current'],service.workflow.revision())
    assert service.imported_sheet(source.sha256,'UT Jan 2026') is not None
    assert sum(r['kind']=='lifecycle_mismatch' for r in result['rows'])==29


def test_import_two_actual_sheets_and_match_in_one_action(tmp_path):
    from pathlib import Path
    from evaluator.quick_workflow import import_inspections
    service=ProjectService(tmp_path/'project')
    source=service.add_source(SOURCE_ROOT/'workbooks/Separator-204 Inspection Report.xlsx')
    service.inspect(source.sha256)
    result=import_inspections(service,source.sha256,'UT Aug-2024','UT Jan 2026',service.workflow.revision())
    assert len(service.imported_sheets())==2
    assert result['comparison']['baseline']==[source.sha256,'UT Aug-2024','current']
    assert sum(r['kind']=='lifecycle_mismatch' for r in result['comparison']['rows'])==29
    assert {'CMLS','NOZZLES'}=={s['name'] for s in service.imported_sheet(source.sha256,'UT Jan 2026')['sections']}


def test_whole_evidence_survives_when_a_sheet_has_no_supported_readings(tmp_path):
    from evaluator.quick_workflow import import_inspections
    path=tmp_path/'unknown.xlsx';wb=Workbook();wb.active.title='Old';wb.active.append(['whole old sheet']);wb.create_sheet('New').append(['whole new sheet']);wb.save(path)
    service=ProjectService(tmp_path/'project');source=service.add_source(path);service.inspect(source.sha256)
    result=import_inspections(service,source.sha256,'Old','New',service.workflow.revision())
    assert result['comparison'] is None
    assert len(service.imported_sheets())==2


def test_older_separator_cml_header_is_listed_as_a_complete_section(tmp_path):
    from pathlib import Path
    service=ProjectService(tmp_path/'project');source=service.add_source(SOURCE_ROOT/'workbooks/Separator-204 Inspection Report.xlsx')
    service.extract(source.sha256,'UT Aug-2024')
    sheet=service.imported_sheet(source.sha256,'UT Aug-2024')
    assert [s['name'] for s in sheet['sections']]==['CMLS','NOZZLES']
    assert 'N92' in sheet['sections'][0]['cells']
    assert 'N114' in sheet['sections'][1]['cells']
