"""Tabular snapshots of saved inspection calculations."""
import json
from math import isfinite


def result_rows(result):
    rows = []
    rows.append(['Location','Previous date','Current date','Previous UT mm','Current UT mm','Material','Pd psi','OD in','Nominal mm','Structural mm','S psi','Pressure thickness mm','Required thickness mm','Calculated CR mm/year','CR used mm/year','CR basis','Remaining life years','Interval years','t in MAWP mm','Next-inspection component pressure psi','Result','Next inspection','Missing inputs','Fitting pressure checked psi','Fitting minimum wall mm','Fitting projected credited wall mm','Fitting projection interval years','Fitting current exceeds minimum','Fitting projected exceeds minimum','Fitting assessment reference','Bend measured position','Bend location pressure candidate psi','Bend calculation rule','Bend design basis record','Other pressure candidate psi','Other pressure assessment basis','Bend tag','Governing bend pressure psi','Governing bend positions','Bend coverage issues','Qualified next-interval fitting pressure psi','Qualification minimum wall mm','Qualification temperature F','Qualification reference','Qualification pressure-wall schedule','Qualified fitting tag','Qualification UT location','Component geometry','Reviewed workbook input references','Review note','Documented Sleeve-T assembly assessment',
                     'Fitting screening basis', 'Screening pressure wall mm', 'Screening required wall mm',
                     'Screening CR mm/year', 'Screening remaining life years', 'Screening interval years',
                     'Screening next inspection', 'Screening draft current pressure psi',
                     'Screening draft forecast pressure psi'])
    screening_fields = (
        'pressure_wall_mm', 'required_wall_mm', 'rate_mm_year', 'remaining_life_years',
        'interval_years', 'due_date', 'pressure_psi', 'forecast_pressure_psi',
    )
    for row in result['rows']:
        if not row.get('current_id'):continue
        i=row.get('input_trace',{}).get('inputs',{});r=row.get('row7') or {}
        if not r and row.get('input_trace', {}).get('basis') in {'recalculate', 'documented_fitting_pressure'}:
            from evaluator.engineering.batch_rules import pressure_psi
            fields = (row.get('profile') or {}).get('fields', {})
            raw = lambda key: fields.get(key, {}).get('value')
            trace = row['input_trace']
            pressure = row.get('forecast_mawp_MPa')
            i = dict(material=raw('material'), pd_psi=raw('P_psi'), od_in=raw('D_outside_in'),
                     nominal_mm=raw('nominal_thickness_mm'),
                     structural_mm=trace.get('overrides', {}).get('structural_minimum_mm'))
            r = dict(s_psi=raw('S_allow_psi'), pressure_mm=row.get('pressure_thickness_mm'),
                     required_mm=row.get('required_thickness_mm'), calculated_cr=row.get('apparent_rate_mm_year'),
                     cr_used=row.get('adopted_rate_mm_year'), cr_basis=trace.get('rate_basis'),
                     remaining_life=row.get('remaining_life_years'), interval=row.get('inspection_interval_years'),
                     mawp_thickness_mm=row.get('outputs', {}).get('trace', {}).get('forecast_mawp_MPa', {}).get('net_thickness_mm'),
                     mawp_psi=pressure_psi(pressure),
                     result=row.get('evaluation_status'), next_inspection=row.get('due_date'))
        forecast_trace = row.get('outputs', {}).get('trace', {}).get('forecast_mawp_MPa', {})
        horizon = forecast_trace.get('horizon_basis')
        other_pressure = [None, None]
        if horizon and horizon not in {'next_inspection_interval', 'manual_interval_override'}:
            other_pressure = [r.get('mawp_psi'), horizon]
            r = dict(r, mawp_psi=None, mawp_thickness_mm=None)
        if 'forecast_mawp_MPa' in row and row['forecast_mawp_MPa'] is None:
            r = dict(r, mawp_psi=None, mawp_thickness_mm=None)
        values=[r.get(k) for k in ('s_psi','pressure_mm','required_mm','calculated_cr','cr_used','cr_basis','remaining_life','interval','mawp_thickness_mm','mawp_psi','result','next_inspection')]
        if values[10]:values[10]='DRAFT / NOT VALIDATED · '+str(values[10])
        fitting = row.get('fitting_check', {})
        fitting_columns = [fitting.get(key) for key in (
            'pressure_psi','minimum_mm','credited_wall_mm','projection_years',
            'current_meets_minimum','projected_meets_minimum','reference',
            'bend_position','bend_pressure_psi','bend_rule','bend_design_reference',
        )]
        bend = row.get('bend_summary', {})
        bend_columns = [bend.get('tag'), bend.get('pressure_psi'),
                        ' | '.join(item['position'] for item in bend.get('governing', [])),
                        ' | '.join(bend.get('issues', []))]
        screen = row.get('fitting_progress', {}).get('straight_pipe_screen') or {}
        screening = ([('ASME B31.3 straight-pipe screening; E assumed 1' if screen.get('assumed_quality_factor')
                       else 'ASME B31.3 straight-pipe screening')] + [screen.get(key) for key in screening_fields]
                     if screen.get('assessment') else [None] * (len(screening_fields) + 1))
        rows.append([row['location'],row.get('previous_inspection_date'),row.get('inspection_date'),row.get('previous_thickness_mm'),row.get('current_thickness_mm'),i.get('material'),i.get('pd_psi'),i.get('od_in'),i.get('nominal_mm'),i.get('structural_mm')]+values+['; '.join(dict.fromkeys(row['issues'] + row.get('outputs', {}).get('issues', {}).get('forecast_mawp_MPa', [])))]+fitting_columns+other_pressure+bend_columns+[fitting.get(key) for key in
            ('qualified_pressure_psi','qualification_required_wall_mm','qualification_temperature_F',
             'qualification_reference','qualification_points','qualification_tag','qualification_ut_location')]+[row.get('routing', {}).get('geometry') or row.get('detected_geometry'), row.get('input_trace', {}).get('overrides', {}).get('source_config_reference'), row.get('input_trace', {}).get('overrides', {}).get('review_note'), json.dumps(row['sleeve_assessment']) if row.get('sleeve_assessment') else None]+screening)
    return rows

