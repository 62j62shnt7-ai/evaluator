"""Pipeline project assessment form and saved calculation trace."""

from html import escape
from urllib.parse import urlencode

from evaluator.desk_ui import shell
from evaluator.engineering.pipeline_corrosion import INPUT_LABELS, LIMIT_LABELS, history


def page(service, form=None, error=''):
    form = form or {}
    workflow = service.workflow
    labels = {'segment': 'Pipeline segment', 'defect': 'Defect ID',
              'source_reference': 'Inspection record reference', 'reviewer': 'Reviewer', **INPUT_LABELS}
    corrosion_form = {} if form.get('assessment_type') == 'documented_limits' else form
    fields = ''.join(f'<label>{label}<input name="{key}" value="{escape(corrosion_form.get(key, ""))}" {"required" if key != "depth_mm" else ""}></label>'
                     for key, label in labels.items())
    options = ['<option value="">Project only</option>']
    for comparison in workflow.comparisons():
        ident = comparison['id']
        selected = ' selected' if form.get('comparison_id') == ident else ''
        options.append(f'<option value="{escape(ident)}"{selected}>{escape(comparison["asset"])}</option>')
    observations = _ut_options(workflow, corrosion_form)
    saved = []
    for record in history(workflow):
        if record.get('assessment_type') == 'documented_limits':
            saved.append(_limit_trace(record))
            continue
        items = {label: record['inputs'][key] for key, label in INPUT_LABELS.items()}
        items.update({'Rule': record['rule'], 'Inspection record': record['source_reference'],
                      'Reviewer': record['reviewer'], 'Input revision': record['input_revision'],
                      'Linked comparison ID': record['comparison_id'] or 'Project only',
                      'Bulging factor': record['bulging_factor'], 'z': record['z'],
                      'Failure stress (psi)': record['failure_stress_psi'],
                      'Estimated failure pressure (psi)': record['estimated_failure_pressure_psi']})
        if record.get('ut_trace'):
            ut = record['ut_trace']
            items.update({'UT source': f"{ut['sheet']}!{ut['cell']} · {ut['date']}",
                          'UT wall (mm)': ut['measured_wall_mm'], 'Depth uncertainty (mm)': ut['uncertainty_mm'],
                          'Depth calculation': ut['basis'], 'UT observation': ut['observation_id']})
        trace = ''.join(f'<dt>{label}</dt><dd>{escape(str(value))}</dd>' for label, value in items.items())
        query = urlencode({'id': record['id']})
        saved.append(f'<article><h3>{escape(record["segment"])} · {escape(record["defect"])}</h3>'
                     f'<p>Draft defect screening pressure <strong>{float(record["defect_screening_pressure_psi"]):,.2f} psi</strong></p>'
                     f'<details><summary>Calculation trace</summary>'
                     '<p>z = axial length² ÷ (outside diameter × nominal wall). '
                     'Estimated failure pressure = 2 × nominal wall × failure stress ÷ outside diameter. '
                     'Screening pressure = estimated failure pressure ÷ safety factor.</p>'
                     f'<dl>{trace}</dl></details>'
                     f'<a href="/pipeline/results.csv?{query}">Download assessment CSV</a></article>')
    content = (f'<section><h1>Pipeline assessments</h1><h2>Modified B31G Level 1</h2>'
               f'<form action="/pipeline" method="post"><input type="hidden" name="revision" value="{workflow.revision()}">'
               f'<label>Linked UT comparison<select name="comparison_id">{"".join(options)}</select></label>{fields}{observations}'
               '<label><input type="checkbox" name="reviewed" value="yes" required> '
               'I reviewed the defect inputs and confirmed this method applies.</label>'
               '<button>Save pipeline assessment</button></form></section>'
               f'{_limit_form(workflow.revision(), options, form)}'
               f'<section id="saved-pipeline"><h2>Saved pipeline assessments</h2>{"".join(saved)}</section>')
    return shell('Pipeline assessments', content, notice=error, active='/pipeline')


