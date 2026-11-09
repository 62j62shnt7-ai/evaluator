import json
from evaluator.importing.reading_identity import identity,key,component


def reading(section='S1',joint=' #12 ',band='TEE-A'):
    return dict(cell='F10',location_candidates=json.dumps([section,joint,band]))


def test_identity_normalizes_only_safe_aliases():
    assert key(identity(reading()))==key(identity(reading(joint='12',band='A')))
    assert key(identity(reading(joint='35')))!=key(identity(reading(joint='36')))
    assert key(identity(reading(section='S1')))!=key(identity(reading(section='S2')))


def test_size_separates_shared_joint_and_band():
    a=identity(dict(reading(),match_size_override='8'))
    b=identity(dict(reading(),match_size_override='4'))
    assert key(a)!=key(b)
    assert key(identity(dict(reading(),match_size_override='1 1/2')))==key(identity(dict(reading(),match_size_override='1.5')))


def test_unknown_components_are_not_guessed():
    assert component('ELBOW 45')==('elbow','A234 WPB')
    assert component('S')==('straight_pipe','A106 B')
    assert component('REDUCER 8X6')==('reducer','A234 WPB')
    assert component('EXTERNAL CHECK')==('unknown',None)


def test_import_matches_size_and_inline_identity_is_undoable(tmp_path):
    from openpyxl import Workbook
    from evaluator.app_services import ProjectService
    from evaluator.workspace import Workspace
    book=Workbook();sheet=book.active;sheet.title='UT 11-2026'
    sheet['A1']='section #1'
    for c,v in enumerate(['JOINT#','BAND','DIAM.','MIN 8-2023','MIN 11-2026','NOM.T','SCH'],1):sheet.cell(4,c,v)
    for n,vals in enumerate([[5,'T 8X4','8"',12,11,12.7,80],[5,'T 8X4','4"',10,9,8.56,80],[12,'UNCLEAR','8"',8,7,12.7,80]],5):
        for c,v in enumerate(vals,1):sheet.cell(n,c,v)
    path=tmp_path/'UT.xlsx';book.save(path)
    service=ProjectService(tmp_path/'project');source=service.add_source(path);service.inspect(source.sha256)
    workspace=Workspace(service);cid=workspace.auto_open(source.sha256,service.workflow.revision())['comparison_id']
    workspace.policy(cid,service.workflow.revision(),'row7')
    rows=workspace.state(cid)['workspace']['rows']
    assert len(rows)==3
    assert all(r['previous_id'] for r in rows)
    assert {r['match_identity']['size'] for r in rows}=={'4.0','8.0'}
    row=next(r for r in rows if r['current_cell']=='E7')
    assert any('Component type unclear' in flag for flag in row['match_flags'])
    workspace.rematch(cid,service.workflow.revision(),row['id'],{'joint':'99'})
    assert not next(r for r in workspace.state(cid)['workspace']['rows'] if r['id']==row['id'])['previous_id']
    service.workflow.undo(service.workflow.revision(),'test','Undo identity correction')
    assert next(r for r in workspace.state(cid)['workspace']['rows'] if r['id']==row['id'])['previous_id']
    workspace.rematch(cid,service.workflow.revision(),row['id'],{'component':'elbow'})
    corrected=next(r for r in workspace.state(cid)['workspace']['rows'] if r['id']==row['id'])
    assert corrected['material']=='A234 WPB'
    assert not any('Component type unclear' in flag for flag in corrected['match_flags'])
    before=service.workflow._selection(*service.workflow.comparison(cid)['baseline'])
    after=service.workflow._selection(*service.workflow.comparison(cid)['current_selection'])
    target=after[0];duplicate=dict(target,observation_id='duplicate')
    pairs=service.workflow._match_records(before,[target,duplicate],True)
    assert any(p['kind']=='ambiguous' for p in pairs)
