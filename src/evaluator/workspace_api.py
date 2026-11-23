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
        if not payload.get('sheet'):
            raise ValueError('Choose the UT worksheet to use for this comparison.')
        result=workspace.open_sheet(payload['source_id'],payload['sheet'],rev,payload.get('previous',''),payload.get('current',''),ut_only=True,
                                    straight_pipe_fitting_screen=payload.get('straight_pipe_fitting_screen', False))
    elif name=='sample':
        filename=payload.get('name','')
        allowed={'TL-B from SAG Gas MFD to GP.xlsx','Separator-204 Inspection Report.xlsx','Separator-204 Inspection Report.xlsm'}
        if filename not in allowed:raise ValueError('Unknown project sample')
        if int(rev)!=service.workflow.revision():raise ValueError('Project changed; refresh before importing')
        source=service.add_source(Path(__file__).resolve().parents[2]/'sources'/'workbooks'/filename)
        service.inspect(source.sha256)
        result=workspace.auto_open(source.sha256,service.workflow.revision())
    elif name == 'prior_code_bases':
        return {'bases': workspace.prior_code_bases(cid)}
    elif name == 'location_preview':
        from evaluator.batch import NUMERIC_OVERRIDES, TEXT_OVERRIDES, PROFILE_TEXT
        if int(rev) != service.workflow.revision():
            raise ValueError('Project changed. Refresh the location to preview again.')
        values = payload.get('values', {})
        allowed = (NUMERIC_OVERRIDES | TEXT_OVERRIDES | set(PROFILE_TEXT)) - {'sleeve_assessment_record'}
        values = {key: str(value) for key, value in values.items() if key in allowed}
        row = service.batch.preview(cid, options={'basis':'assigned','workspace_review':True},
                                    draft=(payload['id'], values, payload.get('readings', {})))
        from evaluator.engineering.batch_rules import pressure_psi
        trace = row.get('outputs', {}).get('trace', {}).get('forecast_mawp_MPa', {})
        pressure = row.get('forecast_mawp_MPa')
        years = trace.get('forecast_years') or (row.get('row7') or {}).get('interval')
        fitting = row.get('fitting_check')
        if fitting:
            years = fitting['projection_years']
        from decimal import Decimal
        physical = None
        if years is not None and row.get('adopted_rate_mm_year') is not None:
            physical = str(Decimal(row['current_thickness_mm']) -
                           Decimal(row['adopted_rate_mm_year']) * Decimal(str(years)))
        return dict(observed=row.get('apparent_rate_mm_year'), adopted=row.get('adopted_rate_mm_year'),
                    wall=physical, credited=trace.get('net_thickness_mm'), date=row.get('due_date'),
                    pressure_psi=pressure_psi(pressure),
                    fitting=fitting, fitting_progress=row.get('fitting_progress'), issues=list(dict.fromkeys(
                        row['issues'] + row.get('outputs', {}).get('issues', {}).get('forecast_mawp_MPa', []))))
    elif name == 'reference_preview':
        from decimal import InvalidOperation
        from evaluator.engineering.reference_rules import (
            GAS_SMYS_REFERENCE, GAS_TEMPERATURE_REFERENCE, GAS_BASIC_CLASS_F, GAS_CLASS_REFERENCE,
            gas_pipe_smys, gas_temperature_factor,
            LIQUID_PIPE_SMYS, LIQUID_PIPE_SMYS_REFERENCE,
        )
        from evaluator.engineering.references import b313_reference_factors, material_stress

        values = payload.get('values', {})
        code = values.get('code_family')
        edition = values.get('code_edition')
        material = values.get('material')
        geometry = values.get('geometry')
        product = values.get('product_form')
        temperature = values.get('temperature_F')
        entries = []
        stress = material_stress(material, geometry, code, edition, temperature, product,
                                 material_thickness_mm=values.get('material_thickness_mm'),
                                 material_condition_reference=values.get('material_condition_reference'))
        if stress and not values.get('S_allow_psi'):
            entries.append(dict(key='S_allow_psi', label='Allowable stress S', value=f"{stress['S_allow_psi']} psi", reference=stress['reference'], notes=stress.get('notes', [])))
        factor_labels = {'E_quality': 'Quality factor E', 'W_reduction': 'Weld reduction factor W', 'Y_coefficient': 'Coefficient Y'}
        for key, (value, reference) in b313_reference_factors(material, geometry, code, edition, temperature).items():
            if values.get(key) in (None, ''):
                entries.append(dict(key=key, label=factor_labels[key], value=value, reference=reference))
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
    elif name == 'prefill_sheet_materials':
        result = workspace.apply_sheet_materials(
            cid, rev, payload.get('materials', {}), replace_existing=payload.get('replace_existing') is True,
        )
    elif name=='review_workbook_pipes':
        if payload.get('confirmed') is not True:raise ValueError('Confirm the workbook inputs before saving.')
        result=workspace.review_workbook_pipes(cid,rev,payload.get('ids',[]),payload.get('alternate_records'))
    elif name=='review_fittings':
        if payload.get('confirmed') is not True:raise ValueError('Confirm the documented fitting limits before saving.')
        result=workspace.review_fittings(cid,rev,payload.get('entries',{}))
    elif name == 'record_sleeve_assessment':
        if payload.get('confirmed') is not True:
            raise ValueError('Confirm that this is an approved assembly assessment.')
        result = workspace.record_sleeve_assessment(cid, rev, payload['id'], payload.get('values', {}))
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
    if name in {'import','sample'} and result.get('comparison_id') and not result.get('reused'):
        workspace.policy(result['comparison_id'], service.workflow.revision(), 'assigned')
    result.setdefault('revision', service.workflow.revision())
    return result