def _ut_options(workflow, form):
    selected = form.get('comparison_id')
    options = ['<option value="">Enter depth manually</option>']
    for comparison in workflow.comparisons():
        if comparison['id'] != selected or comparison.get('stale'):
            continue
        for row in workflow._selection(*comparison['current_selection']):
            if row['raw_unit'] != 'mm' or row.get('review_status') == 'excluded' or not row.get('inspection_date'):
                continue
            oid = row['observation_id']
            wall = row.get('effective_value', row['raw_value'])
            label = f"{row['sheet_name']}!{row['cell']} · {row['inspection_date']} · {wall} mm"
            chosen = ' selected' if form.get('ut_observation_id') == oid else ''
            options.append(f'<option value="{escape(oid)}"{chosen}>{escape(label)}</option>')
    return (f'<label>Current UT record<select name="ut_observation_id">{"".join(options)}</select></label>'
            f'<label>Depth uncertainty (mm)<input name="ut_uncertainty_mm" value="{escape(form.get("ut_uncertainty_mm", ""))}"></label>'
            '<p>Open Pipeline Assessments for a UT comparison to list its records. A linked reading supplies depth from nominal wall, remaining wall and uncertainty. Enter reviewed axial length separately.</p>')


def _limit_form(revision, options, form):
    labels = {'segment': 'Pipeline segment', 'code_basis': 'Governing code, edition and service basis',
              'source_reference': 'Segment pressure-basis record', 'reviewer': 'Reviewer'}
    values = form if form.get('assessment_type') == 'documented_limits' else {}
    metadata = ''.join(f'<label>{label}<input name="{key}" value="{escape(values.get(key, ""))}" required></label>'
                       for key, label in labels.items())
    rows = []
    for key, label in LIMIT_LABELS.items():
        disposition = values.get(key + '_disposition')
        choices = '<option value="">Choose</option>' + ''.join(
            f'<option value="{value}"{" selected" if disposition == value else ""}>{name}</option>'
            for value, name in [('documented', 'Documented'), ('inapplicable', 'Inapplicable')])
        rows.append(f'<tr><th scope="row">{label}</th>'
                    f'<td><select aria-label="{label} disposition" name="{key}_disposition" required>{choices}</select></td>'
                    f'<td><input aria-label="{label} (psi)" name="{key}" type="number" step="any" min="0" '
                    f'value="{escape(values.get(key, ""))}"></td>'
                    f'<td><input aria-label="{label} evidence" name="{key}_reference" '
                    f'value="{escape(values.get(key + "_reference", ""))}" required></td></tr>')
    kinds = ''.join(f'<option{" selected" if values.get("limit_kind") == kind else ""}>{kind}</option>'
                    for kind in ('MAOP', 'MOP'))
    return (f'<section id="pipeline-limits"><h2>Documented MAOP/MOP limits</h2>'
            '<p>Enter pressure limits established for the same segment and pressure basis. The lowest documented applicable pressure governs this comparison.</p>'
            f'<form action="/pipeline#pipeline-limits" method="post"><input type="hidden" name="revision" value="{revision}">'
            '<input type="hidden" name="assessment_type" value="documented_limits">'
            f'<label>Pressure basis<select name="limit_kind">{kinds}</select></label>'
            f'<label>Linked UT comparison<select name="comparison_id">{"".join(options)}</select></label>{metadata}'
            '<div class="scroll"><table><thead><tr><th>Limit</th><th>Disposition</th><th>Pressure (psi)</th><th>Record or applicability basis</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            '<label><input type="checkbox" name="reviewed" value="yes" required> I reviewed the limits and applicability decisions for this segment.</label>'
            '<button>Save documented pressure comparison</button></form></section>')


def _limit_trace(record):
    labels = ', '.join(LIMIT_LABELS[key] for key in record['governing_limits'])
    rows = ''.join(f'<tr><th scope="row">{LIMIT_LABELS[key]}</th><td>{escape(item["psi"] or "Inapplicable")}</td>'
                   f'<td>{escape(item["reference"])}</td></tr>' for key, item in record['inputs'].items())
    query = urlencode({'id': record['id']})
    return (f'<article><h3>{escape(record["segment"])} · Documented {record["limit_kind"]}</h3>'
            f'<p><strong>{escape(record["governing_pressure_psi"])} psi</strong> · {labels}</p>'
            '<details><summary>Pressure limit trace</summary>'
            f'<p>{escape(record["code_basis"])} · {escape(record["source_reference"])} · {escape(record["reviewer"])}</p>'
            f'<table><thead><tr><th>Limit</th><th>Pressure (psi)</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table>'
            f'</details><a href="/pipeline/results.csv?{query}">Download pressure limits CSV</a></article>')
