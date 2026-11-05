"""Read-only view of the complete imported worksheet evidence."""
from urllib.parse import urlencode
from evaluator.workflow_ui import shell,E


def sheet_page(service, source_id, sheet_name):
    sheet=service.imported_sheet(source_id,sheet_name)
    if not sheet: raise ValueError('Import this whole inspection sheet first')
    body=f'<h1>{E(sheet_name)}</h1><p><strong>Whole inspection sheet</strong> · {len(sheet["cells"])} serialized cells · {len(sheet["sections"])} sections · {len(sheet["related_parts"])} related package parts</p><a class="button" href="/source-workbook?{E(urlencode(dict(source=source_id)))}">Download untouched original workbook</a><p class="muted">{E(sheet["fidelity"])}</p>'
    body+='<section><h2>All cells and formulas</h2><input aria-label="Search sheet evidence" placeholder="Search cell, section, reading or comment" oninput="document.querySelectorAll(\'#sheetCells tbody tr\').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))"><div class="scroll"><table id="sheetCells"><thead><tr><th>Cell</th><th>Value / cached value</th><th>Formula</th></tr></thead><tbody>'
    for address,c in sheet['cells'].items():
        body+=f'<tr><td>{E(address)}</td><td>{E(c["value"])}</td><td>{E(c["formula"])}</td></tr>'
    body+='</tbody></table></div></section><section><h2>Drawings, images and comments</h2>'
    for part in sheet['related_parts']:
        url='/sheet-object?'+urlencode(dict(source=source_id,sheet=sheet_name,part=part['part']))
        body+=f'<details><summary>{E(part["part"])}</summary>'
        if part['part'].lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp','.webp')):body+=f'<img src="{E(url)}" alt="Original inspection sheet image" style="max-width:100%">'
        if part.get('texts'):body+='<p>'+E(' / '.join(part['texts']))+'</p>'
        body+=f'<a href="{E(url)}">Open original package part</a></details>'
    body+='</section><p><a href="/workflow">Back to comparison</a></p>'
    return shell(sheet_name,body)
