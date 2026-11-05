"""Small JSON action boundary for the local engineering workspace."""
from pathlib import Path
from evaluator.workspace import Workspace


def action(service, name, payload):
    workspace=Workspace(service)
    cid=payload.get('comparison_id');rev=payload.get('revision');result={}
    if name=='import':
        result=workspace.open_sheet(payload['source_id'],payload['sheet'],rev,payload.get('previous',''),payload.get('current','')) if payload.get('sheet') else workspace.auto_open(payload['source_id'],rev)
    elif name=='sample':
        filename=payload.get('name','')
        allowed={'TL-B from SAG Gas MFD to GP.xlsx','Separator-204 Inspection Report.xlsx','Separator-204 Inspection Report.xlsm'}
        if filename not in allowed:raise ValueError('Unknown project sample')
        if int(rev)!=service.workflow.revision():raise ValueError('Project changed; refresh before importing')
        source=service.add_source(Path(__file__).resolve().parents[2]/'sources'/'workbooks'/filename)
        service.inspect(source.sha256)
        result=workspace.auto_open(source.sha256,service.workflow.revision())
    elif name=='apply':workspace.apply(cid,rev,payload.get('ids',[]),payload.get('values'),payload.get('template_id'),payload.get('dimension_key'),payload.get('scenario'),payload.get('clear',False))
    elif name=='template':result=workspace.save_template(rev,payload.get('name',''),payload.get('values',{}))
    elif name=='evaluate':result=workspace.evaluate(cid,rev,payload.get('scenario'),payload.get('basis'))
    elif name=='policy':workspace.policy(cid,rev,payload.get('basis'),payload.get('scenario'))
    elif name=='correct':result={'comparison_id':workspace.correct(cid,rev,payload['id'],payload['value'])}
    elif name=='dates':result={'comparison_id':workspace.dates(cid,rev,payload.get('previous_date',''),payload.get('current_date',''))}
    elif name=='undo':service.workflow.undo(rev,'Local workspace user','Undo most recent saved action')
    else:raise ValueError('Unknown workspace action')
    return result
