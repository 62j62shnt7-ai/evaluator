"""Server-rendered tank assessment forms and saved calculation records."""
from evaluator.tanks import METHODS, STATUS, history
from evaluator.tank_ut import MAPPINGS
from evaluator.desk_ui import shell
from evaluator.workflow_ui import E, field, hidden, person


def page(service, notice='', *, active_method=None):
    revision = service.workflow.revision()
    records = history(service.workflow)
    body = ('<div class="document-heading"><div><h1>Tank assessments</h1>'
            '<p>Choose a design or in-service check. API 653 shell and bottom checks can use readings from an imported workbook.</p></div>'
            '<a href="#saved-tank-calculations">Saved calculations</a></div>'
            '<div class="tank-methods">')
    for method, (label, fields) in METHODS.items():
        opened = ' open' if method == active_method else ''
        body += (f'<details class="card tank-method"{opened}><summary>{E(label)}</summary>'
                 '<form class="tank-form" method="post" action="/tanks">')
        body += hidden('revision', revision) + hidden('method', method)
        body += field('tank', 'Tank ID') + field('component', 'Course / area / bottom zone')
        if method == 'api650':
            body += ('<label>Course position<select name="course_position"><option value="">Choose if applicable</option>'
                     '<option value="lowest">Lowest course</option><option value="upper">Upper course</option></select></label>'
                     '<p>The app looks up the nominal plate minimum from diameter. Course position matters between 3.2 and 15 m.</p>')
        if method == 'api653_shell':
            body += ('<label>Evaluation scope<select name="scope" required>'
                     '<option value="">Choose…</option><option value="whole">Entire course</option>'
                     '<option value="local">Local area</option></select></label>'
                     '<p>Use the same datum for both heights. For local assessment, enter t1 from the inspector-reviewed profile (at least five equally spaced readings over L) and the least thickness t2 excluding pits. This method excludes reconstructed tanks.</p>')
        mapped = set(MAPPINGS.get(method, ()))
        body += ''.join(field(key, name, kind='number', required=key not in mapped and key not in {'nominal_min_mm', 'governing_min_mm', 'table_min_mm', 't2_mm', 'other_load_H_m'}) for key, name in fields.items())
        if mapped:
            choices = ''.join(f'<option value="{E(source["source_id"])}">{E(source["file_name"])} · {E(source["source_id"][:10])}</option>'
                              for source in service.sources())
            body += ('<details><summary>Use cells from an imported UT workbook</summary>'
                     '<p>Choose a workbook already imported through the workbook library. Map cells by address, separated by commas. '
                     'Selected cells supply the thickness inputs in place of manually entered values.</p>'
                     f'<label>Workbook<select name="ut_source"><option value="">Manual thickness inputs</option>{choices}</select></label>')
            body += field('ut_sheet', 'Exact worksheet name', required=False)
            body += field('ut_date', 'Inspection date', kind='date', required=False)
            if method == 'api653_shell':
                labels = ('Course minimum readings or local t1 profile readings', 'Local t2 area readings excluding pits')
                body += ('<label class="check"><input type="checkbox" name="ut_profile_reviewed" value="yes">'
                         'For local assessment, I verified the selected t1 cells cover the controlling equally spaced profile over L and t2 covers the surveyed area.</label>')
            else:
                labels = ('Bottom-side minimum reading cells', 'Product-side minimum reading cells')
            body += field('ut_primary', labels[0], required=False) + field('ut_secondary', labels[1], required=False)
            body += '<label class="check"><input name="ut_mm" type="checkbox" value="yes">Mapped readings are in millimetres.</label></details>'
        if method == 'api653_bottom':
            body += ('<label>API 653 Table 4.4a bottom design<select name="bottom_design">'
                     '<option value="">Enter reviewed minimum manually</option>'
                     '<option value="no_leak_containment">No leak detection and containment · 2.54 mm</option>'
                     '<option value="leak_detection_containment">Leak detection and containment · 1.27 mm</option>'
                     '<option value="qualified_reinforced_lining">API 652 reinforced lining over 1.27 mm · 1.27 mm</option></select></label>')
        if method == 'api653_pits':
            body += ('<label>Pit observations (one per line: vertical line ID, start mm, end mm, remaining thickness mm)'
                     '<textarea name="pit_rows" rows="5" required></textarea></label>'
                     '<label class="check"><input name="scattered" type="checkbox" value="yes" required>'
                     'These are widely scattered shell pits and all relevant vertical lines were surveyed.</label>')
        if method == 'api653_critical':
            body += '<p>Use unaveraged minima in the zone extending 75 mm radially inward from the shell inside edge.</p>'
        if method == 'api653_annular':
            body += ('<label>Annular lookup method<select name="annular_mode">'
                     '<option value="local_pdf">Generate from verified local PDF</option>'
                     '<option value="manual">Enter reviewed table value</option></select></label>'
                     '<p>For automatic lookup, enter the reviewed first-course thickness and stress. Gravity selects the SI table. The lookup uses the applicable table band without interpolation. '
                     'Use the as-constructed thickness for Table 4.5a or confirm the applicable product or hydrotest basis for Table 5.1a.</p>')
            body += field('shell_course_mm', 'Reviewed first-course thickness (mm)', kind='number', required=False)
            body += field('shell_stress_MPa', 'Reviewed first-course stress (MPa)', kind='number', required=False)
            body += ('<label>Manual lookup table<select name="annular_table">'
                     '<option value="">Choose…</option><option>API 653 Table 4.5a</option>'
                     '<option>API 650 Table 5.1a</option></select></label>'
                     '<label class="check"><input name="nonseismic" type="checkbox" value="yes" required>'
                     'This ring is not thickened for seismic loading. I checked foundation support and the shell stress used in the lookup.</label>')
            body += field('table_evidence', 'Lookup evidence, including edition, row and shell stress basis')
        body += person()
        body += ('<label class="check"><input name="applicability" type="checkbox" value="yes" required>'
                 'I checked the method, scope, edition and input sources for this component.</label>'
                 '<button class="primary">Calculate and save draft</button></form></details>')
    body += '</div><section id="saved-tank-calculations"><h2>Saved tank calculations</h2>'
    if not records:
        body += '<p>Saved assessments will appear here after you run a check.</p>'
    for index, record in enumerate(records):
        label = METHODS[record['method']][0]
        opened = ' open' if index == 0 else ''
        body += f'<details{opened}><summary>{E(record["tank"])} / {E(record["component"])} · {E(label)}</summary>'
        body += f'<p>{STATUS} · {E(record["reference"])} · Input revision {record["input_revision"]}</p>'
        body += f'<p>{E(record["note"])}</p><dl>'
        labels = {
            'liquid_height_candidate_m': 'Liquid-loading height candidate (m)',
            'governing_height_candidate_m': 'Height candidate including reviewed other loads (m)',
            'code_nominal_min_mm': 'Nominal plate minimum from API 650 (mm)',
            'product_mm': 'Product thickness (mm)', 'hydrotest_mm': 'Hydrotest thickness (mm)',
            'governing_candidate_mm': 'Governing thickness candidate (mm)',
            'allowable_stress_MPa': 'Allowable stress (MPa)', 'minimum_mm': 'Minimum thickness (mm)',
            'profile_length_mm': 'Required profile length L (mm)',
            'local_average_margin_mm': 'Margin at local average t1 (mm)',
            'local_least_margin_mm': 'Margin at local least thickness t2 (mm)',
            'net_mm': 'Net thickness after allowance (mm)',
            'pit_min_remaining_mm': 'Least thickness below a pit (mm)',
            'pit_required_remaining_mm': 'Pit minimum limit (mm)',
            'max_pit_extent_mm': 'Largest sum in a 200 mm vertical window (mm)',
            'pit_screen': 'Pit screening result',
            'annular_current_required_mm': 'Current annular minimum including allowance (mm)',
            'annular_current_margin_mm': 'Current annular thickness margin (mm)',
            'governing_bottom_min_mm': 'Governing bottom minimum (mm)',
            'toe_thickness_margin_mm': 'Outer weld toe thickness margin (mm)',
            'toe_projection_margin_mm': 'Outer weld toe projection margin (mm)',
            'projected_remaining_mm': 'Projected remaining bottom thickness (mm)',
            'margin_to_reviewed_minimum_mm': 'Margin to reviewed bottom minimum (mm)',
        }
        for key, value in record['outputs'].items():
            if value is None:
                value = 'Withheld: net thickness below minimum'
                if key == 'governing_height_candidate_m' and record['outputs']['liquid_height_candidate_m'] is not None:
                    value = 'Withheld: reviewed height limit for other loads was not supplied'
            body += f'<dt>{E(labels[key])}</dt><dd>{E(value)}</dd>'
        reference_values = record.get('reference_values', {})
        for reference in reference_values.values():
            body += f'<dt>Reference lookup</dt><dd>{E(reference["value"])} mm · {E(reference["reference"])}</dd>'
        provenance = record.get('ut_provenance')
        if provenance:
            body += '</dl><h3>UT source</h3><dl>'
            body += f'<dt>Worksheet and inspection date</dt><dd>{E(provenance["sheet"])} · {E(provenance["inspection_date"])}</dd>'
            body += f'<dt>Workbook SHA-256</dt><dd>{E(provenance["source_sha256"])}</dd>'
            for group in provenance['groups'].values():
                readings = ', '.join(f'{cell}: {value} mm' for cell, value in group['cells'].items())
                body += f'<dt>{E(group["aggregation"].title())} of mapped cells</dt><dd>{E(readings)}</dd>'
        body += f'</dl><p>{E(record["reviewer"])} · {E(record["reason"])}</p></details>'
    return shell('Tank assessments', body + '</section><script defer src="/assets/code-sample.js"></script>',
                 notice, active='/tanks')
