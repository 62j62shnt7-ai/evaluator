"""User-facing history, proposals, calculation profiles and export screens."""
import html
import json
from decimal import Decimal, InvalidOperation
from collections import Counter
from evaluator.engineering.draft import REQUIRED

E=lambda value: html.escape(str(value if value is not None else ''),quote=True)

def numeric(value):
    if value is None: return ''
    try: return format(Decimal(str(value)),'.4f').rstrip('0').rstrip('.')
    except (InvalidOperation,ValueError): return str(value)

def hidden(name,value): return f'<input type="hidden" name="{E(name)}" value="{E(value)}">'
def person(): return '<label>Reviewer<input name="reviewer" required autocomplete="name"></label><label>Evidence / reason<input name="reason" required></label>'
def field(name,label,value='',kind='text',required=True):
    return f'<label>{E(label)}<input type="{kind}" name="{E(name)}" value="{E(value)}" {"required" if required else ""} {"step=any" if kind=="number" else ""}></label>'
def shell(title,content,notice=''):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)} · UT Review</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#f4f7f3;color:#172e29;font:15px/1.5 system-ui,sans-serif}}header{{background:#173a35;color:white;padding:20px max(24px,calc((100% - 1240px)/2));display:flex;gap:30px;align-items:center}}header a{{color:#d9edb4}}main{{max-width:1240px;padding:24px;margin:auto}}section,.card{{background:white;border:1px solid #d9e3db;border-radius:14px;padding:22px;margin:18px 0}}h1{{font-size:32px;margin:8px 0}}h2{{font-size:23px}}h3{{font-size:18px}}a{{color:#23695d}}button:disabled{{opacity:.45;cursor:not-allowed}}button,.button{{display:inline-block;background:#d9edb4;color:#173a35;border:1px solid #bdd198;border-radius:8px;padding:10px 14px;font-weight:650;text-decoration:none;cursor:pointer}}form{{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin:14px 0}}label{{display:flex;flex-direction:column;gap:5px;min-width:160px;font-size:13px}}input,select{{font:inherit;border:1px solid #bdcdc3;border-radius:7px;padding:10px;background:white;max-width:100%}}label.check{{flex-direction:row;align-items:center;max-width:600px;min-width:0}}.muted,small{{color:#63756e}}.notice{{background:#e1efca;padding:14px;border-radius:8px}}.warn{{background:#fff0dc;padding:14px;border-left:4px solid #b96c34;border-radius:7px}}.bad{{color:#a33924}}.pills{{display:flex;gap:10px;flex-wrap:wrap}}.pill{{padding:5px 10px;background:#edf3e7;border-radius:30px}}.scroll{{overflow:auto;max-height:500px}}thead th{{position:sticky;top:0;z-index:1}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:10px;border-bottom:1px solid #dde6df;text-align:left;vertical-align:top}}th{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;background:#f0f5ed}}code{{font-size:11px;overflow-wrap:anywhere}}details{{padding:12px 0;border-bottom:1px solid #dfe7e0}}summary{{cursor:pointer;font-weight:650}}.inline{{display:inline-flex;margin:0}}.danger{{background:#ffe5dc;border-color:#e2b3a2}}.ruleinputs{{display:flex;gap:12px;flex-wrap:wrap}}.result{{font-size:23px;font-weight:700}}.rowtools{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}@media(max-width:650px){{main{{padding:12px}}section{{padding:14px}}label{{width:100%}}header{{flex-wrap:wrap;gap:12px}}}}
    </style></head><body><header><strong>UT / Review</strong><a href="/">Reports & readings</a><a href="/workflow">Evaluate readings</a><a href="/advanced#exports">Exports & undo</a></header><main>{f'<p class="notice">{E(notice)}</p>' if notice else ''}{content}</main></body></html>'''

NAMES={
 'VIII_UG27_HOOP':'VIII-1 cylindrical shell · hoop pressure thickness',
 'VIII_UG27_LONG':'VIII-1 cylindrical shell · longitudinal pressure thickness',
 'VIII_UG32_ELLIP':'VIII-1 2:1 ellipsoidal head · candidate pressure thickness',
 'VIII_UG32_TORI':'VIII-1 standard torispherical head · candidate pressure thickness',
 'B31_3_304_1_2':'B31.3 straight pipe · pressure thickness',
 'B31_4_403_2_1':'B31.4 straight pipe · pressure thickness (allowances separate)',
 'B31_8_841_1_1':'B31.8 steel gas pipeline · nominal design thickness',
 'CR_LT':'Long-term wall-loss rate','CR_ST':'Short-term wall-loss rate',
 'REMAINING_LIFE':'Remaining life','API570_T_REQUIRED':'Required thickness · maximum of supplied minima'}
LABELS={'P_MPa':'Design pressure · MPa','R_inside_mm':'Inside radius · mm','S_allow_MPa':'VIII allowable stress · MPa','E_joint':'Joint efficiency · 0–1','D_inside_mm':'Inside skirt diameter · mm','L_inside_crown_mm':'Inside crown radius · mm','D_outside_mm':'Outside diameter · mm','S_B313_MPa':'B31.3 allowable stress · MPa','E_quality':'Quality factor · 0–1','W_reduction':'Weld strength reduction factor · 0–1','Y_coefficient':'Y coefficient','F_design':'B31.4 design factor · ≤0.72','E_weld':'Weld factor · 0–1','SMYS_MPa':'Specified minimum yield strength · MPa','F_class':'Location class factor','T_temp':'Temperature factor','elapsed_years':'Elapsed time · years','t_current_mm':'Current thickness · mm','t_previous_mm':'Previous thickness · mm','t_initial_mm':'Initial thickness · mm','t_required_mm':'Required thickness · mm','approved_governing_CR_mm_per_year':'Selected governing rate · mm/year','t_pressure_mm':'Pressure minimum · mm','t_structural_mm':'Structural minimum · mm'}

def standalone_calculator():
    body='<h1>Draft formula calculator</h1><p>Use <a href="/workflow">Evaluate readings</a> to calculate directly from imported readings and save revisioned results. These standalone forms show candidate arithmetic.</p>'
    for rule,keys in REQUIRED.items():
        body+=f'<details><summary>{E(NAMES.get(rule,rule))}</summary><form action="/calculate" method="post">{hidden("rule",rule)}'+''.join(field(k,LABELS.get(k,k),kind='number') for k in keys)+'<button>Calculate draft result</button></form></details>'
    return shell('Draft calculator',body)

def advanced_workflow_page(service, comparison_id=None, notice=''):
    flow=service.workflow; revision=flow.revision(); campaigns=flow.campaigns(); comps=flow.comparisons()
    comp=next((c for c in comps if c['id']==comparison_id),comps[0] if comps and not comparison_id else None)
    def options(selected=None):
        return ''.join(f'<option value="{E(json.dumps([c["source_id"],c["sheet_name"],c["campaign"]]))}" {"selected" if [c["source_id"],c["sheet_name"],c["campaign"]]==selected else ""}>{E(c["file_name"])} / {E(c["sheet_name"])} / {E(c["campaign"])} ({c["count"]} readings)</option>' for c in campaigns)
    def reviewer(reason=None):
        return field('reviewer','Reviewer',comp['actor'] if comp else '')+field('reason','Evidence / reason',reason if reason is not None else (comp['reason'] if comp else ''))
    body=f'<h1>Evaluate inspection readings</h1><p>Choose previous and current readings → confirm location matches → fill missing inputs → evaluate.</p><p class="muted">Project revision {revision} · Draft calculations are available here; there is no separate enable switch.</p>'
    if not campaigns: body+='<p class="warn">First <a href="/">upload and extract a workbook</a>. Two inspection campaigns are needed to compare readings.</p>'
    body+=f'<section id="choose"><h2>1. Choose previous and current readings</h2><p>The app matches exact section, joint / CML and position labels. You confirm that they refer to the same physical component. If a worksheet has several dated minimum-reading columns, choose two dates from that same worksheet here.</p><form action="/workflow/compare" method="post">{hidden("revision",revision)}<label>Previous readings<select name="baseline" required><option value="">Choose previous…</option>{options(comp["baseline"] if comp else None)}</select></label><label>Current readings<select name="current" required><option value="">Choose current…</option>{options(comp["current_selection"] if comp else None)}</select></label>{field("asset","Asset / equipment ID",comp["asset"] if comp else "")}{field("lifecycle","Component lifecycle ID",comp["lifecycle"] if comp else "")}{reviewer()}<label class="check"><input type="checkbox" name="continuity" value="yes" {"checked" if comp and comp["continuity"] else ""}>These are the same physical component, with no replacement between inspections.</label><button>Match locations</button></form></section>'
    if comps:
        body+='<details><summary>Open an existing comparison</summary><ul>'+''.join(f'<li><a href="/workflow?comparison={E(c["id"])}">{E(c["asset"])} · {E(c["baseline"][1])} / {E(c["baseline"][2])} → {E(c["current_selection"][1])} / {E(c["current_selection"][2])}</a> · {"Needs rebuild" if c["stale"] else "current"}</li>' for c in comps)+'</ul></details>'
    if comp:
        cid=comp['id']; rows=comp['rows']; groups=Counter(r['kind'] for r in rows)
        body+=f'<section id="comparison"><h2>2. Check matches and missing inputs · {E(comp["asset"])}</h2><p>{E(comp["lifecycle"])} · {E(comp["reason"])}</p>'
        readiness=flow.readiness(cid)
        body+=f'<div class="card"><h3>What is missing?</h3><p><strong>{readiness["ready"]} pairs ready</strong> · {readiness["unconfirmed"]} need confirmation · {readiness["missing_dates"]} missing dates · {readiness["invalid_dates"]} invalid date order · {readiness["unmatched"]} unresolved locations</p><ul>'+''.join(f'<li>{E(step)}</li>' for step in readiness['steps'])+'</ul></div>'
        body+=f'<form action="/workflow/rebuild" method="post">{hidden("comparison_id",cid)}{hidden("revision",revision)}{reviewer("Rebuild from latest readings and dates")}<button>Rebuild these pairs</button></form><p class="muted">Reuses these campaigns, asset and lifecycle. Creates a new comparison and resets mapping confirmations; prior comparisons and reports remain in history. Manual pairings must be checked again.</p>'
        body+='<details'+(' open' if readiness['missing_dates'] or readiness['invalid_dates'] else '')+'><summary>Set previous / current inspection dates</summary><p>One date applies to every reading in the selected campaign. Save each changed date, then click Rebuild these pairs above.</p>'
        for label,selection in [('Previous',comp['baseline']),('Current',comp['current_selection'])]:
            records=flow._selection(*selection); dates={r['inspection_date'] for r in records}
            chosen=next(iter(dates)) if len(dates)==1 else ''
            body+=f'<form action="/workflow/campaign-date" method="post">{hidden("comparison_id",cid)}{hidden("revision",revision)}{hidden("campaign_selection",json.dumps(selection))}{field("chosen_date",label+" inspection date",chosen or "",kind="date")}{reviewer()}<button>Save {label.lower()} date</button></form>'
        body+='</details>'
        if comp['stale']: body+='<p class="warn">Inputs changed. Click Rebuild these pairs above, then confirm the refreshed matches to enable evaluation.</p>'

        body+='<div class="pills">'+''.join(f'<span class="pill">{E(k.replace("_"," "))}: {v}</span>' for k,v in groups.items())+'</div>'
        body+='<div class="rowtools"><label>Filter issue<select id="kindFilter" onchange="filterRows()"><option value="">All</option>'+''.join(f'<option>{E(k)}</option>' for k in groups)+'</select></label><label>Search locations<input id="pairSearch" oninput="filterRows()" placeholder="Section, joint, cell…"></label></div>'
        body+='<div class="scroll"><table id="pairs"><thead><tr><th>Location evidence</th><th>Baseline</th><th>Current</th><th>Issue / match</th><th>Decision</th></tr></thead><tbody>'
        for r in rows:
            def evidence(record):
                if not record:return '—'
                location=' / '.join(json.loads(record.get('effective_location',record['location_candidates'])))
                return f'{E(record.get("effective_value",record["raw_value"]))} {E(record["raw_unit"])}<br>{E(record["inspection_date"] or "Date unresolved")}<br><small>{E(record["sheet_name"])}!{E(record["cell"])} · {E(location)}</small>'
            ref=r['current'] or r['previous']
            loc=' / '.join(json.loads(ref.get('effective_location',ref['location_candidates']))) if ref else 'Duplicate candidates — resolve explicitly'
            body+=f'<tr data-kind="{E(r["kind"])}"><td>{E(loc)}<br><small>{E(r["basis"])}</small></td><td>{evidence(r["previous"]) if r["kind"]!="ambiguous" else "<hr>".join(evidence(x) for x in r["previous_candidates"])}</td><td>{evidence(r["current"]) if r["kind"]!="ambiguous" else "<hr>".join(evidence(x) for x in r["current_candidates"])}</td><td>{E(r["kind"])}</td><td>{"Confirmed" if r["accepted"] else "Unconfirmed"}<br><small>{E("; ".join(readiness["pair_issues"][r["id"]]) or "Ready for calculation inputs")}</small></td></tr>'
        body+='</tbody></table></div>'
        for proposal in flow.proposals(cid):
            if proposal['action']!='accept_matches': body+='<details><summary>Optional: record follow-up for '+E(proposal['title'])+'</summary>'
            counts=Counter(x['reason'] for x in proposal['excluded'])
            body+=f'<div class="card"><h3>Grouped proposal: {E(proposal["title"])}</h3><p>{E(proposal["basis"])}</p><p><strong>{len(proposal["eligible_ids"])} eligible {"pairs" if proposal["action"]=="accept_matches" else "readings"}</strong>; {len(proposal["excluded"])} excluded ({E(dict(counts))}). This only confirms mapping; it does not accept equipment integrity.</p><form action="/workflow/proposal" method="post">{hidden("proposal_id",proposal["id"])}{hidden("revision",proposal["expected_revision"])}{hidden("comparison_id",cid)}{reviewer()}<button>{"Confirm eligible matches" if proposal["action"]=="accept_matches" else "Record grouped follow-up"}</button></form></div>'
            if proposal['action']!='accept_matches': body+='</details>'
        if not comp['stale']:
            old=flow._selection(*comp['baseline']); new=flow._selection(*comp['current_selection'])
            def reading_options(records):return ''.join(f'<option value="{E(r["observation_id"])}">{E(r["cell"])} · {E(r.get("effective_value",r["raw_value"]))} mm · {E(" / ".join(json.loads(r.get("effective_location",r["location_candidates"]))))}</option>' for r in records)
            body+=f'<details><summary>Resolve a duplicate or unmatched physical location</summary><form action="/workflow/pair" method="post">{hidden("comparison_id",cid)}{hidden("revision",revision)}<label>Baseline reading<select name="previous_id" required>{reading_options(old)}</select></label><label>Current reading<select name="current_id" required>{reading_options(new)}</select></label>{person()}<label class="check"><input type="checkbox" name="continuity" value="yes" required>I verified the same physical point and component lifecycle.</label><button>Confirm this pair</button></form></details>'
        body+='</section>'
        if not comp['stale']:
            body+='<details><summary>Optional: calculate required thickness from design inputs</summary><section><h2>Component pressure-thickness candidates</h2><p class="muted">Optional. Enter code-specific design inputs from component records. Use the resulting candidate with a supplied structural minimum below, or supply required thickness directly.</p>'
            for rule,keys in REQUIRED.items():
                if not rule.startswith(('VIII_','B31_')):continue
                body+=f'<details><summary>{E(NAMES[rule])}</summary><form action="/workflow/design" method="post">{hidden("comparison_id",cid)}{hidden("revision",revision)}{hidden("rule",rule)}'+''.join(field(k,LABELS.get(k,k),kind='number') for k in keys)+person()+'<label class="check"><input type="checkbox" name="applicability" value="yes" required>I checked geometry, material/factor source, code edition and applicability limits, including head geometry/appendix conditions where relevant.</label><button>Save draft pressure result</button></form></details>'
            designs=[d for d in flow.designs() if d['comparison_id']==cid]
            for d in designs:
                body+=f'<p class="card"><strong>{E(NAMES[d["rule"]])}</strong>: {E(d["result"]["value"] or "withheld")} mm · {"STALE" if d["stale"] else "DRAFT / NOT VALIDATED"}<br><small>{E(d["basis"])}</small></p>'
            body+='</section></details><section id="evaluate"><h2>3. Evaluate confirmed pairs</h2><p>This profile applies only to the checked location pairs. Use separate evaluations where required thickness, material, lifecycle or rate basis differs. Apparent historical rates are retained separately from the adopted rate.</p>'
            eligible=[r for r in rows if r['kind']=='matched' and r['accepted']]
            if not eligible:body+='<p class="warn">Confirm matches to enable evaluation: click Confirm eligible matches above, or resolve an unmatched physical location.</p>'
            else:
                history_ids=set(); ancestor=comp; by_id={c['id']:c for c in comps}
                while ancestor and ancestor['id'] not in history_ids:
                    history_ids.add(ancestor['id']); ancestor=by_id.get(ancestor.get('rebuilt_from'))
                previous_eval=next((e for e in flow.evaluations() if e['comparison_id'] in history_ids),{})
                body+='<p class="notice">Confirmations saved. Select locations and save your evaluation. Pairs with missing dates or units stay in the report with affected calculations withheld; resolve the listed inputs for numeric results.</p><p id="inputReadiness" class="warn" role="status" aria-live="polite"></p>'
                designopts=''.join(f'<option value="{E(d["id"])}">{E(NAMES[d["rule"]])}: {E(d["result"]["value"])} mm</option>' for d in designs if not d['stale'] and d['result']['value'] is not None)
                body+=f'<form id="evaluationForm" action="/workflow/evaluate" method="post">{hidden("comparison_id",cid)}{hidden("revision",revision)}<div style="width:100%"><button type="button" onclick="document.querySelectorAll(\'input[name=pair_ids]:not(:disabled)\').forEach(x=>x.checked=true)">Select all confirmed pairs</button> <button type="button" onclick="document.querySelectorAll(\'input[name=pair_ids]\').forEach(x=>x.checked=false)">Clear profile selection</button></div><div style="width:100%">'+''.join(f'<label class="check"><input type="checkbox" name="pair_ids" value="{E(r["id"])}" >{E(" / ".join(json.loads(r["current"].get("effective_location",r["current"]["location_candidates"]))))} · {E(r["previous"]["cell"])} → {E(r["current"]["cell"])} {E("; ".join(readiness["pair_issues"][r["id"]]))}</label>' for r in eligible)+'</div>'+field('required_thickness','Required thickness · mm (for remaining life)','',kind='number',required=False)+f'<label>Or use saved pressure candidate<select name="design_id"><option value="">Use manual required thickness</option>{designopts}</select></label>'+field('structural_minimum','Structural minimum if using pressure candidate · mm',kind='number',required=False)+field('adopted_rate','Manual rate override · mm/year (optional)','',kind='number',required=False)+field('year_days','Days per year convention',previous_eval.get('year_days','365.2425'),'number')+field('basis','Required-thickness and rate source / basis',previous_eval.get('basis',''))+reviewer()+'<label class="check"><input type="checkbox" name="scope" value="yes" required>I checked that this profile, structural minimum, rate and applicable loading/damage scope apply to every selected pair.</label><p class="muted" style="width:100%">Required thickness and adopted rate may be left blank for a historical comparison report. Missing inputs are listed in the report and remaining life is withheld. Calculated historical rates are used unless you enter a manual override.</p><button id="evaluateButton">Evaluate selected pairs</button></form>'
            body+='</section>'
    evals=[e for e in flow.evaluations() if not comp or e['comparison_id']==comp['id']]
    if evals:
        body+='<section><h2>Saved evaluation revisions</h2><p class="muted">Results for this comparison. Open another saved comparison above to view its results. Project exports retain every comparison.</p>'
        for evaluation in evals:
            body+=f'<details open><summary>{E(evaluation["asset"])} · input revision {evaluation["input_revision"]} · {"STALE" if evaluation["stale"] else "DRAFT / NOT VALIDATED"}</summary><p>Required: {E(evaluation['required_thickness_mm'] or 'missing')} mm · selected rate: {E(evaluation["adopted_rate_mm_year"] or "unresolved")} mm/year · {E(evaluation["basis"])}</p><div class="scroll"><table><thead><tr><th>Current / previous reading</th><th>Days</th><th>Apparent rate mm/year</th><th>Adopted rate mm/year</th><th>Remaining life years</th><th>Exceptions</th></tr></thead><tbody>'
            pairs={r['id']:r for r in evaluation['source_snapshot']['rows']}
            outside=sum('NOT_IN_EVALUATION_SCOPE' in r['issues'] for r in evaluation['rows'])
            for r in evaluation['rows']:
                if 'NOT_IN_EVALUATION_SCOPE' in r['issues']: continue
                pair=pairs[r['pair_id']]
                a=pair['previous'];b=pair['current']
                label=(b['sheet_name']+'!'+b['cell'] if b else ('AMBIGUOUS CURRENT' if r['kind']=='ambiguous' else 'CURRENT MISSING'))+' / '+(a['sheet_name']+'!'+a['cell'] if a else 'NO BASELINE')
                body+='<tr>'+''.join(f'<td>{E(v)}</td>' for v in (label,r['elapsed_days'],numeric(r['apparent_rate_mm_year']),numeric(r['adopted_rate_mm_year']),numeric(r['remaining_life_years']),', '.join(r['issues'])))+'</tr>'
            body+=f'</tbody></table></div><p class="muted">{outside} comparison rows were outside this evaluation profile; they remain in the comparison and revision export.</p></details>'
        body+='</section>'
    body+=f'<section id="exports"><h2>4. Export results & recovery</h2><p>Export an immutable ZIP containing XLSX, CSV tables, a self-contained HTML summary, source hashes, calculation inputs/results, audit records and a checksum manifest.</p><form action="/workflow/export" method="post"><button>Download project revision {revision}</button></form><form action="/workflow/backup" method="post"><button>Download complete project backup</button></form><details><summary>Restore a backup as a separate project folder</summary><form action="/workflow/restore" method="post" enctype="multipart/form-data"><label>Project backup ZIP<input type="file" name="backup" accept=".zip" required></label><button>Restore separate project</button></form></details><h3>Undo</h3><p>Undo restores the last reversible transaction as a new project revision. Existing evaluations are marked stale. Workbook addition/deletion creates an undo boundary.</p><form action="/workflow/undo" method="post">{hidden("revision",revision)}{person()}<button>Undo last reversible action</button></form><details><summary>Recent revision audit</summary><div class="scroll"><table><tr><th>Revision</th><th>Action</th><th>Reviewer</th><th>Reason</th><th>UTC</th></tr>'+''.join('<tr>'+''.join(f'<td>{E(a[k])}</td>' for k in ('revision','label','actor','reason','created'))+'</tr>' for a in flow.actions())+'</table></div></details></section>'
    saved=sorted((service.project_dir/'exports').glob('revision-*.zip'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]
    if saved: body+='<section><h2>Saved immutable export packages</h2><ul>'+''.join('<li><a href="/export/revision?name='+E(p.name)+'">'+E(p.name)+'</a></li>' for p in saved)+'</ul></section>'
    body+='''<script>function filterRows(){const k=document.getElementById('kindFilter').value;const q=document.getElementById('pairSearch').value.toLowerCase();document.querySelectorAll('#pairs tbody tr').forEach(r=>r.hidden=!!((k&&r.dataset.kind!==k)||(q&&!r.textContent.toLowerCase().includes(q))));}</script>'''
    body+='''<script>
