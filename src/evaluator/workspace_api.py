"""Small JSON action boundary for the local engineering workspace."""
from pathlib import Path
from evaluator.workspace import Workspace


def action(service, name, payload):
    workspace=Workspace(service)
    cid=payload.get('comparison_id');rev=payload.get('revision');result={}
    if name in {'delete_source','reset_project','restore_cleanup'}:
        from evaluator.project_cleanup import cleanup,restore
        return restore(service,rev) if name=='restore_cleanup' else cleanup(service,rev,'delete' if name=='delete_source' else 'reset',payload.get('source_id') if name=='delete_source' else payload.get('confirmation'))
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
    elif name == 'reference_preview':
        from decimal import InvalidOperation
        from evaluator.engineering.reference_rules import (
            GAS_SMYS_REFERENCE, GAS_TEMPERATURE_REFERENCE, GAS_BASIC_CLASS_F, GAS_CLASS_REFERENCE,
            gas_pipe_smys, gas_temperature_factor,
            LIQUID_PIPE_SMYS, LIQUID_PIPE_SMYS_REFERENCE,
        )
        from evaluator.engineering.references import material_stress

        values = payload.get('values', {})
        code = values.get('code_family')
        edition = values.get('code_edition')
        material = values.get('material')
        geometry = values.get('geometry')
        product = values.get('product_form')
        temperature = values.get('temperature_F')
        entries = []
        stress = material_stress(material, geometry, code, edition, temperature, product)
        if stress and not values.get('S_allow_psi'):
            entries.append(dict(label='Allowable stress S', value=f"{stress['S_allow_psi']} psi", reference=stress['reference']))
        if code == 'ASME B31.4' and edition == '2025' and geometry == 'straight_pipe' and not values.get('SMYS_psi'):
            grade = LIQUID_PIPE_SMYS.get(material)
            if grade:
                smys, line = grade
                entries.append(dict(label='SMYS', value=f'{int(smys):,} psi',
                                    reference=f'{LIQUID_PIPE_SMYS_REFERENCE}, line {line}'))
        if code == 'ASME B31.8' and edition == '2025' and geometry == 'straight_pipe':
            factor = GAS_BASIC_CLASS_F.get(values.get('gas_basic_class'))
            if factor and not values.get('F_class'):
                entries.append(dict(label='Basic design factor F', value=factor, **GAS_CLASS_REFERENCE))
            smys = gas_pipe_smys(material, product)
            if smys is not None and not values.get('SMYS_psi'):
                entries.append(dict(label='SMYS', value=f'{smys:,} psi', **GAS_SMYS_REFERENCE))
            if temperature and not values.get('T_temp'):
                try:
                    factor = gas_temperature_factor(temperature)
                except (ValueError, InvalidOperation):
                    pass
                else:
                    entries.append(dict(label='Temperature factor T', value=str(factor), **GAS_TEMPERATURE_REFERENCE))
        return {'entries': entries}
    elif name=='apply':result=workspace.apply(cid,rev,payload.get('ids',[]),payload.get('values'),payload.get('template_id'),payload.get('dimension_key'),payload.get('scenario'),payload.get('clear',False),payload.get('fill_missing',False))
    elif name=='apply_code_basis':
        result=workspace.apply_code_basis(cid,rev,payload['scope'],payload.get('ids',[]),payload.get('values',{}))
    elif name=='review_workbook_pipes':
        if payload.get('confirmed') is not True:raise ValueError('Confirm the workbook inputs before saving.')
        result=workspace.review_workbook_pipes(cid,rev,payload.get('ids',[]))
    elif name=='template':result=workspace.save_template(rev,payload.get('name',''),payload.get('values',{}))
    elif name=='evaluate':result=workspace.evaluate(cid,rev,payload.get('scenario'),payload.get('basis'))
    elif name=='policy':workspace.policy(cid,rev,payload.get('basis'),payload.get('scenario'))
    elif name=='correct':result={'comparison_id':workspace.correct(cid,rev,payload['id'],payload['value'])}
    elif name=='dates':result={'comparison_id':workspace.campaign_dates(cid,rev,payload['campaign_dates']) if payload.get('campaign_dates') else workspace.dates(cid,rev,payload.get('previous_date',''),payload.get('current_date',''))}
    elif name=='pair':result={'comparison_id':workspace.pair_source_row(cid,rev,payload['id'])}
    elif name=='identity':result={'comparison_id':workspace.rematch(cid,rev,payload.get('id'),payload.get('values'),payload.get('previous_id'))}
    elif name=='undo':service.workflow.undo(rev,'Local workspace user','Undo most recent saved action')
    elif name=='asset_list':result={'assets':service.assets.assets()}
    elif name=='asset_create':service.assets.create_asset(payload['asset_id'],payload['label'],who=payload['who']);result={'assets':service.assets.assets()}
    elif name=='asset_input':
        version=service.assets.set_input(payload['asset_id'],payload['key'],payload['value'],payload['unit'],who=payload['who'],why=payload['why'],source_type=payload.get('source_type','manual'),source_detail=payload.get('source_detail'))
        result={'asset_id':payload['asset_id'],'key':payload['key'],'version':version}
    elif name=='asset_history':result={'history':service.assets.history(payload['asset_id'],payload.get('key'))}
    elif name=='readings_profiles':
        from evaluator.readings_only import ReadingsOnlyService
        sources=[]
        for source in service.sources():
            inventory=service.inventory_for(source['source_id']) or {}
            sources.append(dict(source,sheets=[row['name'] for row in inventory.get('sheets',[])]))
        result={'layouts':list(ReadingsOnlyService(service).profiles().values()),'calculation_profiles':list(__import__('evaluator.template_engine.row_calculations',fromlist=['load_calculation_profiles']).load_calculation_profiles().values()),'assets':service.assets.assets(),'sources':sources}
    elif name=='readings_preview':
        from evaluator.readings_only import ReadingsOnlyService
        result=ReadingsOnlyService(service).preview(payload['source_id'],payload['sheet'])
    elif name=='readings_save_layout':
        from evaluator.readings_only import ReadingsOnlyService
        result=ReadingsOnlyService(service).save_custom_profile(payload['profile'],who=payload['who'],confirmed=bool(payload.get('confirmed')))
    elif name=='readings_import':
        from evaluator.readings_only import ReadingsOnlyService
        result=ReadingsOnlyService(service).import_sheet(payload['source_id'],payload['sheet'],payload['layout_profile_id'],payload['asset_id'])
    elif name=='readings_pairs':
        from evaluator.readings_only import ReadingsOnlyService
        result={'pairs':ReadingsOnlyService(service).pairs(payload.get('source_id')),'results':ReadingsOnlyService(service).results()}
    elif name=='readings_evaluate':
        from evaluator.readings_only import ReadingsOnlyService
        result=ReadingsOnlyService(service).evaluate(payload['pair_id'],payload['calculation_profile_id'])
    elif name=='readings_export':
        from evaluator.readings_only import ReadingsOnlyService
        target=ReadingsOnlyService(service).export_copy(payload['source_id'],result_ids=payload.get('result_ids'))
        result={'path':str(target),'name':target.name}
    else:raise ValueError('Unknown workspace action')
    if name in {'import','sample'} and result.get('comparison_id'):
        workspace.policy(result['comparison_id'], service.workflow.revision(), 'assigned')
    return result
