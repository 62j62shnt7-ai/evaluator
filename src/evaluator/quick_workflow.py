"""Small user actions that compose the revisioned services without audit typing."""
import getpass
import json
from pathlib import Path
from evaluator.storage.database import connection
from evaluator.workflow import _LOCK
from evaluator.inspection_choices import date_rank


def local_actor():
    return 'Local user: '+getpass.getuser()


def match(service, previous, current, expected_revision):
    if len(previous)!=3 or len(current)!=3: raise ValueError('Choose previous and current inspections')
    flow=service.workflow
    with _LOCK, connection(service.repository.path) as db:
        if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
        if int(expected_revision)!=flow.revision(): raise ValueError('The project changed. Refresh before matching.')
        registered={s.sha256 for s in service.repository.sources()}
        # Existing projects created by older versions gain whole-sheet evidence
        # when matching, without asking the user to repeat each import manually.
        for sid,sheet in dict.fromkeys((tuple(previous[:2]),tuple(current[:2]))):
            evidence=service.imported_sheet(sid,sheet)
            if sid in registered and (evidence is None or evidence.get('schema_version',0)<2):
                service.extract(sid,sheet,_expected_revision=flow.revision())
        names={s['source_id']:s['file_name'] for s in service.sources()}
        asset=Path(names.get(current[0],'Inspection')).stem
        return flow.compare(*previous,*current,asset,'Continuity not yet confirmed',False,local_actor(),
                            'Automatic location candidates; no physical continuity or engineering inputs inferred',expected_revision=flow.revision())



def import_inspections(service, source_id, previous_sheet, current_sheet, expected_revision):
    """Import both complete sheets and choose their latest measurement campaigns."""
    from evaluator.inspection_choices import primary_campaigns
    if not previous_sheet or not current_sheet or previous_sheet==current_sheet:
        raise ValueError('Choose two different inspection sheets. Use historical-column selection when both inspections are inside one sheet.')
    flow=service.workflow
    with _LOCK, connection(service.repository.path) as db:
        if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
        if int(expected_revision)!=flow.revision(): raise ValueError('The project changed. Refresh before importing.')
        for sheet in (previous_sheet,current_sheet): service.extract(source_id,sheet,_expected_revision=flow.revision())
        campaigns=primary_campaigns(flow.campaigns(),service.readings())
        choices={(c['source_id'],c['sheet_name']):[c['source_id'],c['sheet_name'],c['campaign']] for c in campaigns}
        old=choices.get((source_id,previous_sheet));new=choices.get((source_id,current_sheet))
        if not old or not new:return {'comparison':None,'imported_sheets':[previous_sheet,current_sheet]}
        return {'comparison':match(service,old,new,flow.revision()),'imported_sheets':[previous_sheet,current_sheet]}


def single_sheet_campaigns(service, source_id, sheet_name):
    """All measured campaigns on this sheet, ordered by their own header date."""
    import re
    readings=service.readings()
    def rank(c):
        label=c['campaign'].strip()
        month=re.fullmatch(r'(\d{1,2})[-/](20\d{2})',label)
        return f'{month[2]}-{int(month[1]):02d}' if month else date_rank([source_id,sheet_name,label],readings)
    campaigns=[dict(c) for c in service.workflow.campaigns() if c['source_id']==source_id and c['sheet_name']==sheet_name]
    for c in campaigns:c['date_rank']=rank(c)
    return sorted(campaigns,key=lambda c:(c['date_rank'],c['campaign']))


def import_single_dated_sheet(service, source_id, sheet_name, expected_revision):
    """Import evidence; leave campaign selection to the user before comparing."""
    flow=service.workflow
    with _LOCK, connection(service.repository.path) as db:
        if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
        if int(expected_revision)!=flow.revision(): raise ValueError('The project changed. Refresh before importing.')
        service.extract(source_id,sheet_name,_expected_revision=flow.revision())
        return single_sheet_campaigns(service,source_id,sheet_name)


