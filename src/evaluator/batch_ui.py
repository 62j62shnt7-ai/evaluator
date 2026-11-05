"""Review UI for component-aware draft batch evaluations."""
from evaluator.workflow_ui import E, hidden, field, shell, numeric
def batch_page(service, comparison_id, notice='', result_id=None, profile_sheet=None):
    flow = service.workflow
    comparison = flow.comparison(comparison_id)
    profiles = service.batch.profiles(comparison['current_selection'][0])
    revision = flow.revision()
    body = '<h1>Component batch evaluation</h1>'
    body += '<p>Review each component record assignment and available output. All calculations remain <strong>DRAFT / NOT VALIDATED</strong>; this page does not declare equipment fitness.</p>'
    body += f'<p><a href="/workflow?comparison={E(comparison_id)}">Back to inspection comparison</a> · {E(comparison["asset"])} · {E(comparison["current_selection"][1])}</p>'

    if not profiles:
        body += '<section class="card"><h2>Import source engineering records</h2><p>Read-only records are extracted from recognized design sheets. Formula caches remain proposals and are not treated as measured UT.</p>'
        body += f'<form method="post" action="/workflow/batch-prepare">{hidden("comparison_id", comparison_id)}{hidden("revision", revision)}<button>Read engineering records</button></form></section>'
        return shell('Component batch evaluation', body, notice)

    preview = service.batch.preview(comparison_id, profile_sheet)
    sheets = ''.join(f'<option value="{E(name)}" {"selected" if name == preview["profile_sheet"] else ""}>{E(name)}</option>' for name in preview['sheets'])
    body += '<section class="card"><h2>Preview and calculate</h2>'
    body += '<p>Review source sheet and proposed assignments before saving. Unsupported geometry, unresolved dates, missing inputs and edition conflicts stay visible per row.</p>'
    body += f'<form method="get" action="/workflow/batch"><input type="hidden" name="comparison" value="{E(comparison_id)}"><label>Engineering scenario <select name="profile_sheet" onchange="this.form.submit()">{sheets}</select></label></form>'
    body += f'<p>{preview["counts"]["current"]} current rows · {preview["counts"]["historical_ready"]} historical rates available · {preview["counts"]["life_ready"]} remaining-life candidates currently ready</p>'

    rows = preview['rows']
    profiles_by_id = {profile['id']: profile for profile in preview['profiles']}
    body += '<div class="scroll"><table><thead><tr><th>Location</th><th>Current UT</th><th>Previous UT</th><th>Source record</th><th>Required thickness</th><th>History rate</th><th>Remaining life</th><th>Selected interval / maximum / due date</th><th>MAWP at remaining life / next inspection</th><th>Readiness / issues</th></tr></thead><tbody>'
    for row in rows:
        source = row['profile']
        if source:
            record = f'{source["sheet"]}!row {source["row"]} · {source["code_family"]} {source.get("code_edition") or "edition unresolved"} · {row["assignment_basis"]}'
            source_interval=source.get('fields',{}).get('selected_interval_years',{})
            if source_interval.get('kind')=='literal':
                record+=f' · workbook interval entry {E(source_interval.get("value"))} y (manual override candidate)'
        else:
            record = 'Unassigned · ' + (', '.join(row['issues']) or 'record missing')
            if row['current_id'] and preview['profiles']:
                candidates = [profiles_by_id[key] for key in row.get('candidate_profile_ids', []) if key in profiles_by_id]
                assignment_options = candidates or preview['profiles']
                options = ''.join(
                    f'<option value="{E(profile["id"])}">{E(profile["component"])} / {E(profile["point"])} · row {profile["row"]} · {E(profile["geometry"])} · {E(profile["code_family"])}</option>'
                    for profile in assignment_options
                )
                availability = 'same-label candidates' if candidates else 'all records in the selected scenario'
                record += f'<details><summary>Assign source record</summary><form method="post" action="/workflow/batch-assignment">{hidden("comparison_id", comparison_id)}{hidden("revision", revision)}{hidden("profile_sheet", preview["profile_sheet"])}{hidden("row_ids", row["current_id"])}<label>Component record · {availability}<select name="profile_id" required><option value="">Choose a component record…</option>{options}</select></label><label class="check"><input type="checkbox" name="confirm_assignment" value="yes" required>I checked this source row belongs to this physical component.</label><button>Save row assignment</button></form></details>'
        def show(key):
            value = row.get(key)
            return '—' if value in (None, '') else E(value) if key=='due_date' else f'{float(value):.4f}'.rstrip('0').rstrip('.') if key=='apparent_rate_mm_year' else f'{float(value):.2f}'.rstrip('0').rstrip('.')
        outputs = f'{show("inspection_interval_years")} / {show("maximum_interval_years")} / {show("due_date")}'
        mawp = show('mawp_MPa')+' / '+show('forecast_mawp_MPa')+' MPa'
        body += '<tr>' + ''.join(f'<td>{value}</td>' for value in (
            E(row['location']), show('current_thickness_mm'), show('previous_thickness_mm'), record,
            show('required_thickness_mm'), show('apparent_rate_mm_year'), show('remaining_life_years'),
            outputs, mawp, E('; '.join(row['issues']) or 'Ready for selected outputs'),
        )) + '</tr>'
    body += '</tbody></table></div>'

    body += '<details><summary>Grouped component inputs</summary><p>Apply one explicit override to a compatible group. Each group shares code family, edition, geometry, material, pressure and strength. Saving an override creates a new revision and marks prior batch results stale.</p>'
    for group in preview['groups']:
        overrides = preview['settings'].get('group_overrides', {}).get(group['id'], {})
        body += f'<form class="card" method="post" action="/workflow/batch-overrides">{hidden("comparison_id", comparison_id)}{hidden("revision", revision)}{hidden("profile_sheet", preview["profile_sheet"])}{hidden("group_ids", group["id"])}'
        body += f'<strong>{E(group["geometry"])} · {E(group["code_family"])} {E(group.get("code_edition") or "edition unresolved")}</strong><p>{group["count"]} locations · {group["ready"]} life outputs currently ready · {E(group.get("material") or "material unresolved")}</p>'
        for key, label in [('required_thickness_mm', 'Governing required thickness · mm'), ('adopted_rate_mm_year', 'Adopted rate · mm/year'), ('structural_minimum_mm', 'Structural minimum · mm'), ('interval_fraction', 'Inspection interval fraction'), ('interval_cap_years', 'Inspection interval cap · years'), ('selected_interval_years', 'Selected inspection interval · years'), ('forecast_years', 'Forecast horizon · years'), ('forecast_factor', 'Forecast rate multiplier'), ('year_days', 'Days per year'), ('allowance_mm', 'Pressure allowance · mm')]:
            body += field(key, label, overrides.get(key, ''), kind='number', required=False)
        body += '<button>Save group inputs</button></form>'
    body += '</details>'

    body += f'<form method="post" action="/workflow/batch-evaluate">{hidden("comparison_id", comparison_id)}{hidden("revision", revision)}{hidden("preview_token", preview["preview_token"])}{hidden("profile_sheet", preview["profile_sheet"])}'
    body += '<label class="check"><input type="checkbox" name="confirm_records" value="yes" required>I reviewed the proposed source records and their component assignments for this inspection.</label>'
    body += '<label class="check"><input type="checkbox" name="confirm_history" value="yes">Use confirmed physical-point matches to calculate apparent historical rates.</label>'
    body += '<label class="check"><input type="checkbox" name="confirm_rules" value="yes">I checked code edition, geometry, factors and applicability for any draft pressure calculations.</label>'
    body += '<label class="check"><input type="checkbox" name="confirm_conflicts" value="yes">I reviewed and reconciled conflicts between copied source current values and measured UT.</label>'
    body += '<label>Basis <select name="basis"><option value="provided">Use provided required-thickness records</option><option value="recalculate">Recalculate supported draft pressure candidates</option></select></label>'
    body += field('year_days', 'Days per year convention (blank uses the source convention)', '', kind='number')
    body += '<p class="muted">Both MAWP projections use the calculated remaining life by default. A manually selected inspection interval changes the next-inspection projection using the source two-rate multiplier. The scheduled date remains a separate source record.</p>'
    body += '<label class="check"><input type="checkbox" name="allow_increase" value="yes">Allow adopted-rate review when measured thickness increased; this does not change the apparent rate.</label>'
    body += '<p class="muted">Batch evaluation preserves all current and historical locations. Blank outputs mean their specific inputs or applicability checks are unresolved.</p><button>Save component batch evaluation</button></form></section>'

    batches = service.batch.results(comparison_id)
    if batches:
        body += '<section class="card"><h2>Saved batch results</h2>'
        for result in batches:
            stale = result['stale']
            body += f'<details {"open" if result["id"] == result_id else ""}><summary>{E(result["profile_sheet"])} · revision {result["input_revision"]} · {"STALE" if stale else result["status"]}</summary>'
            body += f'<p>{result["summary"]["current"]} locations · {result["summary"]["life_evaluated"]} life · {result["summary"]["interval_evaluated"]} intervals · {result["summary"]["mawp_evaluated"]} MAWP outputs. Export the project revision to include full trace and source snapshots.</p></details>'
        body += '</section>'
    return shell('Component batch evaluation', body, notice)
