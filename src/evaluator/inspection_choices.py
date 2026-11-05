"""Inspection suggestions affect selectors only, never measured dates or continuity."""
import json
import re


def selection(campaign):
    return [campaign['source_id'],campaign['sheet_name'],campaign['campaign']]


def date_rank(chosen, readings):
    rows=[r for r in readings if [r['source_id'],r['sheet_name'],r['campaign']]==chosen]
    dates=[r['inspection_date'] for r in rows if r['inspection_date']]
    if not dates:dates=[d for r in rows for d in json.loads(r['date_candidates']) if re.fullmatch(r'\d{4}-\d{2}(-\d{2})?',d)]
    return max(dates,default='')


def primary_campaigns(campaigns, readings):
    best={}
    for c in campaigns:
        key=c['source_id'],c['sheet_name']
        rank=(c['campaign']=='current',date_rank(selection(c),readings),c['count'])
        if key not in best or rank>best[key][0]: best[key]=(rank,c)
    return [c for _,c in best.values()]