def match_single_sheet(service, source_id, sheet_name, previous_campaign, current_campaign, expected_revision):
    with _LOCK, connection(service.repository.path) as db:
        if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
        if int(expected_revision)!=service.workflow.revision(): raise ValueError('The project changed. Refresh before matching.')
        campaigns={c['campaign']:c for c in single_sheet_campaigns(service,source_id,sheet_name)}
        if previous_campaign not in campaigns or current_campaign not in campaigns:
            raise ValueError('Choose two inspection dates from this imported sheet.')
        if previous_campaign==current_campaign:
            raise ValueError('Choose two different inspection dates.')
        old,new=campaigns[previous_campaign]['date_rank'],campaigns[current_campaign]['date_rank']
        if old and new and old>=new:
            raise ValueError('The previous inspection must be earlier than the current inspection.')
        return match(service,[source_id,sheet_name,previous_campaign],
                     [source_id,sheet_name,current_campaign],expected_revision)


def generate(service, comparison_id, expected_revision, *, confirm=False, previous_date='', current_date='',
             include_life=False, required_thickness='', adopted_rate='', profile_confirmed=False):
    flow=service.workflow; actor=local_actor()
    with _LOCK, connection(service.repository.path) as db:
        if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
        if int(expected_revision)!=flow.revision(): raise ValueError('The project changed. Refresh this page before generating the report.')
        comp=flow.comparison(comparison_id)
        if include_life and (not profile_confirmed or not confirm):
            raise ValueError('Confirm the physical matches and that the remaining-life inputs apply to every matched location')
        if include_life and not required_thickness:
            raise ValueError('Enter required thickness, or turn off remaining life')
        if not include_life: required_thickness=adopted_rate=''
        for chosen,selection in [(previous_date,comp['baseline']),(current_date,comp['current_selection'])]:
            if chosen:
                existing={r['inspection_date'] for r in flow._selection(*selection)}
                if existing!={chosen}:
                    service.resolve_campaign_date(*selection,chosen,actor,'Inspection date explicitly supplied in simple evaluation',_expected_revision=flow.revision())
        reviewed=comp
        if flow.comparison(comparison_id)['stale']:
            comp=flow.rebuild(comparison_id,flow.revision(),actor,'Automatically refresh comparison for report')
        else: comp=flow.comparison(comparison_id)
        def preview_signature(comparison):
            return sorted((r['previous_id'],r['current_id'],
                           r['previous'].get('effective_value',r['previous']['raw_value']),
                           r['current'].get('effective_value',r['current']['raw_value']),
                           r['previous'].get('effective_location',r['previous']['location_candidates']),
                           r['current'].get('effective_location',r['current']['location_candidates']))
                          for r in comparison['rows'] if r['kind'] in {'matched','lifecycle_mismatch'})
        if confirm and preview_signature(reviewed)!=preview_signature(comp):
            return {'comparison':flow.comparison(comp['id']),'evaluation':None,'needs_review':True}
        if confirm:
            with flow.change('Confirm exact matches for simple report',inputs=False,expected=flow.revision(),actor=actor,
                             reason='User confirmed exact location labels refer to the same unchanged physical points') as tx:
                flow._stale_comparison_results(tx,comp['id'])
                comp['continuity']=True
                comp['lifecycle']='Same unchanged physical points · user confirmed'
                for row in comp['rows']:
                    if row['kind']=='lifecycle_mismatch': row['kind']='matched'
                    if row['kind']=='matched': row['accepted']=True
                tx.execute('UPDATE wf_comparisons SET payload=? WHERE id=?',(json.dumps(comp),comp['id']))
        # Without confirmation, retain an exception-only report even for a comparison
        # whose matches were accepted earlier. Do not silently adopt that decision.
        if not confirm and any(r['accepted'] for r in comp['rows']):
            comp=flow.compare(*comp['baseline'],*comp['current_selection'],comp['asset'],'Continuity not confirmed for this report',
                              False,actor,'Unconfirmed comparison report requested',expected_revision=flow.revision())
        basis=('User supplied required thickness; calculated historical rate is used unless a manual rate override is entered. Applicability explicitly confirmed. '
               'No code/material basis supplied in simple mode.' if include_life else
               'Historical comparison only. No required thickness or adopted rate supplied; remaining life withheld.')
        evaluation=flow.calculate(comp['id'],required_thickness,adopted_rate,'365.2425',basis,actor,
                                  'Report generated from simple evaluation',True,pair_ids=None,expected_revision=flow.revision())
        return {'comparison':flow.comparison(comp['id']),'evaluation':evaluation}
