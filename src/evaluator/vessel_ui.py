"""Project vessel assessment and pressure trace."""

from html import escape
from urllib.parse import urlencode

from evaluator.desk_ui import shell
from evaluator.engineering.vessel_assessment import history


def page(service, form=None, error=''):
    values = form or {}
    def field(key, label, kind='text', required=True):
        value = escape(values.get(key, ''))
        numeric = ' step="any"' if kind == 'number' else ''
        return (f'<label>{label}<input name="{key}" value="{value}" type="{kind}"'
                f'{numeric}{" required" if required else ""}></label>')

    fields = ''.join(field(*entry) for entry in (
        ('vessel', 'Vessel tag'), ('code_basis', 'Code, edition and service basis'),
        ('inspection_date', 'Next inspection date', 'date'), ('datum_ft', 'Pressure datum elevation (ft)', 'number'),
        ('liquid_level_ft', 'Maximum liquid elevation (ft)', 'number'),
        ('specific_gravity', 'Liquid specific gravity', 'number'),
        ('head_reference', 'Liquid level and datum evidence'), ('reviewer', 'Reviewer'),
    ))
    rows = []
    for index in range(1, 9):
        controls = ''.join(field(f'{key}_{index}', label, kind, False) for key, label, kind in (
            ('component', 'Component ID', 'text'), ('pressure_psi', 'Local next-inspection pressure (psi)', 'number'),
            ('elevation_ft', 'Component elevation (ft)', 'number'), ('reference', 'Dated calculation or rating evidence', 'text'),
        ))
        rows.append(f'<fieldset><legend>Component {index}</legend>{controls}</fieldset>')
    records = ''.join(_trace(record) for record in history(service.workflow))
    content = ('<section><h1>Vessel assessments</h1><h2>Next-inspection MAWP</h2>'
               '<p>Enter reviewed component pressures for the same date and service conditions. '
               'Use elevations measured from a common reference. Enter zero specific gravity for dry service.</p>'
               f'<form method="post" action="/vessels"><input type="hidden" name="revision" value="{service.workflow.revision()}">'
               f'{fields}{"".join(rows)}'
               '<label><input type="checkbox" name="reviewed" value="yes" required> '
               'I reviewed the pressure basis, liquid head and coverage of every potentially governing component.</label>'
               '<button>Save vessel assessment</button></form></section>'
               f'<section id="saved-vessels"><h2>Saved vessel assessments</h2>{records}</section>')
    return shell('Vessel assessments', content, notice=error, active='/vessels')


def _trace(record):
    rows = ''.join('<tr>' + ''.join(f'<td>{escape(str(component[key]))}</td>' for key in
                                  ('component', 'pressure_psi', 'elevation_ft', 'static_head_psi', 'datum_pressure_psi', 'reference')) +
                   '</tr>' for component in record['components'])
    query = urlencode({'id': record['id']})
    governing = escape(', '.join(record['governing_components']))
    return (f'<article><h3>{escape(record["vessel"])} · {escape(record["inspection_date"])}</h3>'
            f'<p>Draft MAWP at datum <strong>{float(record["mawp_psi"]):,.2f} psi</strong> · Governing component {governing}</p>'
            '<details><summary>Static head and component trace</summary>'
            f'<p>Datum {escape(record["datum_ft"])} ft · Liquid elevation {escape(record["liquid_level_ft"])} ft · '
            f'Specific gravity {escape(record["specific_gravity"])} · {escape(record["head_reference"])}</p>'
            f'<p>{escape(record["code_basis"])} · Reviewer {escape(record["reviewer"])}</p>'
            '<p>Datum pressure = local component pressure − differential static head. The lowest datum pressure governs.</p>'
            '<table><thead><tr><th>Component</th><th>Local pressure (psi)</th><th>Elevation (ft)</th>'
            '<th>Differential head (psi)</th><th>Datum pressure (psi)</th><th>Evidence</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></details>'
            f'<a href="/vessels/results.csv?{query}">Download vessel assessment CSV</a></article>')