REVIEW_FIRST = (
    'Location', 'Component geometry', 'Code basis', 'Forecast MAWP (psi)',
    'Current pressure (psi)', 'Remaining life (years)', 'Next inspection',
    'Inspection interval (years)', 'Result', 'Missing inputs', 'Previous date',
    'Current date', 'Previous UT mm', 'Current UT mm', 'Required thickness mm',
    'Pressure thickness mm', 'Calculated CR mm/year', 'CR used mm/year', 'CR basis',
)


def review_rows(result):
    from evaluator.engineering.batch_rules import pressure_psi

    headers, *values = result_rows(result)
    records = []
    saved = (row for row in result['rows'] if row.get('current_id'))
    for row, values_for_row in zip(saved, values, strict=True):
        record = dict(zip(headers, values_for_row, strict=True))
        profile = row.get('profile') or {}
        progress = row.get('fitting_progress') or {}
        screen = progress.get('straight_pipe_screen') or {}
        record['Code basis'] = ' '.join(filter(None, (
            profile.get('code_family'), str(profile.get('code_edition') or ''),
        )))
        record['Forecast MAWP (psi)'] = next((value for value in (
            record['Screening draft forecast pressure psi'],
            progress.get('bend_forecast_pressure_psi'),
            progress.get('qualified_forecast_pressure_psi'),
            record.pop('Next-inspection component pressure psi'),
        ) if value is not None), None)
        trace = row.get('outputs', {}).get('trace', {}).get('mawp_MPa', {})
        record['Current pressure (psi)'] = next((value for value in (
            record['Screening draft current pressure psi'], progress.get('bend_pressure_psi'),
            progress.get('qualified_current_pressure_psi'),
            pressure_psi(row.get('mawp_MPa')) if trace.get('horizon_basis') == 'current_measurement' else None,
        ) if value is not None), None)
        record['Inspection interval (years)'] = record.pop('Interval years')
        record['Remaining life (years)'] = record.pop('Remaining life years')
        record['Result'] = record['Result'] or row.get('evaluation_status') or 'No saved calculation'
        issues = record['Missing inputs'].split('; ') if record['Missing inputs'] else []
        issues.extend(progress.get('screening_missing') or [])
        record['Missing inputs'] = '; '.join(dict.fromkeys(issues))
        if screen.get('assessment'):
            record['Result'] = 'Draft straight-pipe screening'
            for label, field in (
                ('Remaining life (years)', 'remaining_life_years'),
                ('Next inspection', 'due_date'),
                ('Inspection interval (years)', 'interval_years'),
                ('Pressure thickness mm', 'pressure_wall_mm'),
                ('Required thickness mm', 'required_wall_mm'),
                ('CR used mm/year', 'rate_mm_year'),
            ):
                if screen.get(field) is not None:
                    record[label] = screen[field]
        records.append(record)

    columns = list(REVIEW_FIRST)
    columns.extend(label for label in headers if label not in columns
                   and any(record.get(label) not in (None, '') for record in records))
    formats = [number_format(label) for label in columns]
    return {
        'columns': [{'label': label, 'format': fmt} for label, fmt in zip(columns, formats)],
        'rows': [[table_value(record.get(label), fmt) for label, fmt in zip(columns, formats)]
                 for record in records],
    }


def number_format(label):
    if label.endswith(('psi', '(psi)')):
        return 'pressure'
    if label.endswith(('years', '(years)')):
        return 'years'
    if label.endswith('mm/year'):
        return 'rate'
    if label.endswith((' mm', ' in', ' F')):
        return 'decimal'
    return None


def table_value(value, fmt):
    if fmt and value not in (None, ''):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return number if isfinite(number) else None
    return value


def workbook_bytes(result):
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    snapshot = review_rows(result)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Calculations'
    sheet.sheet_view.showGridLines = False
    sheet.append(['DRAFT / NOT VALIDATED'])
    sheet['A1'].font = Font(bold=True, color='9A5114')
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
    sheet.append([column['label'] for column in snapshot['columns']])
    sheet.freeze_panes = 'B3'
    formats = {'pressure': '#,##0', 'years': '0.#', 'rate': '0.##', 'decimal': '0.##'}
    for idx, column in enumerate(snapshot['columns'], start=1):
        cell = sheet.cell(2, idx)
        cell.fill = PatternFill('solid', fgColor='223D46')
        cell.font = Font(bold=True, color='FFFFFF')
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        width = 24 if column['format'] is None else 16
        if column['label'] in {'Location', 'Result', 'Missing inputs'}:
            width = 38
        sheet.column_dimensions[get_column_letter(idx)].width = width
    sheet.row_dimensions[2].height = 32
    for row_index, row in enumerate(snapshot['rows'], start=3):
        for idx, (value, column) in enumerate(zip(row, snapshot['columns']), start=1):
            cell = sheet.cell(row_index, idx, value)
            if isinstance(value, str):
                cell.data_type = 's'
            if column['format']:
                cell.number_format = formats[column['format']]
            else:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
            if row_index % 2 == 0:
                cell.fill = PatternFill('solid', fgColor='EFF5F5')
    sheet.auto_filter.ref = f'A2:{get_column_letter(sheet.max_column)}{sheet.max_row}'
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
