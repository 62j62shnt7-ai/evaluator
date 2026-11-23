"""Tank shell projection form and saved course traces."""

from html import escape
from urllib.parse import urlencode

from evaluator.desk_ui import shell
from evaluator.engineering.tank_forecast import COURSE_COLUMNS, LOCAL_COLUMNS, PIT_COLUMNS
from evaluator.tanks import history


def page(service, form=None, error=''):
    form = form or {}
    fields = {
        'tank': 'Tank tag', 'reviewer': 'Reviewer', 'reason': 'API 650 design and API 653 applicability evidence',
        'current_date': 'UT measurement date', 'inspection_date': 'Next inspection date',
        'diameter_m': 'Tank diameter (m)', 'specific_gravity': 'Maximum product specific gravity',
        'design_height_m': 'Original design fill height (m)', 'other_height_m': 'Reviewed non-shell fill limit (m)',
        'other_height_reference': 'Non-shell limit evidence',
    }
    controls = ''.join(f'<label>{label}<input name="{key}" value="{escape(form.get(key, ""))}" '
                       f'type="{"date" if key.endswith("_date") else "text"}" '
                       f'{"" if key.startswith("other_") else "required"}></label>' for key, label in fields.items())
    header = ','.join(COURSE_COLUMNS)
    conditions = ''.join(_survey(form, key, label, columns) for key, label, columns in (
        ('local', 'Local thinning', LOCAL_COLUMNS), ('pit', 'Scattered shell pitting', PIT_COLUMNS),
    ))
    records = ''.join(_trace(row) for row in history(service.workflow) if row['method'] == 'api653_forecast')
    return shell('Next-inspection tank assessment',
                 '<section><h1>Next-inspection tank assessment</h1>'
                 '<p>Enter the reviewed controlling wall for each whole shell course. '
                 'Use the original design fill height and a common tank-bottom datum.</p>'
                 f'<form method="post" action="/tanks/forecast"><input type="hidden" name="revision" value="{service.workflow.revision()}">'
                 '<input type="hidden" name="method" value="api653_forecast"><input type="hidden" name="component" value="Shell courses">'
                 f'{controls}<label>Shell courses (CSV)<textarea name="courses" rows="8" required>'
                 f'{escape(form.get("courses", header + chr(10)))}</textarea></label>'
                 '<p>Paste one row per course below the headers, starting at the bottom course.</p>'
                 f'{conditions}'
                 '<p>Mapped pit lines must cover the assessed areas. The forecast projects depth using each entered rate and uses the reviewed vertical extents as entered.</p>'
                 '<label><input type="checkbox" name="applicability" value="yes" required> '
                 'I reviewed whole-course applicability, controlling readings, rates and shell coverage.</label>'
                 '<button>Save tank forecast</button></form></section>'
                 f'<section id="saved-tank-forecasts"><h2>Saved tank forecasts</h2>{records}</section>',
                 error, active='/tanks')


def _trace(record):
    outputs = record['outputs']
    def height(key):
        return f'{float(outputs[key]):.3f} m' if outputs[key] is not None else 'Withheld'
    courses = ', '.join(outputs['governing_shell_courses']) or 'Unresolved'
    rows = ''.join('<tr>' + ''.join(f'<td>{escape(str(course[key]) if course[key] is not None else "Withheld")}</td>'
                                  for key in ('course', 'bottom_m', 'current_wall_mm', 'rate_mm_year',
                                              'projected_wall_mm', 'max_fill_m', 'reference')) + '</tr>'
                   for course in record['courses'])
    local_areas = ', '.join(outputs.get('governing_local_areas', []))
    failed = ', '.join(outputs.get('pit_exclusion_failed_courses', []))
    evidence = ''
    if local_areas:
        evidence += f'<p>Governing local area {escape(local_areas)}</p>'
    if failed:
        evidence += f'<p>Pit exclusion failed on course {escape(failed)}. Allowable fill height is withheld pending review.</p>'
    details = ''
    for course in record['courses']:
        for check in course.get('local_checks', []):
            fields = {'Course': course['course'], 'Local evaluation elevation (m)': check['datum_m'],
                      'Projected average (mm)': check['projected_average_mm'],
                      'Projected least wall (mm)': check['projected_least_mm'],
                      'Local fill limit (m)': check['max_fill_m'], 'Evidence': check['reference']}
            details += _details(check['area'], fields)
        pit = course.get('pit_check')
        if pit:
            fields = {'Screen': pit['pit_screen'], 'Evaluated fill (m)': pit.get('evaluated_fill_m'),
                      'Least projected wall (mm)': pit.get('pit_min_remaining_mm'),
                      'Required remaining wall (mm)': pit.get('pit_required_remaining_mm'),
                      'Maximum extent in 200 mm (mm)': pit.get('max_pit_extent_mm')}
            details += _details(f"Course {course['course']} pits", fields)
            for item in pit['observations']:
                details += _details(item['line'], {'Start (mm)': item['start_mm'], 'End (mm)': item['end_mm'],
                                    'Projected wall (mm)': item['projected_remaining_mm'], 'Evidence': item['reference']})
    query = urlencode({'id': record['id']})
    return (f'<article><h3>{escape(record["tank"])} · {escape(record["inputs"]["inspection_date"])}</h3>'
            f'<p>Draft allowable fill height <strong>{height("allowable_fill_height_m")}</strong> · '
            f'Shell limit {height("shell_fill_height_m")} · Governing shell course {escape(courses)}</p>'
            f'{evidence}<details><summary>Projected wall and fill height trace</summary>'
            f'<p>{escape(record["reference"])} · {escape(record["reason"])}</p>'
            f'<p>Interval {float(outputs["interval_years"]):.4f} years. Projected wall = measured wall − adopted rate × interval.</p>'
            '<table><thead><tr><th>Course</th><th>Bottom (m)</th><th>Current wall (mm)</th><th>Rate (mm/year)</th>'
            '<th>Projected wall (mm)</th><th>Fill limit (m)</th><th>Evidence</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>{details}</details>'
            f'<a href="/tanks/forecast.csv?{query}">Download tank forecast CSV</a></article>')



def _details(title, fields):
    rows = ''.join(f'<dt>{label}</dt><dd>{escape(str(value)) if value is not None else "Withheld"}</dd>'
                   for label, value in fields.items())
    return f'<h4>{escape(title)}</h4><dl>{rows}</dl>'


def _survey(form, key, label, columns):
    disposition = form.get(key + '_status', '')
    choices = ''.join(f'<option value="{value}"{" selected" if disposition == value else ""}>{text}</option>'
                      for value, text in [('', 'Choose'), ('none', 'Reviewed survey found none'),
                                          ('mapped', 'Mapped observations provided')])
    field = 'local_areas' if key == 'local' else 'pit_rows'
    header = ','.join(columns)
    return (f'<fieldset><legend>{label}</legend><label>Survey disposition<select name="{key}_status" required>'
            f'{choices}</select></label><label>Survey evidence<input name="{key}_survey_reference" required '
            f'value="{escape(form.get(key + "_survey_reference", ""))}"></label>'
            f'<label>Observations (CSV)<textarea name="{field}" rows="4" '
            f'placeholder="{header}">{escape(form.get(field, ""))}</textarea></label>'
            f'<p>CSV headers <code>{header}</code></p></fieldset>')
