"""Focused, editable row walkthrough."""
from html import escape
from evaluator.engineering.row_example import EXAMPLE, FIXED_STRESS_PSI, calculate


def row_page(values=None):
    values = dict(EXAMPLE if values is None else values)
    def field(key, label, kind='number'):
        return f'<label>{label}<input name="{key}" type="{kind}" step="any" required value="{escape(str(values.get(key, "")), quote=True)}"></label>'
    options = ''.join(f'<option {"selected" if values.get("material") == m else ""}>{escape(m)}</option>' for m in FIXED_STRESS_PSI)
    body = '<label>Material<select name="material">'+options+'</select></label>'
    for key, label in [('pd_psi','Pd (psi)'),('od_in','OD (in)'),('nominal_mm','t nominal (mm)'),('structural_mm','t structural (mm)')]:
        body += field(key,label)
    body += '<p>S is fixed by material: A106 B / A234 WPB = 20,000 psi.</p><div class="pair"><div>'
    body += field('previous_date','Previous UT date · K4','date') + field('previous_mm','Previous UT (mm) · K7')
    body += '</div><div>'+field('current_date','Current UT date · M4','date')+field('current_mm','Current UT (mm) · M7')+'</div></div>'
    body += field('selected_cr','Selected CR (mm/year), used only when calculated CR ≤ 0')
    try:
        result = calculate(values)
        rows = ''.join(f'<tr><th>{escape(k.replace("_", " "))}</th><td>{escape(format(v,".8g") if isinstance(v,float) else str(v))}</td></tr>' for k,v in result.items())
        output = '<h2>Calculated sequence</h2><table>'+rows+'</table>'
    except (ValueError, KeyError, OverflowError) as exc:
        output = '<p role="alert">'+escape(str(exc))+'</p>'
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Row 7 evaluation</title><style>body{font:16px system-ui;background:#f5f7f3;color:#173a35;max-width:850px;margin:30px auto;padding:20px}form,table{background:white;padding:24px;border-radius:12px;width:100%;box-sizing:border-box}label{display:block;margin:12px 0}input,select{display:block;padding:9px;border:1px solid #bccbc3;border-radius:5px} .pair{display:flex;gap:40px;flex-wrap:wrap}td,th{text-align:left;padding:9px;border-bottom:1px solid #ddd}button{padding:12px;background:#d9edb4;border:0;border-radius:6px}</style><a href="/">← Workspace</a><h1>Row 7 evaluation</h1><p>Example: Evaluation 11-2026, joint 2 / band 2. Edit the inputs and recalculate.</p><form action="/row-evaluation" method="get">'''+body+'''<button>Recalculate row</button></form>'''+output+'''<p>CR = (previous UT − current UT) / ((current date − previous date) / 365). Required thickness = MAX(structural, pressure thickness). Interval = MIN(10, remaining life / 2). MAWP thickness = current UT − 2 × CR used × interval. Next inspection uses 365 days/year.</p></html>'''
