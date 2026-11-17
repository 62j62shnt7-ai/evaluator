"""Server-rendered tank assessment forms and saved calculation records."""
from evaluator.tanks import METHODS, STATUS, history
from evaluator.workflow_ui import E, field, hidden, person, shell


def page(service, notice=''):
    revision = service.workflow.revision()
    body = f'<p><a href="/">Back to UT Evaluator</a></p><h1>Tank assessments</h1><p>{STATUS}</p>'
    for method, (label, fields) in METHODS.items():
        body += f'<section><h2>{E(label)}</h2><form method="post" action="/tanks">'
        body += hidden('revision', revision) + hidden('method', method)
        body += field('tank', 'Tank ID') + field('component', 'Course / area / bottom zone')
        if method == 'api653_shell':
            body += ('<label>Evaluation scope<select name="scope" required>'
                     '<option value="">Choose…</option><option value="whole">Entire course</option>'
                     '<option value="local">Local area</option></select></label>'
                     '<p>Use the same datum for both heights. For local assessment, enter t1 from the inspector-reviewed profile (at least five equally spaced readings over L) and the least thickness t2 excluding pits. This method excludes reconstructed tanks.</p>')
        body += ''.join(field(key, name, kind='number', required=key != 't2_mm') for key, name in fields.items())
        body += person()
        body += ('<label class="check"><input name="applicability" type="checkbox" value="yes" required>'
                 'I checked the method, scope, edition and input sources for this component.</label>'
                 '<button>Calculate and save draft</button></form></section>')
    body += '<section><h2>Saved tank calculations</h2>'
    for record in history(service.workflow):
        label = METHODS[record['method']][0]
        body += f'<details><summary>{E(record["tank"])} / {E(record["component"])} · {E(label)}</summary>'
        body += f'<p>{STATUS} · {E(record["reference"])} · Input revision {record["input_revision"]}</p>'
        body += f'<p>{E(record["note"])}</p><dl>'
        labels = {
            'product_mm': 'Product thickness (mm)', 'hydrotest_mm': 'Hydrotest thickness (mm)',
            'governing_candidate_mm': 'Governing thickness candidate (mm)',
            'allowable_stress_MPa': 'Allowable stress (MPa)', 'minimum_mm': 'Minimum thickness (mm)',
            'profile_length_mm': 'Required profile length L (mm)',
            'local_average_margin_mm': 'Margin at local average t1 (mm)',
            'local_least_margin_mm': 'Margin at local least thickness t2 (mm)',
            'net_mm': 'Net thickness after allowance (mm)', 'liquid_height_candidate_m': 'Liquid height candidate (m)',
            'projected_remaining_mm': 'Projected remaining bottom thickness (mm)',
            'margin_to_reviewed_minimum_mm': 'Margin to reviewed bottom minimum (mm)',
        }
        for key, value in record['outputs'].items():
            body += f'<dt>{E(labels[key])}</dt><dd>{E(value if value is not None else "Withheld: net thickness below minimum")}</dd>'
        body += f'</dl><p>{E(record["reviewer"])} · {E(record["reason"])}</p></details>'
    return shell('Tank assessments', body + '</section>', notice)
