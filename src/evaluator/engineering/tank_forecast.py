"""Next-inspection shell-course assessment using the existing API 653 engine."""

from csv import DictReader
from datetime import date
from decimal import Decimal
from io import StringIO

from evaluator.engineering.batch_rules import _number
from evaluator.tanks import calculate, screen_pits


COURSE_COLUMNS = ('course', 'bottom_m', 'current_wall_mm', 'rate_mm_year',
                  'yield_MPa', 'tensile_MPa', 'joint_efficiency', 'reference')


LOCAL_COLUMNS = ('course', 'area', 'datum_m', 'average_mm', 'least_mm', 'rate_mm_year', 'reference')
PIT_COLUMNS = ('course', 'line', 'start_mm', 'end_mm', 'remaining_mm', 'rate_mm_year', 'reference')


def _observations(form, key, columns):
    raw = form.get(key, '').strip()
    if not raw:
        return []
    reader = DictReader(StringIO(raw))
    if tuple(reader.fieldnames or ()) != columns:
        raise ValueError(f'Use the displayed {key} column headers.')
    rows = list(reader)
    if not rows or any(None in row or any(not value or not value.strip() for value in row.values()) for row in rows):
        raise ValueError(f'Complete every {key} entry, including its evidence reference.')
    return rows


def _local_checks(rows, courses, years, design):
    limits = []
    for row in rows:
        parent = courses.get(row['course'])
        if parent is None:
            raise ValueError('Local thinning references an unknown shell course.')
        datum = _number(row['datum_m'], 'Local evaluation elevation', nonnegative=True)
        if not Decimal(parent['bottom_m']) <= datum < min(parent['top_m'], design):
            raise ValueError('Local evaluation elevation must lie within the entered course and below design fill.')
        loss = _number(row['rate_mm_year'], 'Local corrosion rate', nonnegative=True) * years
        local_design = design - datum
        check = calculate('api653_shell', dict(parent['api653']['inputs'],
                          H_m=local_design, design_H_m=local_design, measured_mm=row['average_mm'],
                          t2_mm=row['least_mm'], CA_mm=loss), 'local')
        height = check['outputs']['liquid_height_candidate_m']
        record = dict(row, projected_average_mm=check['outputs']['net_mm'],
                      projected_least_mm=str(Decimal(row['least_mm']) - loss),
                      max_fill_m=None if height is None else str(datum + Decimal(height)), api653=check)
        parent.setdefault('local_checks', []).append(record)
        limits.append((row['course'], record['max_fill_m']))
    return limits


def _pit_checks(rows, courses, years, fill):
    groups = {}
    for row in rows:
        if row['course'] not in courses:
            raise ValueError('Pit observations reference an unknown shell course.')
        loss = _number(row['rate_mm_year'], 'Pit corrosion rate', nonnegative=True) * years
        remaining = _number(row['remaining_mm'], 'Pit remaining wall', nonnegative=True) - loss
        groups.setdefault(row['course'], []).append(dict(row, projected_remaining_mm=str(remaining)))
    failed = []
    for course, group in groups.items():
        parent = courses[course]
        if fill is None:
            parent['pit_check'] = dict(observations=group, pit_screen='Fill basis unavailable')
            continue
        basis = parent['api653']
        v = basis['inputs']
        coefficient = Decimal('4.9') * Decimal(v['D_m']) * Decimal(v['G']) / (
            Decimal(basis['outputs']['allowable_stress_MPa']) * Decimal(v['E']))
        minimum = max(Decimal('2.5'), coefficient * (fill - Decimal(parent['bottom_m']) - Decimal('.3')))
        raw = '\n'.join(','.join((row['line'], row['start_mm'], row['end_mm'],
                                  str(max(Decimal(0), Decimal(row['projected_remaining_mm']))))) for row in group)
        result, _ = screen_pits(raw, minimum)
        parent['pit_check'] = dict({key: str(value) for key, value in result.items()},
                                   evaluated_fill_m=str(fill), shell_minimum_mm=str(minimum),
                                   observations=group, reference='API 653 4.3.2.2')
        if result['pit_screen'] != 'Meets both screening limits':
            failed.append(course)
    return failed