const evaluationForm=document.getElementById('evaluationForm');
function evaluationReadiness(){
 if(!evaluationForm)return;
 const f=evaluationForm.elements, missing=[];
 if(!evaluationForm.querySelector('input[name=pair_ids]:checked:not(:disabled)'))missing.push('select at least one confirmed pair');
 if(!f.design_id.value && f.required_thickness.value && !(Number(f.required_thickness.value)>0))missing.push('required thickness must be greater than zero or blank');
 if(f.design_id.value && !(Number(f.structural_minimum.value)>0))missing.push('enter the structural minimum');
 if(f.adopted_rate.value && !(Number(f.adopted_rate.value)>0))missing.push('enter an adopted rate greater than zero or leave it blank');
 if(!(Number(f.year_days.value)>0))missing.push('enter days per year');
 for(const [key,label] of [['basis','input source / basis'],['reviewer','reviewer'],['reason','evidence / reason']])if(!f[key].value.trim())missing.push(label);
 if(!f.scope.checked)missing.push('confirm the profile applies to all selected pairs');
 document.getElementById('inputReadiness').textContent=missing.length?'To enable evaluation: '+missing.join('; ')+'.':('Ready to evaluate selected pairs.'+(f.adopted_rate.value && (f.required_thickness.value || f.design_id.value)?'':' Historical comparison report is available; add required thickness and adopted rate for remaining life.'));
 document.getElementById('evaluateButton').disabled=missing.length>0;
}
if(evaluationForm){evaluationForm.addEventListener('input',evaluationReadiness);evaluationForm.addEventListener('change',evaluationReadiness);evaluationReadiness();}
document.querySelectorAll('button[type=button]').forEach(b=>b.addEventListener('click',evaluationReadiness));
</script>'''
    return shell('Evaluate readings',body,notice)


def workflow_page(service, comparison_id=None, notice='', report_name=None):
    from evaluator.quick_ui import quick_page
    return quick_page(service,comparison_id,notice,report_name)
