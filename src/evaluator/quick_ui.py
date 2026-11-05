"""Default two-step inspection comparison. Detailed tools live under /advanced."""
from collections import Counter
import json
import re
from urllib.parse import urlencode
from evaluator.workflow_ui import E, field, hidden, numeric, shell


from evaluator.inspection_choices import date_rank as _date_rank, primary_campaigns


def import_pair_form(service, source):
    sheets=(service.inventory_for(source['source_id']) or {}).get('sheets',[])
    months={m:i for i,m in enumerate(('jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),1)}
    def hint(name):
        years=re.findall(r'20\d{2}',name);year=max(years,default='0000')
        number=re.search(r'(\d{1,2})\s*-\s*20\d{2}',name)
        month=int(number[1]) if number else next((v for k,v in months.items() if k in name.lower()),0)
        return year,month,name
    likely=[s for s in sheets if re.match(r'\s*(?:UT\b|UT-|20\d{2}|\d{1,2}-20\d{2})',s['name'],re.I) and not re.search('preview|assistant|control|import',s['name'],re.I)]
    ordered=sorted(likely,key=lambda s:hint(s['name']),reverse=True)
    current=ordered[0]['name'] if ordered else ''
    previous=ordered[1]['name'] if len(ordered)>1 else ''
    def options(chosen):
        return '<option value="">Choose inspection sheet…</option>'+''.join(f'<option value="{E(s["name"])}" {"selected" if s["name"]==chosen else ""}>{E(s["name"])}</option>' for s in sheets)
    return f'<section id="import-{E(source["source_id"])}" style="scroll-margin-top:88px"><h2>{E(source["file_name"])}</h2><p>Choose two inspection sheets. The app imports both in full and finds matching locations.</p><form class="pair-import" action="/workflow/quick-import" method="post">{hidden("source_id",source["source_id"])}{hidden("revision",service.workflow.revision())}<label for="previous-{E(source["source_id"])}">Previous inspection sheet</label><select id="previous-{E(source["source_id"])}" name="previous_sheet" required>{options(previous)}</select><label for="current-{E(source["source_id"])}">Current inspection sheet</label><select id="current-{E(source["source_id"])}" name="current_sheet" required>{options(current)}</select><button class="primary">Import both sheets &amp; find matches</button></form><small>All table sections, cells and drawing evidence are retained. The latest measured campaign on each sheet is selected automatically; source dates are not guessed.</small></section>'


def single_sheet_page(service, source_id, sheet_name):
    from evaluator.quick_workflow import single_sheet_campaigns
    campaigns=single_sheet_campaigns(service,source_id,sheet_name)
    body=f'<h1>Choose dates to compare</h1><p>{E(sheet_name)} · minimum readings only.</p>'
    if len(campaigns)<2:
        return shell('Choose inspection dates',body+'<p class="notice">This sheet has fewer than two supported measurement campaigns. The whole sheet is preserved. Choose another sheet or use the two-sheet import.</p><a href="/">Back to import</a>')
    def options():
        return '<option value="">Choose inspection date…</option>'+''.join(f'<option value="{E(c["campaign"])}">{E(c["campaign"])} · {c["count"]} Min readings</option>' for c in campaigns)
    body+=f'<section><form action="/workflow/quick-match-single" method="post">{hidden("source_id",source_id)}{hidden("sheet_name",sheet_name)}{hidden("revision",service.workflow.revision())}<label>Previous inspection date<select name="previous_campaign" required>{options()}</select></label><label>Current inspection date<select name="current_campaign" required>{options()}</select></label><button>Compare selected dates</button></form><p>Every detected measurement campaign is available. Missing or conflicting exact dates can be confirmed after reviewing the matches. Duplicate location readings remain flagged for review.</p></section><a href="/">Back to import</a>'
    body+='<table><thead><tr><th>Campaign from column header</th><th>Readings</th><th>Date evidence</th></tr></thead><tbody>'
    for c in campaigns:
        rows=service.workflow._selection(source_id,sheet_name,c['campaign'])
        dates={r['inspection_date'] for r in rows}
        candidates=sorted({d for r in rows for d in json.loads(r['date_candidates'])})
        evidence=next(iter(dates)) if len(dates)==1 and None not in dates else 'Needs confirmation: '+(', '.join(candidates) or 'no exact date')
        body+=f'<tr><td>{E(c["campaign"])}</td><td>{c["count"]}</td><td>{E(evidence)}</td></tr>'
    return shell('Choose inspection dates',body+'</tbody></table>')


def quick_page(service, comparison_id=None, notice='', report_name=None):
    flow=service.workflow; rev=flow.revision(); comps=flow.comparisons(); readings=service.readings()
    comp=next((c for c in comps if c['id']==comparison_id),comps[0] if comps and not comparison_id else None)
    campaigns=flow.campaigns()
    same_sheet=bool(comp and comp['baseline'][:2]==comp['current_selection'][:2])
    if same_sheet:
        from evaluator.quick_workflow import single_sheet_campaigns
        campaigns=single_sheet_campaigns(service,*comp['baseline'][:2])
    primary=campaigns if same_sheet else primary_campaigns(campaigns,readings)
    primary_ids={tuple([c["source_id"],c["sheet_name"],c["campaign"]]) for c in primary}
    def selection(c): return [c['source_id'],c['sheet_name'],c['campaign']]
    if comp: previous,current=comp['baseline'],comp['current_selection']
    else:
        # Suggestions affect selectors only, never inspection dates or continuity.
        group=[c for c in primary if c['source_id']==primary[0]['source_id']] if primary else []
        if len(group)<2: group=[c for c in campaigns if primary and c['source_id']==primary[0]['source_id']]
        group=sorted(group,key=lambda c:(_date_rank(selection(c),readings),c['campaign']=='current',c['sheet_name']),reverse=True)
        current=selection(group[0]) if group else None
        current_rank=_date_rank(current,readings) if current else ''
        earlier=[c for c in group[1:] if _date_rank(selection(c),readings)<current_rank]
        previous=selection((earlier or group[1:])[0]) if len(group)>1 else None
    def options(chosen):
        return '<option value="">Choose inspection…</option>'+''.join(f'<option value="{E((c["campaign"] if same_sheet else json.dumps(selection(c))))}" {"selected" if selection(c)==chosen else ""} {"data-historical hidden" if tuple(selection(c)) not in primary_ids and selection(c)!=chosen else ""}>{E(c["file_name"])} · {E(c["sheet_name"])} · {E(c["campaign"])} · {c["count"]} readings</option>' for c in campaigns)
    body='<h1>Compare inspections</h1><p>Choose two inspections. Review the matches. Get your report.</p>'
    if len(campaigns)<2: body+='<p class="notice">First <a href="/">import your inspection sheets</a>. Import the whole sheet once; all its supported table sections are included.</p>'
    action='/workflow/quick-match-single' if same_sheet else '/workflow/quick-match'
    previous_name='previous_campaign' if same_sheet else 'baseline'
    current_name='current_campaign' if same_sheet else 'current'
    context=hidden('revision',rev)
    heading='Choose previous and current readings'
    if same_sheet:
        context+=hidden('source_id',comp['baseline'][0])+hidden('sheet_name',comp['baseline'][1])
        heading='Choose dates from '+comp['baseline'][1]
    body+=f'<section><h2>{E(heading)}</h2><form action="{action}" method="post">{context}<label>Previous inspection<select name="{previous_name}" required>{options(previous)}</select></label><label>Current inspection<select name="{current_name}" required>{options(current)}</select></label><button>{"Refresh matches" if comp else "Find matches"}</button></form><small>Whole inspection campaigns, across all imported sections. Dates and physical continuity are never guessed.</small>'
    if not same_sheet:
        body+='<details><summary>Historical columns inside a sheet</summary><label class="check"><input type="checkbox" onchange="document.querySelectorAll(&quot;[data-historical]&quot;).forEach(o=>o.hidden=!this.checked)">Show historical columns</label></details>'
    body+='</section>'
    if comp:
        cid=comp['id']; rows=comp['rows']; groups=Counter(r['kind'] for r in rows)
        possible=[r for r in rows if r['kind'] in {'matched','lifecycle_mismatch'}]
        unresolved=[r for r in rows if r not in possible]
        evaluations=[e for e in flow.evaluations() if e['comparison_id']==cid]
        date_pending=0
        if evaluations:
            latest=evaluations[0]
            valid=sum(r['apparent_rate_mm_year'] is not None for r in latest['rows'])
            life=sum(r['remaining_life_years'] is not None for r in latest['rows'])
            date_pending=sum(bool({'DATE_UNRESOLVED','NONPOSITIVE_ELAPSED_TIME'} & set(r['issues'])) for r in latest['rows'])
            body+=f'<section class="notice"><h2>{"Report needs refresh" if latest["stale"] or comp["stale"] else "Your report is ready"}</h2><p>{valid} historical rates · {life} remaining-life results. All unmatched points and missing inputs are included.</p>'
            if report_name and re.fullmatch(r'revision-[0-9]{6,}-[a-f0-9]{8}\.zip',report_name): body+=f'<a class="button" href="/export/revision?name={E(report_name)}">Download report</a>'
            else: body+=f'<form action="/workflow/quick-export" method="post" class="inline">{hidden("comparison_id",cid)}<button>Download report</button></form>'
            if date_pending: body+=f'<p>{date_pending} matched locations need inspection dates before rates can be calculated. <a href="#reportDates" onclick="document.getElementById(&quot;reportDates&quot;).open=true">Set dates here</a>; your report already includes the readings.</p>'
            body+='</section>'
        body+=f'<section><h2>{len(possible)} location matches found</h2><p>{len(unresolved)} unmatched or ambiguous groups stay in the report for follow-up. You can generate it now.</p>'
        if comp['stale']: body+='<p class="notice">Readings changed. Generating the report will refresh the matches automatically.</p>'
        if possible:
            body+='<details open><summary>Review matching locations</summary><div class="scroll"><table><thead><tr><th>Location</th><th>Previous · mm</th><th>Current · mm</th></tr></thead><tbody>'
            for r in possible:
                old,new=r['previous'],r['current'];loc=' / '.join(json.loads(new.get('effective_location',new['location_candidates'])))
                body+=f'<tr><td>{E(loc)}</td><td>{E(old.get("effective_value",old["raw_value"]))}<br><small>{E(old["inspection_date"] or "Date needs confirmation")}</small></td><td>{E(new.get("effective_value",new["raw_value"]))}<br><small>{E(new["inspection_date"] or "Date needs confirmation")}</small></td></tr>'
            body+='</tbody></table></div></details>'
        if unresolved:
            body+='<details><summary>Unmatched points and duplicates</summary><p>These are retained, not automatically paired.</p><ul>'+''.join(f'<li>{E(k.replace("_"," "))}: {v}</li>' for k,v in groups.items() if k not in {'matched','lifecycle_mismatch'})+f'</ul><a href="/advanced?comparison={E(cid)}#comparison">Resolve individual locations</a></details>'
        body+=f'<form action="/workflow/quick-report" method="post" id="quickReport">{hidden("comparison_id",cid)}{hidden("revision",rev)}<label class="check" style="width:100%"><input type="checkbox" name="confirm" value="yes">I checked these exact matches are the same physical points with no intervening replacement.</label>'
        body+='<small style="width:100%">Confirm to calculate historical rates. Leave unchecked for an unconfirmed comparison report.</small>'
        body+='<details id="reportDates" style="width:100%"><summary>Add or correct dates (optional)</summary><p>Only needed where dates are missing or wrong. Saving the report applies dates and rebuilds matches in one action.</p><div class="ruleinputs">'
        for label,key,sel in [('Previous','previous_date',comp['baseline']),('Current','current_date',comp['current_selection'])]:
            rr=flow._selection(*sel);dates={r['inspection_date'] for r in rr};chosen=next(iter(dates)) if len(dates)==1 else ''
            if chosen and len(chosen)!=10:chosen='' 
            hints=sorted({d for r in rr for d in json.loads(r['date_candidates'])})
            body+=field(key,label+' inspection date',chosen or '',kind='date',required=False)
            if not chosen: body+=f'<small>{E(label)} source candidates: {E(", ".join(hints) or "none")}</small>'
        body+='</div></details><details style="width:100%"><summary>Add remaining life (optional)</summary><label class="check"><input type="checkbox" name="include_life" value="yes" id="includeLife">Include remaining-life calculations</label><div class="ruleinputs">'+field('required_thickness','Required thickness · mm',kind='number',required=False)+field('adopted_rate','Manual rate override · mm/year (optional)',kind='number',required=False)+'</div><label class="check"><input type="checkbox" name="profile_confirmed" value="yes">These inputs apply to every matching location above.</label><small>For different component inputs, use the detailed tools to evaluate separate groups.</small></details><button>Generate report</button></form><small>Audit identity and action details are recorded automatically using your local account. Calculations remain draft.</small></section>'
        body+='<details><summary>View calculated results</summary>'
        if evaluations:
            latest=evaluations[0]; pairs={r['id']:r for r in latest['source_snapshot']['rows']}
            body+='<div class="scroll"><table><thead><tr><th>Location</th><th>Previous → current mm</th><th>Rate mm/year</th><th>Life years</th><th>Needs attention</th></tr></thead><tbody>'
            for r in latest['rows']:
                pair=pairs[r['pair_id']];old,new=pair['previous'],pair['current'];ref=new or old
                loc=' / '.join(json.loads(ref.get('effective_location',ref['location_candidates']))) if ref else 'Ambiguous location'
                values=(old.get('effective_value',old['raw_value']) if old else '—')+' → '+(new.get('effective_value',new['raw_value']) if new else '—')
                body+='<tr>'+''.join(f'<td>{E(v)}</td>' for v in (loc,values,numeric(r['apparent_rate_mm_year']),numeric(r['remaining_life_years']),', '.join(i.replace('_',' ').lower() for i in r['issues'])))+'</tr>'
            body+='</tbody></table></div>'
        else: body+='<p>Generate a report to see rates and exceptions here.</p>'
        body+='</details>'
        body+='<details><summary>Open original inspection sheets</summary>'+''.join(f'<p><a href="/sheet?{E(urlencode(dict(source=sel[0],sheet=sel[1])))}">{E(label)} · {E(sel[1])} · all cells and objects</a></p>' for label,sel in [('Previous',comp['baseline']),('Current',comp['current_selection'])])+'</details>'
        body+=f'<p><a href="/workflow/batch?comparison={E(cid)}">Evaluate whole inspection with component records</a> · <a href="/advanced?comparison={E(cid)}">Detailed tools: individual pairing, component calculations, undo and backups</a></p>'
    if comps:
        body+='<details><summary>Previous comparisons</summary><ul>'+''.join(f'<li><a href="/workflow?comparison={E(c["id"])}">{E(c["asset"])} · {E(c["baseline"][1])} → {E(c["current_selection"][1])}</a></li>' for c in comps[:30])+'</ul></details>'
    body+='''<script>const quick=document.getElementById('quickReport');if(quick){quick.addEventListener('change',()=>{const f=quick.elements;f.required_thickness.required=f.profile_confirmed.required=f.confirm.required=f.include_life.checked;});}</script>'''
    return shell('Compare inspections',body,notice)