def calculate_forecast(form):
    current = date.fromisoformat(form['current_date'])
    target = date.fromisoformat(form['inspection_date'])
    days = (target - current).days
    if days <= 0:
        raise ValueError('Next inspection must follow the measurement date.')
    years = Decimal(days) / Decimal('365.2425')
    design = _number(form['design_height_m'], 'Original design fill height', positive=True)
    other = form.get('other_height_m', '').strip()
    if other and not form.get('other_height_reference', '').strip():
        raise ValueError('Enter the reference for the reviewed non-shell height limit.')
    other = _number(other, 'Non-shell height limit', positive=True) if other else None
    inputs = DictReader(StringIO(form['courses'].strip()))
    if tuple(inputs.fieldnames or ()) != COURSE_COLUMNS:
        raise ValueError('Use the displayed shell course column headers.')
    courses = []
    for row in inputs:
        if None in row or any(value is None or not value.strip() for value in row.values()):
            raise ValueError('Each course needs all eight entries, including its evidence reference.')
        course = _number(row['course'], 'Course number', positive=True)
        if course != len(courses) + 1:
            raise ValueError('Enter consecutive shell courses from bottom to top, starting at 1.')
        bottom = _number(row['bottom_m'], 'Course bottom elevation', nonnegative=True)
        if (not courses and bottom != 0) or (courses and bottom <= Decimal(courses[-1]['bottom_m'])):
            raise ValueError('The first course starts at zero. Higher courses need increasing elevations.')
        wall = _number(row['current_wall_mm'], 'Controlling measured wall', positive=True)
        rate = _number(row['rate_mm_year'], 'Adopted corrosion rate', nonnegative=True)
        projected = wall - rate * years
        local_design = design - bottom
        if local_design <= Decimal('.3'):
            raise ValueError(f'Course {course} is outside the supported one-foot liquid-height range.')
        check = calculate('api653_shell', dict(
            D_m=form['diameter_m'], H_m=str(local_design), G=form['specific_gravity'],
            course=str(course), Y_MPa=row['yield_MPa'], T_MPa=row['tensile_MPa'],
            E=row['joint_efficiency'], measured_mm=str(wall), CA_mm=str(rate * years),
            design_H_m=str(local_design),
        ), 'whole')
        output = check['outputs']
        local = output['liquid_height_candidate_m']
        courses.append(dict(row, bottom_m=str(bottom), projected_wall_mm=str(projected),
                            max_fill_m=None if local is None else str(bottom + Decimal(local)),
                            api653=check))
    if not courses:
        raise ValueError('Enter the shell course measurements.')
    for index, course in enumerate(courses):
        course['top_m'] = Decimal(courses[index + 1]['bottom_m']) if index + 1 < len(courses) else design
    by_course = {course['course']: course for course in courses}
    local = _observations(form, 'local_areas', LOCAL_COLUMNS)
    pits = _observations(form, 'pit_rows', PIT_COLUMNS)
    if form.get('local_status') not in (None, '', 'none', 'mapped') or form.get('pit_status') not in (None, '', 'none', 'mapped'):
        raise ValueError('Select the condition survey dispositions.')
    for key, observations in [('local_status', local), ('pit_status', pits)]:
        if form.get(key) and not form.get(key.replace('_status', '_survey_reference'), '').strip():
            raise ValueError('Enter the local thinning and pitting survey evidence.')
        if bool(observations) != (form.get(key) == 'mapped'):
            raise ValueError('Each mapped condition needs observations and a confirmed survey disposition.')
    limits = [(row['course'], row['max_fill_m']) for row in courses]
    local_limits = _local_checks(local, by_course, years, design)
    limits.extend(local_limits)
    shell = min(Decimal(height) for _, height in limits) if all(height is not None for _, height in limits) else None
    candidate = min(shell, other) if shell is not None and other is not None else shell
    failed_pits = _pit_checks(pits, by_course, years, candidate)
    for course in courses:
        course.pop('top_m')
    return dict(method='api653_forecast', status='DRAFT / NOT VALIDATED',
                reference='API 653 5th edition through July 2025, 4.3 whole-course assessment',
                inputs={key: form.get(key, '') for key in ('current_date', 'inspection_date', 'diameter_m',
                        'specific_gravity', 'design_height_m', 'other_height_m', 'other_height_reference', 'local_status', 'pit_status', 'local_survey_reference', 'pit_survey_reference')},
                outputs=dict(interval_years=str(years), shell_fill_height_m=None if shell is None else str(shell),
                             allowable_fill_height_m=None if shell is None or other is None or failed_pits else str(candidate),
                             governing_shell_courses=list(dict.fromkeys(course for course, height in limits
                                                      if shell is not None and Decimal(height) == shell)),
                             governing_local_areas=[row['area'] for course in courses
                                                    for row in course.get('local_checks', [])
                                                    if shell is not None and Decimal(row['max_fill_m']) == shell],
                             pit_exclusion_failed_courses=failed_pits,
                             governing_limit='pit exclusion requires review' if failed_pits else None if shell is None or other is None else
                             'non-shell limit' if other < shell else 'shell and non-shell limits' if other == shell else 'shell limit'),
                courses=courses, note='Course elevations and fill heights are measured from the tank bottom.')
