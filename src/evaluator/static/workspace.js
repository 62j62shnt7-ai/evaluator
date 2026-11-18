'use strict';
const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (value, decimals = 2) => value == null || value === '' ? '—' :
    Number(value).toLocaleString(undefined, {maximumFractionDigits: decimals});
const rateLabel = value => {
    const rate = Number(value);
    if (rate > 0 && rate < 0.01) return '&lt;0.01';
    if (rate < 0 && rate > -0.01) return '&gt;-0.01';
    return num(value);
};
const wholePressure = value => value == null || value === '' ? '—' : Math.floor(Number(value)).toLocaleString();
let state,cid=new URLSearchParams(location.search).get('comparison'),selected=new Set(),screen='import';
const workspace=()=>state?.workspace;
function codeBasisStatus(row) {
    const labels = {
        ROUTE_SELECTED:'Calculation method available',
        FITTING_REVIEW_REQUIRED:'Fitting rating check optional',
        FITTING_CHECK_AVAILABLE:'Fitting rating check available',
        SLEEVE_T_REVIEW_REQUIRED:'Sleeve-T assessment needed',
        SLEEVE_T_DOCUMENTED_ASSESSMENT:'Sleeve-T assessment recorded',
        NOT_ASSESSED:'Calculation method unavailable',
        NEEDS_COMPONENT_IDENTIFICATION:'Confirm component identity',
    };
    return labels[row.routing?.status] || 'Confirm code basis';
}
function message(text,error=false){$('message').textContent=text;$('message').hidden=!text;$('message').classList.toggle('error',error);}
async function actionResponse(response) {
    if (!response.headers.get('Content-Type')?.includes('application/json')) {
        throw Error(`The app returned an unexpected response (HTTP ${response.status}). Reload the page and try again.`);
    }
    const data = await response.json();
    if (!response.ok) throw Error(data.error || `Request failed (HTTP ${response.status}).`);
    return data;
}
function options(id,items,value,placeholder='Choose…'){const el=$(id);el.innerHTML=`<option value="">${esc(placeholder)}</option>`+items.map(([v,label])=>`<option value="${esc(v)}">${esc(label)}</option>`).join('');el.value=value||'';}
function navigate(next) {
    screen = next;
    document.querySelectorAll('.screen').forEach(el => el.hidden = el.id !== 'screen-' + next);
    for (const button of document.querySelectorAll('[data-screen]')) {
        const active = button.dataset.screen === next;
        button.classList.toggle('active', active);
        if (active) {
            button.setAttribute('aria-current', 'page');
            $('deskTitle').textContent = button.textContent;
        } else {
            button.removeAttribute('aria-current');
        }
    }
    if (next === 'calculations') showCalculations();
}
async function load(){const response=await fetch('/api/workspace'+(cid?'?'+new URLSearchParams({comparison:cid}):''));state=await response.json();if(!response.ok)throw Error(state.error);if(workspace()){cid=workspace().comparison.id;history.replaceState(null,'','/?'+new URLSearchParams({comparison:cid}));const valid=new Set(workspace().rows.map(r=>r.current_id));selected=new Set([...selected].filter(id=>valid.has(id)));}render();}
async function workspaceRequest(name, payload) {
    const response = await fetch('/api/workspace/' + name, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({comparison_id: cid, revision: state.revision, ...payload})
    });
    return actionResponse(response);
}

async function action(name, payload = {}) {
    $('busy').hidden = false;
    try {
        const data = await workspaceRequest(name, payload);
        if (name === 'import' && !data.comparison_id) {
            const response = await fetch('/api/workspace?'+new URLSearchParams(cid ? {comparison: cid} : {}));
            if (response.ok) state.revision = (await response.json()).revision;
            message(data.message, true);
            return data;
        }
        if (data.reset_workspace) {
            cid = null;
            selected.clear();
            $('batchForm').reset();
            $('drawer').hidden = true;
            history.replaceState(null, '', '/');
        }
        if (data.comparison_id && data.comparison_id !== cid) {
            cid = data.comparison_id;
            selected.clear();
        }
        if (data.revision == null) await load();
        else state.revision = data.revision;
        if (workspace() && ['apply', 'correct', 'identity', 'pair', 'dates', 'undo', 'apply_code_basis', 'prefill_sheet_materials', 'review_workbook_pipes', 'review_fittings', 'record_sleeve_assessment'].includes(name)) {
            try {
                await workspaceRequest('evaluate', {basis: 'assigned'});
            } catch (error) {
                await load();
                message('Change saved. Recalculation failed. ' + error.message, true);
                return data;
            }
        }
        await load();
        navigate(workspace() ? (name === 'evaluate' ? 'calculations' : 'workspace') : 'import');
        message(data.message || 'Saved.');
        return data;
    } catch (error) {
        message(error.message, true);
    } finally {
        $('busy').hidden = true;
    }
}
function sheets() {
    const source = state.sources.find(item => item.source_id === $('source').value);
    const current = workspace()?.comparison.current_selection;
    const names = source?.sheets || [];
    options('sheet', names.map(name => [name, name]),
        current?.[0] === source?.source_id ? current?.[1] : names.length === 1 ? names[0] : '');
}
function render(){const w=workspace();renderWorkbooks();$('revision').textContent='Revision '+state.revision;options('source',state.sources.map(s=>[s.source_id,s.file_name]),w?.comparison.current_selection[0]||$('source').value);sheets();options('comparison',state.comparisons.map(c=>[c.id,c.asset+' · '+c.sheet]),cid);dimensions();if(!w){$('screen-import').hidden=false;$('screen-workspace').hidden=true;return;}$('screen-import').hidden=true;$('screen-workspace').hidden=false;$('reviewWorkbookPipes').hidden=Boolean(w.comparison.selected_ut_only);$('reviewSleeveTees').hidden=!w.rows.some(row=>row.geometry==='sleeve_tee');$('asset').textContent=w.comparison.asset;$('scope').textContent=w.comparison.current_selection[1];const campaigns=w.campaigns.map(c=>[c.campaign,(c.label||c.campaign)+' · '+c.count+' readings']);options('previousCampaign',campaigns,w.comparison.baseline[2]);options('currentCampaign',campaigns,w.comparison.current_selection[2]);$('campaignDateFields').innerHTML=w.campaigns.filter(c=>!c.campaign.startsWith('auto:')).map(c=>`<label>${esc(c.campaign)} exact date<input type="date" data-campaign-date="${esc(c.campaign)}"></label>`).join('');options('sectionFilter',[...new Set(w.rows.map(r=>r.segment))].map(v=>[v,v]),$('sectionFilter').value,'All sections');table();results();}
function visible(){const q=$('search').value.toLowerCase(),component=$('componentFilter').value;return (workspace()?.rows||[]).filter(r=>{const type=r.geometry||'unknown';const fits=!component||(component==='straight_pipe'?type==='straight_pipe':['elbow','tee','reducer','branch','fitting','sleeve_tee'].includes(type));return fits&&(!$('sectionFilter').value||r.segment===$('sectionFilter').value)&&[r.location,r.segment,r.material].join(' ').toLowerCase().includes(q);});}
function edit(r,key,value){return `<input class="engineering-input" type="number" min="0" step="any" data-engineering="${key}" data-row="${esc(r.current_id)}" value="${esc(value??'')}" aria-label="${key} for ${esc(r.location)}">`;}
function rowSelect(r,key,value,items){return `<select data-engineering="${key}" data-row="${esc(r.current_id)}" aria-label="${key} for ${esc(r.location)}">${[...new Set([value||'',...items])].map(v=>`<option value="${esc(v)}" ${String(v)===String(value??'')?'selected':''}>${esc(v||'Choose…')}</option>`).join('')}</select>`;}
function liveAssessment(panel, row, draft) {
    let revision = 0;
    let timer;
    return function update() {
        const request = ++revision;
        clearTimeout(timer);
        panel.textContent = 'Updating assessment…';
        timer = setTimeout(async () => {
            try {
                if (!panel.isConnected) return;
                const response = await fetch('/api/workspace/location_preview', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({comparison_id: cid, revision: state.revision, id: row.current_id, ...draft()})
                });
                const result = await actionResponse(response);
                if (request !== revision || !panel.isConnected) return;
                const value = (amount, unit) => amount == null ? 'Unavailable' : num(amount) + ' ' + unit;
                const fitting = result.fitting;
                const progress = result.fitting_progress;
                const metrics = progress && !fitting ? [
                    ['Observed wall loss', value(progress.wall_loss_mm, 'mm')],
                    ['Observed corrosion', value(progress.observed_rate_mm_year, 'mm/year')],
                    ['Projected physical wall', value(progress.projected_wall_mm, 'mm')],
                    ...(row.geometry === 'elbow'
                        ? [['Local bend pressure candidate', value(progress.bend_pressure_psi, 'psi')]]
                        : [['Qualified pressure at measured wall', value(progress.qualified_current_pressure_psi, 'psi')]]),
                ] : [
                    ['Observed corrosion', value(result.observed, 'mm/year')],
                    ['Adopted corrosion', value(result.adopted, 'mm/year')],
                    ['Projected physical wall', value(result.wall, 'mm')],
                    ['Wall credited', value(fitting?.credited_wall_mm ?? result.credited, 'mm')],
                    [fitting ? 'Documented pressure checked' : 'Next-inspection component pressure',
                        value(fitting?.pressure_psi ?? result.pressure_psi, 'psi')],
                    [fitting ? 'Projection interval' : 'Next inspection', fitting
                        ? value(fitting.projection_years, 'years') : result.date || 'Unavailable'],
                ];
                if (fitting?.qualified_pressure_psi) metrics.push(['Qualified next-interval pressure',
                    value(fitting.qualified_pressure_psi, 'psi')]);
                if (fitting?.bend_pressure_psi) metrics.push(['Bend location pressure candidate',
                    value(fitting.bend_pressure_psi, 'psi')]);
                if (fitting) metrics.push(['Projected wall check', fitting.projected_meets_minimum
                    ? 'Above documented minimum' : 'At or below documented minimum']);
                const issues = progress && !fitting
                    ? [...progress.missing, ...progress.pressure_missing] : result.issues;
                panel.innerHTML = '<p class="assessment-caption">Live draft assessment</p><dl>' + metrics.map(([label, reading]) =>
                    '<div><dt>' + esc(label) + '</dt><dd>' + esc(reading) + '</dd></div>').join('') + '</dl>' +
                    (issues.length ? '<small>' + esc(issues.join(' · ').replaceAll('_', ' ')) + '</small>' : '');
            } catch (error) {
                if (request === revision) panel.textContent = error.message;
            }
        }, 220);
    };
}

function attachCodePreview(form, row, initial = true) {
    const panel = document.createElement('aside');
    panel.className = 'live-assessment';
    panel.setAttribute('aria-live', 'polite');
    form.before(panel);
    const update = liveAssessment(panel, row, () => ({
        values: {...Object.fromEntries(new FormData(form)),
            code_edition: showEditionDefault(form), code_owner_confirmed: form.elements.code_owner_confirmed.checked ? 'yes' : 'no', reviewed: form.elements.reviewed.checked ? 'yes' : 'no'},
    }));
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    if (initial) update();
    else panel.hidden = true;
    form.addEventListener('input', () => { panel.hidden = false; });
    form.addEventListener('change', () => { panel.hidden = false; });
}

function codeEditor(id, host = $('details')){const r=workspace().rows.find(x=>x.current_id===id);if(!r)return;if(host===$('details')){$('drawer').hidden=false;closeRowEditor();}const workbookInput = key => r.fitting_workbook_review?.inputs[key]?.value;const codes=['ASME B31.3','ASME B31.4','ASME B31.8','ASME VIII-1','API 650'],assets=['process_piping','liquid_transmission','gas_transmission','production_flowline','pressure_vessel','storage_tank'];host.innerHTML=`<h2>Code basis · ${esc(r.location)}</h2><p>Set the construction basis for this component. Code routing only selects an existing draft method; it does not establish MAWP or engineering approval. Flowlines require an explicit service boundary.</p><form id="codeBasisForm" data-row="${esc(id)}"><label>Asset / service boundary<select name="code_asset_type" required><option value="">Choose…</option>${assets.map(v=>`<option value="${v}" ${r.code_asset_type===v?'selected':''}>${v.replaceAll('_',' ')}</option>`).join('')}</select></label><label>Construction code<select name="code_family" required><option value="">Choose…</option>${codes.map(v=>`<option ${r.code_family===v?'selected':''}>${v}</option>`).join('')}</select></label><label>Edition year (optional)<input name="code_edition" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" value="${esc(r.code_edition||'')}" ></label><label class="wide">Code basis evidence<input name="code_evidence" value="${esc(r.code_evidence||'')}" placeholder="Document, line list, drawing or approved basis reference" required></label><label class="check"><input type="checkbox" name="code_owner_confirmed" value="yes" ${r.code_owner_confirmed?'checked':''} required>I confirmed this code’s applicability and boundary for this component.</label><label>Calculation geometry<select name="geometry" required><option value="">Choose…</option>${['straight_pipe','elbow','tee','reducer','branch','nozzle','shell','cylindrical_shell','ellipsoidal_head_2to1','head_unspecified','unknown'].map(v=>`<option value="${v}" ${(r.geometry === 'unknown' ? r.fitting_workbook_review?.geometry : r.geometry)===v?'selected':''}>${v.replaceAll('_',' ')}</option>`).join('')}</select></label><fieldset id="methodFields"><legend>Inputs for this calculation</legend>
<label>Material section thickness (mm)<input name="material_thickness_mm" type="number" step="any" value="${esc(r.input_trace?.overrides?.material_thickness_mm??'')}"></label>
<label>Material certificate and heat-treatment record<input name="material_condition_reference" value="${esc(r.input_trace?.overrides?.material_condition_reference??'')}"></label>
<label>Process piping method<select name="pipe_method">
<option value="example" ${r.input_trace?.basis==='row7'?'selected':''}>Row 7 workbook example (E = 1, W = 1, Y = 0.4)</option>
<option value="code" ${r.input_trace?.basis!=='row7'?'selected':''}>B31.3 with entered E, W and Y</option>
</select></label><p id="methodHint" aria-live="polite"></p>
<div class="fields">

<label>Reference temperature<select id="referenceTemperature"></select></label>
</div><label>Basic B31.8 pipeline class (only where the basic factor applies)
<select name="gas_basic_class"><option value="manual">Use manual factor</option>
${['1 Division 1','1 Division 2','2','3','4'].map(value=>`<option value="${value}" ${r.input_trace?.overrides?.gas_basic_class===value?'selected':''}>Class ${value}</option>`).join('')}</select></label>
<output id="referencePreview" aria-live="polite"></output>
<label>Material specification and grade<select name="material" id="referenceMaterial"><option value="${esc(r.material || workbookInput('material'))}">${esc(r.material || workbookInput('material') || 'Choose a grade')}</option></select></label>
<label>Product form<select name="product_form"><option value="">Choose…</option>${['plate','pipe','forging'].map(form=>`<option value="${form}" ${r.profile?.product_form===form?'selected':''}>${form}</option>`).join('')}${['LFW','HFW','SMLS','SAWL','SAWH','COWL','COWH','CW'].map(form=>`<option value="${form}" ${r.profile?.product_form===form?'selected':''}>${form}</option>`).join('')}</select></label>
${Object.entries({D_outside_in:'Outside diameter (in)',nominal_thickness_mm:'Nominal wall (mm)',adopted_rate_mm_year:'Adopted corrosion rate (mm/year)',temperature_F:'Design metal temperature (°F)',D_inside_in:'Inside diameter (in)',P_psi:'Design pressure (psi)',E_joint:'Joint efficiency',structural_minimum_mm:'Structural minimum (mm)',E_quality:'Pipe quality factor',W_reduction:'Weld strength reduction factor',Y_coefficient:'Y coefficient',F_class:'Gas pipeline class factor',F_design:'Liquid pipeline design factor',E_weld:'Pipeline weld factor',T_temp:'Gas pipeline temperature factor',SMYS_psi:'Pipeline SMYS (psi)',selected_interval_years:'Selected next interval (years)',interval_fraction:'Inspection interval fraction of remaining life',interval_cap_years:'Inspection interval cap (years)'}).map(([key,label])=>`<label>${label}<input type="number" step="any" name="${key}" value="${esc(r.input_trace?.overrides?.[key]??r.profile?.fields?.[key]?.value ?? workbookInput(key === 'P_psi' ? 'fitting_pressure_psi' : key) ?? '')}"></label>`).join('')}
<label>Manual allowable stress (psi), if needed<input type="number" step="any" name="S_allow_psi" value="${esc(r.input_trace?.overrides?.S_allow_psi ?? workbookInput('S_allow_psi') ?? '')}"></label>
<label>Manual material property reference<input name="material_reference" value="${esc(r.input_trace?.overrides?.material_reference??'')}"></label>
<label>Review basis or corrosion-rate reference<input name="review_note" value="${esc(r.input_trace?.overrides?.review_note??'')}"></label>
<label>Required wall at this fitting location (mm)<input name="required_thickness_mm" type="number" min="0" step="any" value="${esc(r.input_trace?.overrides?.required_thickness_mm)}"></label>
<label>Approved required-wall reference<input name="fitting_life_reference" value="${esc(r.input_trace?.overrides?.fitting_life_reference)}"></label>
<label>API 570 thickness inspection class (routine UT without RBI or special limits)
    <select name="api570_ut_class"><option value="">Use workbook or reviewed interval policy</option>
        <option value="conservative" ${r.input_trace?.overrides?.api570_ut_class === 'conservative' ? 'selected' : ''}>Conservative routine UT planning (5-year cap)</option>
        ${['1','2','3'].map(value => `<option value="${value}" ${r.input_trace?.overrides?.api570_ut_class === value ? 'selected' : ''}>Class ${value}</option>`).join('')}
    </select>
</label>
<label class="check"><input name="allow_increase" type="checkbox" value="yes" ${r.input_trace?.overrides?.allow_increase === 'yes' ? 'checked' : ''}>
    I reviewed the increase in measured wall. Use the entered corrosion rate and review basis.</label>
${Object.entries({bend_radius_in:'Centerline bend radius (in)', allowance_mm:'Remaining wall allowance (mm)'}).map(([key,label]) =>
    `<label>${label}<input name="${key}" type="number" min="0" step="any" value="${esc(r.input_trace?.overrides?.[key])}"></label>`).join('')}
<label>UT position on bend<select name="bend_position"><option value="">Choose a position</option>
    ${['intrados','extrados','sidewall_left','sidewall_right','tangent_start','tangent_end'].map(position =>
        `<option value="${position}" ${r.input_trace?.overrides?.bend_position === position ? 'selected' : ''}>${position.replaceAll('_',' ')}</option>`).join('')}
</select></label>
<label>Bend design basis reference<input name="bend_design_reference" value="${esc(r.input_trace?.overrides?.bend_design_reference)}"></label>

<label>Physical fitting tag<input name="qualification_tag" value="${esc(r.input_trace?.overrides?.qualification_tag)}"></label>
<label>Approved qualification and UT coverage reference<input name="qualification_reference" value="${esc(r.input_trace?.overrides?.qualification_reference)}"></label>
<label>Qualification temperature (°F)<input name="qualification_temperature_F" type="number" step="any" value="${esc(r.input_trace?.overrides?.qualification_temperature_F)}"></label>
<label>Approved minimum wall (mm), pressure (psi) pairs<textarea name="qualification_points" rows="3">${esc(r.input_trace?.overrides?.qualification_points)}</textarea></label>
</fieldset><label class="check"><input type="checkbox" name="reviewed" value="yes" ${r.reviewed?'checked':''}>I checked the component assignment and calculation inputs against the source records.</label><button class="primary">Save code basis</button></form><p class="muted">${esc(codeBasisStatus(r))} · results remain DRAFT / NOT VALIDATED.</p>`;const form = host.querySelector('#codeBasisForm');
bindReferenceSelectors(form, r);attachCodePreview(form, r, host === $('details'));form.onsubmit=saveCodeBasis;}
async function saveCodeBasis(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries([...new FormData(form)].filter(([, value]) => value !== ''));
    values.reviewed = values.reviewed || 'no';
    values.code_edition = showEditionDefault(form);
    const inDrawer = $('details').contains(form);
    const saved = await action('apply', {ids:[form.dataset.row], values});
    if (saved && inDrawer) codeEditor(form.dataset.row);
}
function showEditionDefault(form) {
    const code = form.elements.code_family.value;
    const fallback = state.default_code_editions[code] || '';
    form.elements.code_edition.placeholder = fallback ? 'Defaults to ' + fallback : 'Leave blank if unknown';
    return form.elements.code_edition.value || fallback;
}

function reviewPipeLocation(row) {
    codeEditor(row.current_id);
    const form = $('codeBasisForm');
    const panel = document.createElement('section');
    const proposal = row.workbook_review;
    const earlier = (workspace().previous_choices_by_section?.[row.match_identity?.section] || [])
        .filter(choice => choice.date && row.inspection_date && choice.date.slice(0, 7) < row.inspection_date.slice(0, 7));
    panel.innerHTML = `
        <h3>Imported workbook evidence</h3>
        <p>Current UT · ${esc(row.current_sheet)}!${esc(row.current_cell)} · ${num(row.current_thickness_mm)} mm</p>
        <p>${row.previous_cell
            ? `Earlier UT · ${esc(row.previous_sheet)}!${esc(row.previous_cell)} · ${num(row.previous_thickness_mm)} mm`
            : 'No earlier UT is linked. Enter a reviewed corrosion rate and its basis for a baseline forecast.'}</p>
        ${!row.previous_id && earlier.length ? `
            <label>Match imported earlier UT<select data-earlier-ut><option value="">Choose a reading</option>
                ${earlier.map(choice => `<option value="${esc(choice.id)}">${esc(choice.identity.joint)} /
                    ${esc(choice.identity.band)} · ${esc(choice.date)} · ${esc(choice.cell)} · ${num(choice.value)} mm</option>`).join('')}
            </select></label>
            <button type="button" data-save-earlier disabled>Confirm same location and link reading</button>` : ''}
        ${(proposal.alternate_records || []).map((candidate, index) => `
            <div>
                <p>Possible historical evaluation match · joint ${esc(candidate.joint)} / band ${esc(candidate.band)}.
                    The earlier wall agrees at ${esc(candidate.ut_source)}.</p>
                <ul>${Object.entries(candidate.linked_inputs).map(([key, value]) =>
                    `<li>${esc(pipeEvidenceLabels[key] || key)} · ${esc(value)} · ${esc(candidate.references[key])}</li>`).join('')}</ul>
                <label class="check"><input type="checkbox" data-confirm-alternate="${index}">
                    I confirm this historical record applies to the same physical pipe location.
                </label>
                <button type="button" data-use-alternate="${index}" disabled>Use historical inputs and calculate</button>
            </div>`).join('')}`;
    form.before(panel);
    const earlierSelect = panel.querySelector('[data-earlier-ut]');
    if (earlierSelect) {
        const save = panel.querySelector('[data-save-earlier]');
        earlierSelect.onchange = () => { save.disabled = !earlierSelect.value; };
        save.onclick = async () => {
            const saved = await action('identity', {id:row.current_id, previous_id:earlierSelect.value});
            if (saved) {
                const updated = workspace().rows.find(item => item.current_id === row.current_id);
                if (updated?.workbook_review) reviewPipeLocation(updated);
                else $('drawer').hidden = true;
            }
        };
    }
    for (const button of panel.querySelectorAll('[data-use-alternate]')) {
        const index = button.dataset.useAlternate;
        const confirmation = panel.querySelector(`[data-confirm-alternate="${index}"]`);
        confirmation.onchange = () => { button.disabled = !confirmation.checked; };
        button.onclick = async () => {
            if (!confirmation.checked) return;
            const candidate = proposal.alternate_records[index];
            const saved = await action('review_workbook_pipes', {
                ids:[row.current_id], alternate_records:{[row.current_id]:candidate.profile_id}, confirmed:true,
            });
            if (saved) {
                $('drawer').hidden = true;
                await action('evaluate', {basis:'assigned'});
            }
        };
    }
}

const pipeEvidenceLabels = {
    material:'Material', P_psi:'Design pressure (psi)', D_outside_in:'OD (in)',
    structural_minimum_mm:'Structural minimum (mm)', S_allow_psi:'Allowable stress (psi)',
    adopted_rate_mm_year:'Adopted corrosion rate (mm/year)', nominal_thickness_mm:'Nominal wall (mm)',
};

function batchCodeEditor() {
    const w = workspace();
    if (!w) return;
    const rows = w.rows.filter(row => row.current_id);
    const common = key => rows.length && rows.every(row => row[key] === rows[0][key]) ? rows[0][key] || '' : '';
    $('drawer').hidden = false;
    $('details').innerHTML = `<h2>Set code basis</h2>
        <p>Switch the calculation basis and recalculate ${esc(w.comparison.current_selection[1])}.</p>
        <form id="batchCodeBasisForm"><div id="priorCodeBases" aria-live="polite"></div>
            <label>Apply to<select name="scope">
                <option value="sheet">Entire current sheet · ${rows.length} locations</option>
                <option value="selected" ${selected.size ? '' : 'disabled'}>Selected locations · ${selected.size}</option>
            </select></label>
            <label>Asset / service boundary<select name="code_asset_type" required><option value="">Choose…</option></select></label>
            <label>Construction code<select name="code_family" required><option value="">Choose…</option></select></label>
            <label>Edition year (optional)<input name="code_edition" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" value="${esc(common('code_edition'))}"></label>
            <label>Code basis evidence<input name="code_evidence" placeholder="Document, line list, drawing or approved basis reference" value="${esc(common('code_evidence'))}" required></label>
            <label class="check"><input type="checkbox" name="code_owner_confirmed" value="yes" required>
                I confirm this code and service boundary apply to all locations in this scope.
            </label>
            <fieldset id="batchGasInputs" hidden disabled><legend>Shared straight-pipe inputs, if documented</legend>
                <label>Pipe manufacturing type<select name="product_form"><option value="">Keep existing</option>
                    ${['SMLS','LFW','HFW','SAWL','SAWH','COWL','COWH','CW'].map(value => `<option>${value}</option>`).join('')}
                </select></label>
                <label>Basic location class<select name="gas_basic_class"><option value="">Keep existing</option>
                    ${['1 Division 1','1 Division 2','2','3','4'].map(value => `<option value="${value}">Class ${value}</option>`).join('')}
                </select></label>
                <label>Design metal temperature (°F)<input name="temperature_F" type="number" min="0" step="any"></label>
                <label>Longitudinal weld factor<input name="E_weld" type="number" min="0" max="1" step="any"></label>
            </fieldset>
            <button class="primary">Apply code basis</button>
        </form>`;
    const form = $('batchCodeBasisForm');
    const choices = state.codes_by_asset;
    const asset = form.elements.code_asset_type;
    const code = form.elements.code_family;
    asset.id = 'batchCodeAsset';
    code.id = 'batchCodeFamily';
    options(asset.id, Object.keys(choices).map(value => [value, value.replaceAll('_', ' ')]), common('code_asset_type'));
    function updateCodes(value) {
        const allowed = choices[asset.value] || [...new Set(Object.values(choices).flat())];
        options(code.id, allowed.map(label => [label, label]), allowed.length === 1 ? allowed[0] : value);
        showEditionDefault(form);
        const gas = form.querySelector('#batchGasInputs');
        gas.hidden = gas.disabled = code.value !== 'ASME B31.8';
    }
    updateCodes(common('code_family'));
    fetch('/api/workspace/prior_code_bases', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({comparison_id: cid}),
    }).then(actionResponse).then(({bases}) => {
        if (!form.isConnected || !bases.length) return;
        const area = form.querySelector('#priorCodeBases');
        for (const basis of bases) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = 'Prefill prior basis · ' + basis.code_family + ' ' + basis.code_edition;
            button.onclick = () => {
                asset.value = basis.code_asset_type;
                updateCodes(basis.code_family);
                form.elements.code_edition.value = basis.code_edition;
                form.elements.code_evidence.value = basis.code_evidence;
                form.elements.code_owner_confirmed.checked = false;
            };
            area.append(button);
        }
    }).catch(error => {
        if (form.isConnected) form.querySelector('#priorCodeBases').textContent = error.message;
    });

    function codeChanged() {
        const gas = form.querySelector('#batchGasInputs');
        gas.hidden = gas.disabled = code.value !== 'ASME B31.8';
        form.elements.code_edition.value = '';
        form.elements.code_evidence.value = code.value === common('code_family') ? common('code_evidence') : '';
        showEditionDefault(form);
    }
    asset.onchange = () => {
        const previous = code.value;
        updateCodes(previous);
        if (code.value !== previous) codeChanged();
    };
    code.onchange = codeChanged;
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const {scope, ...values} = Object.fromEntries(new FormData(form));
        if (await action('apply_code_basis', {scope, ids:[...selected], values})) {
            if (scope === 'sheet' && rows.some(row => !row.code_family)) sheetMaterialEditor();
            else $('drawer').hidden = true;
        }
    });
}
$('editBatchCode').onclick = batchCodeEditor;

function materialGrades(rows) {
    const productFor = row => row.geometry === 'straight_pipe' ? 'pipe'
        : ['elbow','tee','reducer','branch','fitting'].includes(row.geometry) ? 'fitting'
        : row.profile?.product_form || 'plate';
    const grades = new Set(rows.flatMap(row => [row.material, row.workbook_review?.detected_material,
        row.fitting_workbook_review?.inputs?.material?.value]).filter(Boolean));
    for (const entry of state.material_stresses) {
        if (rows.some(row => entry.product_form === productFor(row) &&
            (!row.code_family || row.code_family === entry.code_family) &&
            (!row.code_edition || row.code_edition === entry.code_edition))) grades.add(entry.material);
    }
    if (rows.some(row => row.geometry === 'straight_pipe' && row.code_family === 'ASME B31.8')) {
        for (const grade of state.gas_pipe_grades) grades.add('API 5L ' + grade);
    }
    if (rows.some(row => row.geometry === 'straight_pipe' && row.code_family === 'ASME B31.4')) {
        for (const grade of state.liquid_pipe_grades) grades.add(grade);
    }
    return [...grades].sort((a, b) => a.localeCompare(b));
}

function sheetMaterialEditor() {
    const rows = workspace().rows;
    const pipe = rows.filter(row => row.geometry === 'straight_pipe');
    const fittings = rows.filter(row => ['elbow', 'tee', 'reducer', 'branch', 'fitting'].includes(row.geometry));
    const field = (name, label, group) => {
        if (!group.length) return '';
        const grades = materialGrades(group);
        return `<label>${label} · ${group.length} locations
            <select name="${name}"><option value="">Keep existing</option>
                ${grades
                    .map(grade => `<option value="${esc(grade)}">${esc(grade)}</option>`).join('')}
            </select>
        </label>`;
    };
    if (!pipe.length && !fittings.length) {
        $('drawer').hidden = true;
        return;
    }
    $('drawer').hidden = false;
    $('details').innerHTML = `<h2>Prefill materials</h2>
        <p>Choose a shared grade for each component group you want to fill.</p>
        <form id="sheetMaterialsForm">
            ${field('pipe', 'Straight pipes', pipe)}
            ${field('fittings', 'Fittings', fittings)}
            <label class="check"><input type="checkbox" name="replace_existing"> Replace existing grades in these groups</label>
            <button class="primary">Apply material grades</button>
            <button type="button" id="skipSheetMaterials">Continue to locations</button>
        </form>`;
    $('skipSheetMaterials').onclick = () => { $('drawer').hidden = true; };
    $('sheetMaterialsForm').onsubmit = async event => {
        event.preventDefault();
        const {replace_existing, ...materials} = Object.fromEntries(new FormData(event.target));
        if (await action('prefill_sheet_materials', {materials, replace_existing:replace_existing === 'on'})) {
            $('drawer').hidden = true;
        }
    };
}
$('prefillSheetMaterials').onclick = sheetMaterialEditor;

$('reviewWorkbookPipes').onclick = () => {
    const rows = (workspace()?.rows || []).filter(row => row.workbook_review);
    if (!rows.length) return message('No B31.3 straight pipes on this sheet.', true);
    const cell = (value, source, unit) => value == null ? 'Missing' :
        `${num(value)} ${unit}<br><small>${esc(source)}</small>`;
    $('drawer').hidden = false;
    $('details').innerHTML = `<h2>Review straight pipes in batch</h2>
        <p>Review each row’s workbook values. Clear any row you want to review separately. In the pipe workflow, the workbook rate is used when the measured corrosion rate is zero or negative.</p>
        <form id="pipeReviewForm">
            <div class="table-scroll"><table>
                <thead><tr><th>Include</th><th>Location</th><th>Material and design inputs</th><th>Workbook stress</th><th>Workbook rate</th></tr></thead>
                <tbody>${rows.map(row => {
                    const p = row.workbook_review;
                    return `<tr><td>${p.eligible
                        ? `<input type="checkbox" name="ids" value="${esc(row.current_id)}" aria-label="Include ${esc(row.location)}" checked>`
                        : `${esc(p.reason)}<br><button type="button" data-review-pipe="${esc(row.current_id)}">Review location</button>`}</td><td>${esc(row.location)}<br><small>${esc(row.current_sheet)}!${esc(row.current_cell)} · ${num(row.current_thickness_mm)} mm</small>${row.previous_cell ? `<br><small>Earlier UT · ${esc(row.previous_sheet)}!${esc(row.previous_cell)} · ${num(row.previous_thickness_mm)} mm</small>` : ''}${p.code_conflicts?.length ? `<br><small>Conflicting code evidence: ${esc(p.code_conflicts.join('; '))}</small>` : ''}${p.code_correction ? `<br><small>${esc(p.code_correction)}</small>` : ''}</td>
                        <td>${esc(p.linked_inputs?.material ?? row.material)}${p.linked_inputs ? `<br><small>${Object.entries(p.linked_inputs).filter(([key]) => !['S_allow_psi','adopted_rate_mm_year'].includes(key)).map(([key,value]) => esc(`${value} · ${p.references[key]}`)).join('<br>')}</small>` : ''}</td>
                        <td>${cell(p.stress,p.stress_source,'psi')}</td><td>${cell(p.rate,p.rate_source,'mm/year')}${p.cached_rate ? '<br><small>Saved workbook formula result</small>' : ''}</td></tr>`;
                }).join('')}</tbody>
            </table></div>
            <label class="check"><input name="confirmed" type="checkbox" required>
                I checked the component assignments, workbook inputs and any conflicting code evidence for each included location.
            </label>
            <button class="primary" ${rows.some(row => row.workbook_review.eligible) ? '' : 'disabled'}>Confirm inputs and calculate</button>
        </form>`;
    for (const button of $('pipeReviewForm').querySelectorAll('[data-review-pipe]')) {
        button.onclick = () => reviewPipeLocation(rows.find(row => row.current_id === button.dataset.reviewPipe));
    }
    $('pipeReviewForm').onsubmit = async event => {
        event.preventDefault();
        const form = new FormData(event.target);
        const ids = form.getAll('ids');
        if (!ids.length) return message('Include at least one straight-pipe location.', true);
        const saved = await action('review_workbook_pipes', {ids, confirmed:form.has('confirmed')});
        if (saved) {
            $('drawer').hidden = true;
            await action('evaluate', {basis:'assigned'});
        }
    };
};

$('reviewSleeveTees').onclick = () => {
    closeRowEditor();
    $('drawer').hidden = false;
    sleeveEditor(workspace().rows.filter(row => row.geometry === 'sleeve_tee'), $('details'));
};

function sleeveEditor(rows, host) {
    host.innerHTML = `<h2>Review Sleeve-T locations</h2>
        <p>Pressure is withheld pending an approved assessment of the assembled Sleeve-T.</p>
        <ol>
            <li>As-built drawing with carrier, sleeve and branch dimensions, nominal walls, materials, welds and reinforcement.</li>
            <li>Inspection map tying each UT point to the drawing. Include coverage gaps and the evidence supporting any estimated remaining wall.</li>
            <li>Approved assessment with the governing method, minimum wall by location, allowable pressure and temperature, and any operating or reinspection limits.</li>
        </ol>
        ${rows.map(row => {
            const saved = row.sleeve_assessment || {};
            const fields = {
                drawing:'As-built drawing and revision', inspection_map:'Inspection map and revision',
                assessment_reference:'Approved assessment and revision', assessor:'Approving assessor',
                pressure_psi:'Documented pressure (psi)', temperature_F:'Applicable temperature (°F)',
                minimum_wall_mm:'Documented minimum wall at this point (mm)',
            };
            return `<details ${host === $('details') ? '' : 'open'}><summary>${esc(row.location)} · ${esc(row.current_sheet)}!${esc(row.current_cell)} ·
                ${num(row.current_thickness_mm)} mm${row.sleeve_assessment ? ' · Assessment recorded' : ''}</summary>
                <form data-sleeve-record="${esc(row.current_id)}">
                    ${Object.entries(fields).map(([key, label]) => `<label>${esc(label)}
                        <input name="${key}" required value="${esc(saved[key])}"></label>`).join('')}
                    <label class="check"><input type="checkbox" name="confirmed" required>
                        I confirmed that this approved assembly assessment covers this UT point.
                    </label>
                    <button class="primary">Record approved assessment</button>
                </form>
            </details>`;
        }).join('')}`;
    for (const form of host.querySelectorAll('[data-sleeve-record]')) {
        form.onsubmit = async event => {
            event.preventDefault();
            const data = new FormData(form);
            const confirmed = data.has('confirmed');
            data.delete('confirmed');
            const saved = await action('record_sleeve_assessment', {
                id:form.dataset.sleeveRecord, values:Object.fromEntries(data), confirmed,
            });
            if (saved && host === $('details')) $('reviewSleeveTees').onclick();
        };
    }
}

function fittingWorkbookEvidence(row) {
    const review = row.fitting_workbook_review || {};
    const source = record => [record.sheet, record.cell].filter(Boolean).join('!');
    const reading = prefix => {
        const previous = prefix === 'previous';
        const date = review.dates?.[prefix];
        const recordedDate = previous ? row.previous_inspection_date : row.inspection_date;
        return [row[prefix + '_thickness_mm'], 'mm',
            date && recordedDate?.length === 7 ? `${date.date} (workbook, ${source(date)})` : recordedDate,
            source({sheet: row[prefix + '_sheet'], cell: row[prefix + '_cell']})].filter(Boolean).join(' · ');
    };
    const progress = row.fitting_progress || {};
    const calculations = [
        ['Straight-pipe pressure wall for screening (mm)', progress.straight_pipe_screen?.pressure_wall_mm],
        ['Straight-pipe required wall for screening (mm)', progress.straight_pipe_screen?.required_wall_mm],
        ['Quality factor E used for screening', progress.straight_pipe_screen?.quality_factor],
        ['Observed wall loss (mm)', progress.wall_loss_mm],
        ['Observed corrosion rate (mm/year)', progress.observed_rate_mm_year],
        ['Projected physical wall (mm)', progress.projected_wall_mm],
        ['Corrosion rate used (mm/year)', progress.used_rate_mm_year],
        ['Planning projection horizon (years)', progress.planning_projection_only ? progress.projection_years : null],
        ['Draft next UT interval (years)', progress.next_interval_years],
        ['Remaining life (years)', row.remaining_life_years ?? progress.remaining_life_years],
        ['Local bend pressure candidate at measured wall (psi)', progress.bend_pressure_psi],
        ['Qualified fitting pressure at measured wall (psi)', progress.qualified_current_pressure_psi],
        ['Forecast pressure candidate at next UT (psi)', progress.bend_forecast_pressure_psi ?? progress.qualified_forecast_pressure_psi],
        ['Qualified fitting pressure at projected wall (psi)', row.fitting_check?.qualified_pressure_psi],
    ];
    const labels = {
        fitting_pressure_psi: 'Workbook design pressure (psi)', fitting_minimum_mm: 'Historical required wall',
        fitting_interval_years: 'Historical interval', adopted_rate_mm_year: 'Historical selected rate',
        material: 'Material', nps: 'Nominal pipe size', schedule: 'Schedule',
        D_outside_in: 'Outside diameter (in)', nominal_thickness_mm: 'Nominal wall (mm)',
        S_allow_psi: 'Allowable stress', structural_minimum_mm: 'Structural minimum',
        pressure_thickness_mm: 'Pressure thickness',
    };
    return `<div class="fitting-workbook-evidence">
        <dl><dt>Current UT</dt><dd>${esc(reading('current'))}</dd>
        <dt>Previous UT</dt><dd>${row.previous_id ? esc(reading('previous')) : 'Match previous UT'}</dd>
        ${calculations.filter(([, value]) => value != null).map(([label, value]) =>
            `<dt>${esc(label)}</dt><dd>${num(value)}</dd>`).join('')}
        ${Object.entries(review.inputs || {}).map(([key, item]) =>
            `<dt>${esc(labels[key])}</dt><dd>${esc(item.value)} ${esc(item.unit)} · ${esc(source(item))}</dd>`).join('')}</dl>
        ${review.conflict ? '<p><strong>Conflicting workbook construction codes</strong></p>' : ''}
        ${(review.codes || []).map(item => `<p>${esc(item.code)} · ${esc(source(item))}${item.original_code ? ` (workbook says ${esc(item.original_code)}; owner corrected)` : ''}</p>`).join('')}
        ${[...(progress.missing || []), ...(row.fitting_check?.qualified_pressure_psi ? [] : progress.pressure_missing || [])].map(issue =>
            `<div>${esc(issue)}</div>`).join('')}
        <button type="button" data-code="${esc(row.current_id)}">Enter calculation inputs</button>
        <button type="button" data-detail="${esc(row.id)}">Review UT match and dates</button>
    </div>`;
}

$('reviewFittings').onclick = () => {
    const rows = (workspace()?.rows || []).filter(row =>
        (row.fitting_workbook_review || ['elbow','tee','reducer'].includes(row.geometry)) &&
        (!selected.size || selected.has(row.current_id)));
    if (!rows.length) return message('No fittings in the current selection.', true);
    $('drawer').hidden = false;
    $('details').innerHTML = `<h2>Fitting workbook data</h2>
        <button type="button" id="startFittingRatingCheck">Run a fitting rating check</button>
        ${rows.map(row => `<details><summary>${esc(row.location)} · ${esc(row.geometry)} ·
            ${esc([row.nps && 'NPS ' + row.nps, row.schedule && 'Sch ' + row.schedule, row.material].filter(Boolean).join(' · '))}
            </summary>${fittingWorkbookEvidence(row)}</details>`).join('')}`;
    $('startFittingRatingCheck').onclick = () => fittingRatingEditor(rows);
    bindFittingEvidenceActions($('details'));
};

function bindFittingEvidenceActions(container) {
    for (const button of container.querySelectorAll('[data-code]')) {
        button.onclick = () => codeEditor(button.dataset.code);
    }
    for (const button of container.querySelectorAll('[data-detail]')) {
        button.onclick = () => detail(button.dataset.detail);
    }
}

function fittingRatingEditor(rows) {
    const input = (key, label, value, type = 'number') =>
        `<input name="${key}" aria-label="${label}" type="${type}" value="${esc(value)}"
            ${type === 'number' ? 'min="0" step="any"' : ''}>`;
    $('drawer').hidden = false;
    $('details').innerHTML = `<h2>Fitting rating check</h2>
        <p>Enter the approved pressure and minimum wall from the fitting assessment. For an elbow with a reviewed bend design basis, you can calculate the local minimum using the bend inputs below.</p>
        <form id="fittingReviewForm"><div class="table-scroll"><table>
            <thead><tr><th>Location</th><th>Approved pressure (psi)</th><th>Minimum wall (mm)</th><th>Interval (yr)</th><th>Adopted CR (mm/yr)</th><th>Assessment reference and fitting inputs</th></tr></thead>
            <tbody>${rows.map(row => {
                const o = {...row.input_trace?.overrides, ...row.qualification_prefill};
                const label = `${row.location} · ${row.fitting_workbook_review?.geometry || row.geometry}`;
                const proposed = key => o[key] ?? row.fitting_workbook_review?.inputs[key]?.value;
                const evidence = fittingWorkbookEvidence(row);
                let reason = '';
                if (!row.previous_id) reason = 'Match previous UT';
                else if (!['FITTING_REVIEW_REQUIRED','FITTING_CHECK_AVAILABLE'].includes(row.routing?.status)) reason = 'Confirm B31.3-2024 sheet basis';

                return `<tr ${reason ? '' : `data-fitting-id="${esc(row.current_id)}"`}><td>${esc(label)}${evidence}${reason ? `<p>${esc(reason)}</p>` : ''}
                    <label><input type="checkbox" name="include" ${reason ? 'disabled' : rows.length === 1 ? 'checked' : ''}>Include</label></td>
                    <td>${input('fitting_pressure_psi','Approved fitting pressure (psi)',o.fitting_pressure_psi)}</td>
                    <td>${input('fitting_minimum_mm','Approved minimum wall (mm)',o.fitting_minimum_basis === 'bend' ? '' : o.fitting_minimum_mm)}</td>
                    <td>${input('fitting_interval_years','Projection interval',proposed('fitting_interval_years'))}</td>
                    <td>${input('adopted_rate_mm_year','Adopted corrosion rate',proposed('adopted_rate_mm_year') ?? row.profile?.fields?.adopted_rate_mm_year?.value)}</td>
                    <td>${input('fitting_reference','Fitting assessment reference',o.fitting_reference,'text')}
                    ${row.geometry === 'elbow' ? `<details><summary>B31.3 bend location calculation</summary>
                    ${input('bend_tag','Physical bend tag shared by all six positions',o.bend_tag,'text')}
                    ${input('bend_position','Position (intrados, extrados, sidewall_left, sidewall_right, tangent_start, tangent_end)',o.bend_position,'text')}
                    ${input('bend_design_reference','Bend design basis record',o.bend_design_reference,'text')}
                    ${input('bend_radius_in','Centerline bend radius (in)',o.bend_radius_in)}
                    ${input('allowance_mm','Applicable remaining allowance (mm)',o.allowance_mm)}
                    ${input('E_quality','Quality factor E',o.E_quality)}
                    ${input('W_reduction','Weld strength reduction W',o.W_reduction)}
                    ${input('Y_coefficient','Coefficient Y',o.Y_coefficient)}
                    <small>Use only for reviewed §304.2.1 applicability. Diameter and stress come from the location’s code inputs.</small>
                    </details>` : `<details ${row.qualification_prefill ? 'open' : ''}><summary>Qualified pressure and wall schedule</summary>
                    ${row.qualification_prefill ? '<small>Prefilled from a reviewed qualification at this UT location. Confirm the fitting tag and current inspection inputs.</small>' : ''}
                    ${input('qualification_tag','Physical fitting tag',o.qualification_tag,'text')}
                    ${input('qualification_reference','Approved qualification and controlling UT coverage record',o.qualification_reference,'text')}
                    ${input('qualification_temperature_F','Qualification temperature (°F)',o.qualification_temperature_F)}
                    <label>Approved minimum wall (mm), pressure (psi)<textarea name="qualification_points" rows="3">${esc(o.qualification_points||'')}</textarea></label>
                    <small>Enter one approved pair per line, in ascending order. Use a schedule qualified for this fitting and its governing UT location.</small>
                    </details>`}</td></tr>`;
            }).join('')}</tbody></table></div>
            <label class="check"><input type="checkbox" name="confirmed" required>
                I confirmed the fitting assessments, UT coverage, rates and intervals for the included locations.</label>
            <button class="primary" ${rows.some(row => row.previous_id && ['FITTING_REVIEW_REQUIRED', 'FITTING_CHECK_AVAILABLE'].includes(row.routing?.status)) ? '' : 'disabled'}>Confirm fittings and calculate</button>
        </form>`;
    const form = $('fittingReviewForm');
    bindFittingEvidenceActions(form);
    for (const tr of form.querySelectorAll('[data-fitting-id]')) {
        const row = rows.find(item => item.current_id === tr.dataset.fittingId);
        const panel = document.createElement('div');
        panel.className = 'live-assessment fitting-preview';
        panel.setAttribute('aria-live', 'polite');
        tr.lastElementChild.append(panel);
        const update = liveAssessment(panel, row, () => ({values: {
            ...Object.fromEntries([...tr.querySelectorAll('input:not([name="include"]), textarea')]
                .map(control => [control.name, control.value])),
            fitting_geometry: row.geometry, reviewed: 'yes',
        }}));
        tr.addEventListener('input', update);
        if (row.fitting_check || row.qualification_prefill) update();
    }
    form.oninput = event => {
        const tr = event.target.closest('[data-fitting-id]');
        if (tr && event.target.name !== 'include') tr.querySelector('[name="include"]').checked = true;
    };
    form.onsubmit = async event => {
        event.preventDefault();
        const entries = {};
        for (const tr of form.querySelectorAll('[data-fitting-id]')) {
            if (!tr.querySelector('[name="include"]').checked) continue;
            entries[tr.dataset.fittingId] = Object.fromEntries([...tr.querySelectorAll('input:not([name="include"]), textarea')]
                .map(control => [control.name, control.value]));
        }
        const saved = await action('review_fittings', {entries, confirmed:form.elements.confirmed.checked});
        if (saved) {
            $('drawer').hidden = true;
            await action('evaluate', {basis:'assigned'});
        }
    };
}

function bindReferenceSelectors(form, row) {
    const material = form.querySelector('#referenceMaterial');
    const temperature = form.querySelector('#referenceTemperature');
    const preview = form.querySelector('#referencePreview');
    const field = key => form.elements.namedItem(key);
    const get = key => field(key)?.value || '';
    const stress = row.profile?.fields?.S_allow_psi;
    const workbookStress = stress?.source_record || (stress?.kind === 'literal' ? stress : null);
    const useStress = document.createElement('button');
    useStress.type = 'button';
    useStress.textContent = `Use reviewed workbook stress (${num(workbookStress?.value)} psi)`;
    field('S_allow_psi').closest('label').after(useStress);
    useStress.onclick = () => {
        field('S_allow_psi').value = workbookStress.value;
        field('material_reference').value = [row.profile.sheet, workbookStress.cell].filter(Boolean).join('!');
        refresh();
    };
    let generation = 0;

    function availableRows(edition) {
        const geometry = get('geometry');
        const product = get('code_family') === 'ASME VIII-1'
            ? (['shell','cylindrical_shell','ellipsoidal_head_2to1','standard_torispherical_head','nozzle'].includes(geometry)
                ? get('product_form') || 'plate' : '')
            : geometry === 'straight_pipe' ? 'pipe'
            : ['elbow','tee','reducer','branch'].includes(geometry) ? 'fitting' : '';
        return state.material_stresses.filter(row => row.code_family === get('code_family') &&
            row.code_edition === edition && row.product_form === product);
    }

    function showMethodFields() {
        const code = get('code_family');
        const geometry = get('geometry');
        const straight = geometry === 'straight_pipe';
        const vessel = code === 'ASME VIII-1' && ['shell','cylindrical_shell','ellipsoidal_head_2to1'].includes(geometry);
        const vesselNozzle = code === 'ASME VIII-1' && geometry === 'nozzle';
        const vesselMaterial = vessel || vesselNozzle;
        const gas = straight && code === 'ASME B31.8';
        const liquid = straight && code === 'ASME B31.4';
        const process = straight && code === 'ASME B31.3';
        const processFitting = code === 'ASME B31.3' && ['elbow','tee','reducer','branch'].includes(geometry);
        const simplified = process && get('pipe_method') !== 'code';
        const supported = vessel || gas || liquid || process;
        const fields = new Set();
        const include = (condition, keys) => {
            if (condition) for (const key of keys.split(' ')) fields.add(key);
        };
        include(supported, 'material P_psi structural_minimum_mm adopted_rate_mm_year');
        include(supported && row.previous_id && Number(row.current_thickness_mm) > Number(row.previous_thickness_mm), 'allow_increase review_note');
        include(processFitting, 'material temperature_F P_psi structural_minimum_mm nominal_thickness_mm adopted_rate_mm_year selected_interval_years review_note');
        include(processFitting, 'required_thickness_mm fitting_life_reference');
        include(processFitting && ['tee','reducer'].includes(geometry), 'qualification_tag qualification_reference qualification_temperature_F qualification_points');
        include(processFitting && geometry === 'elbow', 'bend_radius_in bend_position allowance_mm bend_design_reference E_quality W_reduction Y_coefficient');
        const policy = row.input_trace?.interval_policy;
        const workbookPolicy = (policy?.reference && !policy.reference.startsWith('API 570')) ||
            (policy?.interval_fraction_reference?.includes('!') && policy?.interval_cap_years_reference?.includes('!'));
        const api570Applies = process && !simplified && ['process_piping','production_flowline'].includes(get('code_asset_type'));
        include(supported && !simplified && !workbookPolicy &&
            !(api570Applies && get('api570_ut_class')), 'interval_fraction interval_cap_years');
        include(api570Applies && !workbookPolicy, 'api570_ut_class');
        include(gas || liquid || process || processFitting, 'D_outside_in');
        include(process, 'pipe_method');
        include(simplified, 'nominal_thickness_mm');
        include(process && !simplified, 'selected_interval_years allowance_mm');
        include(process && !simplified, 'E_quality W_reduction Y_coefficient');
        include(vesselMaterial || gas, 'product_form');
        include(vesselNozzle, 'material');
        include(vesselMaterial && get('product_form') === 'forging', 'material_condition_reference');
        include(vesselMaterial && get('product_form') === 'forging' && /182.*F316/i.test(get('material')), 'material_thickness_mm');
        include(process || vesselMaterial || gas, 'temperature_F');
        include(process || vesselMaterial || processFitting, 'S_allow_psi');
        include(supported || processFitting || vesselNozzle, 'material_reference');
        include(vessel, 'D_inside_in E_joint');
        include(gas || liquid, 'SMYS_psi E_weld');
        include(gas, 'gas_basic_class F_class T_temp');
        include(liquid, 'F_design');
        for (const control of form.querySelectorAll('#methodFields [name]')) {
            control.disabled = !fields.has(control.name);
            control.closest('label').hidden = control.disabled;
        }
        useStress.hidden = !fields.has('S_allow_psi') || !(Number(workbookStress?.value) > 0)
            || get('code_family') !== row.code_family;
        const lookup = supported || processFitting || vesselNozzle;
        material.closest('label').hidden = !lookup;
        temperature.closest('label').hidden = !(process || processFitting || vesselMaterial || gas);
        preview.hidden = !lookup;
        form.querySelector('#methodHint').textContent = supported ? '' : code === 'API 650'
            ? 'Use Tank assessments for tank inputs and calculations.'
            : 'Choose the code and a supported component geometry to see its inputs.';
    }

    async function refresh() {
        showMethodFields();
        const current = ++generation;
        const edition = showEditionDefault(form);
        const rows = availableRows(edition);
        const gas = get('code_family') === 'ASME B31.8' && edition === '2025' &&
            get('geometry') === 'straight_pipe';
        const materials = [...new Set(rows.map(row => row.material))];
        if (gas) materials.push(...state.gas_pipe_grades.map(grade => 'API 5L ' + grade));
        const liquid = get('code_family') === 'ASME B31.4' && edition === '2025' &&
            get('geometry') === 'straight_pipe';
        if (liquid) materials.push(...state.liquid_pipe_grades);
        const detected = row.material || row.fitting_workbook_review?.inputs?.material?.value;
        if (detected && !materials.includes(detected)) materials.unshift(detected);
        const workbookGrade = row.workbook_review?.detected_material;
        if (workbookGrade && !materials.includes(workbookGrade)) materials.push(workbookGrade);
        options(material.id, materials.map(value => [value, value]), get('material'),
            materials.length ? 'Choose a grade' : 'No library grades for this selection');
        material.disabled ||= !materials.length;
        const points = rows.filter(row => row.material_token === get('material').toUpperCase().replace(/[^A-Z0-9]/g, '').replace(/^ASTM/, '').replace(/GRADE|GR/g, '')).map(row => [
            row.temperature_F, row.temperature_F + ' °F']).filter(([value], index, entries) => entries.findIndex(([point]) => point === value) === index);
        if (gas) points.push(...[250,300,350,400,450].map(value => [String(value), value + ' °F']));
        points.sort(([a], [b]) => Number(a) - Number(b));
        if (!get('temperature_F') && points.length && !field('temperature_F').disabled) {
            field('temperature_F').value = points[0][0];
        }
        options(temperature.id, points, get('temperature_F'), points.length ? 'Choose a temperature' : 'Enter temperature below');
        temperature.disabled = !points.length;
        if (preview.hidden) return;
        preview.textContent = 'Checking reference values…';
        try {
            const response = await fetch('/api/workspace/reference_preview', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({values:{...Object.fromEntries(new FormData(form)), code_edition:edition}}),
            });
            const result = await response.json();
            if (!response.ok) throw Error(result.error || 'Reference lookup failed');
            if (current !== generation) return;
            for (const key of ['S_allow_psi', 'E_quality', 'W_reduction', 'Y_coefficient']) field(key).placeholder = '';
            for (const entry of result.entries) {
                if (entry.key) field(entry.key).placeholder = entry.value + ' · library';
            }
            preview.innerHTML = result.entries.map(entry =>
                `<div><strong>${esc(entry.label)}: ${esc(entry.value)}</strong> <small>${esc(entry.reference)} ${esc((entry.notes||[]).join(' '))}</small></div>`).join('')
                || 'No automatic value for this selection. Enter a reviewed value if required.';
        } catch (error) {
            if (current === generation) preview.textContent = error.message;
        }
    }
    function clearMaterialProperties() {
        for (const key of ['S_allow_psi','SMYS_psi','material_reference','E_quality','W_reduction','Y_coefficient']) {
            field(key).value = '';
        }
    }

    field('code_edition').addEventListener('input', () => {
        clearMaterialProperties();
        refresh();
    });
    form.addEventListener('change', event => {
        if (event.target === field('code_family')) field('code_edition').value = '';
        if (event.target === field('gas_basic_class') && get('gas_basic_class') !== 'manual') field('F_class').value = '';
        if (event.target === material && material.value) {
            field('material').value = material.value;
            if (get('code_family') === 'ASME VIII-1' && !get('product_form')) field('product_form').value = 'plate';
        }
        if (event.target === temperature && temperature.value) field('temperature_F').value = temperature.value;
        if (['code_family','geometry','product_form','material','temperature_F','material_thickness_mm','material_condition_reference'].includes(event.target.name) ||
            event.target === material || event.target === temperature) {
            clearMaterialProperties();
        }
        refresh();
    });
    refresh();
}
function identityInputs(r){const i=r.match_identity||{},meta=[i.section||r.segment,i.joint?`Joint ${i.joint}`:'',i.band?`Band ${i.band}`:'',i.size?`NPS ${i.size}`:''].filter(Boolean).join(' · ');return `<div class="identity-summary"><strong>${esc(r.location||'Unassigned location')}</strong><small>${esc(meta||'Location details unavailable')}</small></div><div class="identity-actions"><details class="identity-editor"><summary>Edit match</summary><div class="identity-fields">${['section','joint','band','size'].map(k=>`<label class="identity-field">${esc(k)}<input data-identity="${k}" data-row="${esc(r.current_id)}" value="${esc(i[k]||'')}" aria-label="Matching ${k} for ${esc(r.location)}"></label>`).join('')}</div><button data-save-identity="${esc(r.current_id)}">Save match</button><small class="match-warning">${esc((r.match_flags||[]).join('; '))}</small></details><button class="detail-action" data-code="${esc(r.current_id)}">Code basis · ${esc(codeBasisStatus(r))}</button><button class="detail-action" data-detail="${esc(r.id)}">Calculation details</button></div>`;}
function componentInput(r){const current=r.geometry||'unknown';return `<select data-component="${esc(r.current_id)}" aria-label="Component type for ${esc(r.location)}">${[...new Set(['unknown','straight_pipe','elbow','tee','reducer','fitting',current])].map(v=>`<option value="${v}" ${v===current?'selected':''}>${v.replaceAll('_',' ')}</option>`).join('')}</select>`;}
function previousLabel(c){return `${c.identity.joint} / ${c.identity.band} / NPS ${c.identity.size||'?'} · ${c.date} · ${c.value} mm · ${c.cell}`;}
function previousInput(r){const c=(workspace()?.previous_choices_by_section?.[r.previous_section]||[]).find(x=>x.id===r.previous_id);return `<select data-previous="${esc(r.current_id)}" data-previous-section="${esc(r.previous_section||'')}" aria-label="Previous reading for ${esc(r.location)}">${r.previous_id?`<option value="${esc(r.previous_id)}" selected>${esc(previousLabel(c||{identity:{joint:'',band:''},date:'',value:'',cell:''}))}</option>`:'<option value="">Choose previous UT…</option>'}</select>`;}
function rowHtml(r, resultRow = r){
const fitting = resultRow.fitting_progress;
const screen = fitting?.straight_pipe_screen?.assessment ? fitting.straight_pipe_screen : null;
const c=r.row7||{},fields=r.profile?.fields||{},i=r.input_trace?.inputs||{
pd_psi:fields.P_psi?.value,od_in:fields.D_outside_in?.value,nominal_mm:fields.nominal_thickness_mm?.value,
structural_mm:r.input_trace?.overrides?.structural_minimum_mm,selected_cr:r.input_trace?.overrides?.adopted_rate_mm_year},dims=state.dimensions.filter(d=>d.family==='ferritic'&&!d.issues.length),result=c.result?`DRAFT / NOT VALIDATED · ${c.result}`:screen?.assessment ? 'Draft straight-pipe screening' : resultRow.mawp_MPa != null || resultRow.forecast_mawp_MPa != null ? 'Draft pressure available' : r.reviewed ? 'Inputs needed' : 'Review inputs',resultClass='review';
const forecast = resultRow.forecast_mawp_MPa == null ? null : Number(resultRow.forecast_mawp_MPa) / 0.006894757293;
const currentPressure = screen?.pressure_psi ?? fitting?.bend_pressure_psi ?? fitting?.qualified_current_pressure_psi ??
    (resultRow.outputs?.trace?.mawp_MPa?.horizon_basis === 'current_measurement' && resultRow.mawp_MPa != null
        ? Number(resultRow.mawp_MPa) / 0.006894757293 : null);
const projectedPressure = screen?.forecast_pressure_psi ?? fitting?.bend_forecast_pressure_psi ??
    fitting?.qualified_forecast_pressure_psi ?? c.mawp_psi ?? forecast;
const life = screen?.remaining_life_years ?? c.remaining_life ?? resultRow.remaining_life_years;
const due = screen?.due_date || c.next_inspection || resultRow.due_date;
const factors = r.input_trace?.normalized_design || {};
const b313Factors = r.code_family === 'ASME B31.3' ? [
    ['E', screen?.quality_factor ?? factors.E_quality?.value ?? r.input_trace?.overrides?.E_quality],
    ['W', screen?.weld_reduction_factor ?? factors.W_reduction?.value ?? r.input_trace?.overrides?.W_reduction],
    ['Y', screen?.y_coefficient ?? factors.Y_coefficient?.value ?? r.input_trace?.overrides?.Y_coefficient],
].filter(([, value]) => value != null).map(([label, value]) => label + ': ' + num(value)) : [];
const rowResult = `<span class="result-badge ${resultClass}">${esc(result)}</span>
    ${rowActions(r, resultRow, screen)}`;
return `<tr data-row-id="${esc(r.current_id)}"><td class="select-cell">${r.current_id?`<input type="checkbox" data-select="${esc(r.current_id)}" ${selected.has(r.current_id)?'checked':''} aria-label="Select ${esc(r.location)}">`:''}</td><td class="identity-cell">${identityInputs(r)}</td><td class="pinned-results"><div class="result-metrics">
<span>${wholePressure(projectedPressure ?? currentPressure)}${projectedPressure != null || currentPressure != null ? `<small>${projectedPressure != null ? 'Forecast' : 'Current'}${screen ? ' · screening' : ''}</small>` : ''}</span>
<span>${num(life, 1)}</span><span>${esc(due || '—')}</span></div></td>
<td class="result-cell">${rowResult}</td><td>${componentInput(r)}</td><td class="reading-cell"><div class="ut-reading"><small class="ut-date">${esc(r.previous_inspection_date||'Date missing')}</small>${reading(r.previous_id,r.previous_thickness_mm,'Previous')}</div><div class="previous-match">${previousInput(r)}</div></td><td class="reading-cell"><div class="ut-reading"><small class="ut-date">${esc(r.inspection_date||'Date missing')}</small>${reading(r.current_id,r.current_thickness_mm,'Current')}</div></td><td class="material-cell">${rowSelect(r,'material',r.material,materialGrades([r]))}<small class="allowable-stress">S: ${num(c.s_psi||r.S_allow_psi)}</small>${b313Factors.length ? `<small>${b313Factors.join(' · ')}</small>` : ''}</td><td class="size-cell"><div class="size-controls">${rowSelect(r,'nps',r.nps,dims.map(d=>d.nps))}${rowSelect(r,'schedule',r.schedule,dims.filter(d=>d.nps===r.nps).map(d=>d.schedule))}</div></td><td class="advanced-column">${edit(r,'P_psi',i.pd_psi)}</td><td class="advanced-column">${edit(r,'D_outside_in',i.od_in)}</td><td class="advanced-column">${edit(r,'nominal_thickness_mm',i.nominal_mm)}</td><td class="advanced-column">${edit(r,'structural_minimum_mm',i.structural_mm)}</td><td class="advanced-column">${edit(r,'adopted_rate_mm_year',i.selected_cr)}</td> ${[
    [screen?.pressure_wall_mm ?? c.pressure_mm ?? resultRow.pressure_thickness_mm, true, value => num(value, 1)],
    [screen?.required_wall_mm ?? c.required_mm ?? resultRow.required_thickness_mm, false, value => num(value, 1)],
    [c.calculated_cr ?? resultRow.apparent_rate_mm_year, false, rateLabel],
    [screen?.rate_mm_year ?? c.cr_used ?? resultRow.adopted_rate_mm_year, true, rateLabel],
    [screen?.interval_years ?? c.interval ?? resultRow.inspection_interval_years, true, value => num(value, 1)],
    [screen?.pressure_trace?.net_thickness_mm ?? c.mawp_thickness_mm ?? resultRow.outputs?.trace?.forecast_mawp_MPa?.net_thickness_mm, true, value => num(value, 1)],
].map(([value, advanced, format]) => `<td class="${advanced ? 'advanced-column' : ''}">${format(value)}</td>`).join('')}<td>${wholePressure(currentPressure)}</td></tr>`;}
function syncTableScroll() {
    const rail = $('tableXScroll'), scroller = $('tableScroll'), table = $('locations');
    const headers = [...table.tHead.rows[0].cells];
    const pinned = headers.slice(0, 3).reduce((width, cell) => width + cell.offsetWidth, 0);
    const last = headers.slice(3).findLast(cell => cell.offsetWidth);
    const width = scroller.clientWidth;
    const tableWidth = table.offsetWidth;
    scroller.style.setProperty('--grid-width', width + 'px');
    scroller.style.setProperty('--grid-pinned', pinned + 'px');
    scroller.style.setProperty('--grid-table-width', tableWidth + 'px');
    scroller.style.setProperty('--grid-end-padding', Math.max(0, width - pinned - (last?.offsetWidth || 0)) + 'px');
    rail.firstElementChild.style.width = scroller.scrollWidth + 'px';
    rail.hidden = scroller.scrollWidth <= width + 1;
    syncTableScrollFrom(scroller, rail);
}

function syncTableScrollFrom(source, target) {
    if (Math.abs(target.scrollLeft - source.scrollLeft) > 1) target.scrollLeft = source.scrollLeft;
}
const inputTargets = {
    'Match the previous UT reading': '[data-previous]',
    'Design pressure': '[data-engineering="P_psi"]',
    'Structural minimum thickness': '[data-engineering="structural_minimum_mm"]',
    'Material specification and grade': '[data-engineering="material"]',
    'Outside diameter or NPS and schedule': '[data-engineering="nps"]',
    'Enter a positive selected corrosion rate': '[data-engineering="adopted_rate_mm_year"]',
    'Current UT wall in mm': '[data-reading][aria-label="Current UT"]',
};

function rowActions(row, resultRow, screen) {
    const {missing, notes} = readiness(row);
    if (row.geometry === 'sleeve_tee' && !row.sleeve_assessment) missing.push('Record the approved Sleeve-T assessment');
    const progress = resultRow.fitting_progress;
    const fittingIssues = row.fitting_progress?.screening_missing ?? progress?.screening_missing ?? (progress && !screen
        ? [...(progress.missing || []), ...(progress.pressure_missing || [])] : []);
    const issues = [...new Set([...missing, ...notes, ...fittingIssues])];
    if (resultRow.issues?.includes('ADOPTED_RATE_POLICY_REVIEW'))
        issues.push('Review corrosion rate after an increase in measured wall');
    return issues.map(issue => `<button type="button" class="input-link"
        data-fix-input="${esc(issue)}">${esc(issue)}</button>`).join('');
}

function readiness(row) {
    const profile = row.profile || {};
    const fields = profile.fields || {};
    const overrides = row.input_trace?.overrides || {};
    const value = key => overrides[key] ?? fields[key]?.value ?? row.input_trace?.design_inputs?.[key];
    const missing = [];
    const notes = [];
    const requireValue = (key, label) => {
        const resolved = value(key) ?? row.input_trace?.normalized_design?.[key]?.value;
        if (resolved == null || resolved === '') missing.push(label);
    };
    if (!row.previous_id) missing.push('Match the previous UT reading');
    if ((row.previous_id && !row.previous_inspection_date) || !row.inspection_date) missing.push('Confirm inspection dates');

    const code = row.code_family;
    const vessel = code === 'ASME VIII-1';
    const pipeline = ['ASME B31.4', 'ASME B31.8'].includes(code);
    const pipe = code === 'ASME B31.3';
    const assigned = Boolean(code && row.code_edition && row.code_asset_type &&
        row.code_owner_confirmed && row.code_evidence?.trim());
    if (!assigned) missing.push('Confirm construction code, edition, service and evidence');
    if (row.fitting_workbook_review && row.routing?.status !== 'FITTING_CHECK_AVAILABLE') {
        return {missing, notes, sourced:[], assigned};
    }
    if (!workspace()?.comparison.selected_ut_only && !row.reviewed && row.routing?.status === 'ROUTE_SELECTED') missing.push('Open Code and inputs, verify the source values, and check the review box');

    if ((vessel || pipeline || pipe) && row.routing?.status === 'ROUTE_SELECTED') {
        requireValue('P_psi', 'Design pressure');
        requireValue('structural_minimum_mm', 'Structural minimum thickness');
        requireValue('material', 'Material specification and grade');
        if (vessel) {
            requireValue('D_inside_in', 'Inside diameter');
            requireValue('E_joint', 'Joint efficiency');
            if (!['shell', 'cylindrical_shell', 'ellipsoidal_head_2to1'].includes(row.geometry)) {
                missing.push('Confirm supported vessel geometry');
            }
        } else {
            requireValue('D_outside_in', 'Outside diameter or NPS and schedule');
            if (row.geometry !== 'straight_pipe') missing.push('Confirm supported pipe geometry');
            if (pipe && row.input_trace?.basis !== 'row7') {
                requireValue('E_quality', 'Quality factor');
                requireValue('W_reduction', 'Weld strength reduction factor');
                requireValue('Y_coefficient', 'Y coefficient');
            }
            if (pipeline) {
                if (!row.input_trace?.normalized_design?.F_class?.reference) requireValue(code === 'ASME B31.8' ? 'F_class' : 'F_design', 'Applicable design factor');
                requireValue('E_weld', 'Weld factor');
                if (code === 'ASME B31.8' && row.input_trace?.normalized_design?.T_temp?.reference == null) {
                    if (value('T_temp') == null && value('temperature_F') == null) missing.push('Design temperature or temperature factor');
                    if (row.issues?.includes('B31_8_TEMPERATURE_REFERENCE_UNAVAILABLE')) missing.push('Reviewed temperature factor outside the lookup range');
                }
            }
        }
        const strength = pipeline ? 'SMYS_psi' : 'S_allow_psi';
        if ((value(strength) == null || value(strength) === '') && !(pipeline && row.input_trace?.normalized_design?.SMYS_MPa?.reference)) {
            if (pipeline) missing.push(code === 'ASME B31.8' ? 'API 5L grade and pipe manufacturing type, or reviewed SMYS' : 'Specified minimum yield strength (SMYS)');
            else if (vessel) missing.push('Plate product form and design temperature, or reviewed allowable stress');
            else missing.push('Allowable stress S');
        }
    }
    if (assigned && !vessel && !pipeline && !pipe) notes.push('Use the applicable assessment screen for this code.');
    if (row.routing?.status === 'NOT_ASSESSED' &&
        !(vessel && workspace()?.settings?.basis === 'row7')) {
        notes.push(...(row.routing.issues || []));
    }
    if (row.issues?.includes('PROFILE_CURRENT_CONFLICT')) notes.push('Resolve the conflict between the source record and measured UT.');
    if (row.input_trace?.basis !== 'row7' && row.issues?.includes('INSPECTION_POLICY_REQUIRED')) {
        missing.push(pipe && ['process_piping','production_flowline'].includes(row.code_asset_type)
            ? 'Next inspection only: select the API 570 class if it applies, or enter the interval policy'
            : 'Enter the applicable inspection interval policy');
    }
    if (row.previous_id && Number(row.previous_thickness_mm) <= Number(row.current_thickness_mm) &&
        row.routing?.status === 'ROUTE_SELECTED') {
        const rate = value('adopted_rate_mm_year');
        if (!(Number(rate) > 0)) missing.push('Enter a positive selected corrosion rate');
    }

    const sourced = ['S_allow_psi', 'SMYS_psi', 'D_outside_in', 'nominal_thickness_mm', 'temperature_F']
        .filter(key => fields[key]?.kind === 'reference_derived' && fields[key]?.value != null)
        .map(key => {
            const labels = {S_allow_psi:'Allowable stress (psi)', SMYS_psi:'SMYS (psi)',
                D_outside_in:'OD (in)', nominal_thickness_mm:'Nominal wall (mm)', temperature_F:'Temperature (°F)'};
            return [labels[key], fields[key].value, fields[key].basis];
        });
    const design = row.input_trace?.normalized_design || {};
    if (design.SMYS_MPa?.reference) sourced.push(['SMYS (psi)', design.SMYS_MPa.value_psi, design.SMYS_MPa.reference]);
    if (design.F_class?.reference) sourced.push(['Basic design factor F', design.F_class.value, design.F_class.reference]);
    if (design.T_temp?.reference) sourced.push(['Temperature factor T', design.T_temp.value, design.T_temp.reference]);
    return {missing, notes, sourced, assigned};
}

function codeReviewCell(row, assigned, sourced) {
    const code = [row.code_family, row.code_edition].filter(Boolean).join(' · ');
    const status = !code ? 'Choose a construction code'
        : !assigned ? 'Detected code · confirm basis'
        : row.routing?.status === 'ROUTE_SELECTED' ? 'Code assigned · calculation route available'
        : row.routing?.status === 'FITTING_REVIEW_REQUIRED' ? 'Fitting · rating check optional'
        : row.routing?.status === 'FITTING_CHECK_AVAILABLE' ? 'Fitting · documented pressure check available'
        : 'Code assigned · no calculation route for this component';
    const basis = code ? `<strong>${esc(code)}</strong>` : '';
    const policy = row.input_trace?.interval_policy;
    const policySource = policy?.reference || policy?.interval_cap_years_reference;
    const intervalText = policySource && policy?.fraction != null && policy?.cap_years != null
        ? `<div>UT interval: ${num(100 * Number(policy.fraction))}% of remaining life, capped at ${num(policy.cap_years)} years <small>${esc(policySource)}</small></div>`
        : '';
    const fitting = row.fitting_workbook_review;
    const fittingFacts = fitting ? [row.geometry, row.nps && 'NPS ' + row.nps,
        row.schedule && 'Sch ' + row.schedule,
        row.material || fitting.inputs?.material?.value,
        row.nominal_thickness_mm && num(row.nominal_thickness_mm) + ' mm nominal wall',
    ].filter(Boolean).join(' · ') : '';
    const values = sourced.map(([label,value,source]) =>
        `<div>${esc(label)}: ${num(value)} <small>${esc(source)}</small></div>`).join('');
    const stress = row.profile?.fields?.S_allow_psi;
    const workbookStress = stress?.source_record || (stress?.kind === 'literal' ? stress : null);
    const proposal = workbookStress?.value != null && !sourced.some(([label]) => label === 'Allowable stress (psi)')
        ? `<div>Workbook stress: ${num(workbookStress.value)} psi <small>Source proposal</small></div>` : '';
    const reason = ['NOT_ASSESSED', 'NEEDS_CODE_CONFIRMATION'].includes(row.routing?.status)
        ? row.routing.issues?.[0] : null;
    return `${basis}<div>${esc(reason || status)}</div>${fittingFacts ? `<div>${esc(fittingFacts)}</div>` : ''}${values}${proposal}${intervalText}`;
}

function suggestedGroups(rows) {
    const groups = new Map();
    for (const row of rows) {
        const facts = [row.segment, row.code_family, row.code_edition, row.geometry, row.material];
        if (facts.some(value => !value || value === 'unknown') || !row.code_owner_confirmed) continue;
        const size = [row.nps, row.schedule, row.profile?.fields?.D_outside_in?.value,
            row.profile?.fields?.D_inside_in?.value, row.profile?.product_form,
            row.profile?.fields?.temperature_F?.value, row.profile?.fields?.P_psi?.value,
            row.code_asset_type, row.code_evidence];
        const key = JSON.stringify([...facts,...size]);
        if (!groups.has(key)) groups.set(key, {label:facts.join(' · '), ids:[]});
        groups.get(key).ids.push(row.current_id);
    }
    return [...groups.values()].filter(group => group.ids.length > 1);
}

function renderSuggestedGroups(rows) {
    const groups = suggestedGroups(rows);
    const container = $('suggestedGroups');
    container.innerHTML = groups.length
        ? '<h3>Suggested selections for shared inputs</h3><p>Review the selected rows before applying a change.</p>' +
          groups.map((group, index) => `<button data-suggested-group="${index}">Select ${group.ids.length} · ${esc(group.label)}</button>`).join(' ')
        : '';
    container.onclick = event => {
        const button = event.target.closest('[data-suggested-group]');
        if (!button) return;
        selected = new Set(groups[Number(button.dataset.suggestedGroup)].ids);
        table();
        $('inputScope').scrollIntoView({block:'nearest'});
    };
}

function renderReadiness(rows = visible()) {
    const count = rows.filter(row => {
        const state = readiness(row);
        return state.missing.length || state.notes.length;
    }).length;
    $('readinessCount').textContent = count + ' of ' + rows.length + ' rows need attention';
}

function table(){const rows=visible();
const latest = workspace()?.results?.[0];
const savedRows = new Map(latest && !latest.stale ? latest.rows.map(row => [row.current_id, row]) : []);const selectedRows=rows.filter(row=>selected.has(row.current_id));options('materialGrade',materialGrades(selectedRows.length ? selectedRows : rows).map(grade=>[grade,grade]),$('materialGrade').value,'Keep existing');renderReadiness(rows);$('locations').querySelector('tbody').innerHTML=rows.map(row => rowHtml(row, savedRows.get(row.current_id))).join('');$('selectedCount').textContent=selected.size+' selected';$('rowCount').textContent=rows.length+' of '+(workspace()?.rows.length||0)+' locations';const ids=rows.map(r=>r.current_id).filter(Boolean);$('selectAll').checked=ids.length>0&&ids.every(id=>selected.has(id));$('selectAll').indeterminate=ids.some(id=>selected.has(id))&&!$('selectAll').checked;$('inputScope').textContent=selected.size===1?'Batch inputs · one selected reading':'Batch inputs · '+selected.size+' selected readings';requestAnimationFrame(syncTableScroll);}
function reading(id,value,label){return id?`<input class="reading" type="number" min="0" step="any" data-reading="${esc(id)}" value="${esc(value)}" aria-label="${label} UT">`:'—';}
function dimensions(){if(!state)return;const nps=$('nps').value,schedule=$('schedule').value;const rows=state.dimensions.filter(d=>d.family===$('pipeFamily').value);options('nps',[...new Set(rows.map(d=>d.nps))].map(n=>[n,n+' in']),nps,'Custom / keep existing');options('schedule',rows.filter(d=>d.nps===$('nps').value).map(d=>[d.schedule,d.schedule+(d.issues.length?' · unavailable':'')]),schedule,'Keep existing');const d=dimension();$('dimensions').textContent=d?`${d.od_in} in OD · ${d.nominal_mm} mm nominal${d.issues.length?' · reference discrepancy; choose another entry':''}`:'Select size and schedule, or enter custom dimensions.';}
function dimension(){return state?.dimensions.find(d=>d.family===$('pipeFamily').value&&d.nps===$('nps').value&&d.schedule===$('schedule').value);}
function values(){return Object.fromEntries([...new FormData($('batchForm'))].filter(([,value])=>value!==''));}
function requireSelected(){if(selected.size)return true;message('Select one or more readings first.',true);return false;}
$('showEngineeringColumns').onchange = event => {
    closeRowEditor();
    $('locations').classList.toggle('show-engineering', event.target.checked);
    requestAnimationFrame(syncTableScroll);
};
function closeRowEditor() {
    $('locations').querySelector('.row-editor')?.remove();
}

function openRowEditor(row, button) {
    closeRowEditor();
    $('drawer').hidden = true;
    $('details').replaceChildren();
    const editor = row.parentElement.insertRow(row.sectionRowIndex + 1);
    editor.className = 'row-editor';
    const cell = editor.insertCell();
    cell.colSpan = [...$('locations').tHead.rows[0].cells].filter(header => header.offsetWidth).length;
    cell.innerHTML = '<section class="row-editor-panel" aria-label="Inputs for this location"><button type="button" class="close-row-editor">Close inputs</button><div class="row-editor-content"></div></section>';
    cell.querySelector('button').onclick = () => {
        closeRowEditor();
        button.focus();
    };
    return cell.querySelector('.row-editor-content');
}

$('locations').addEventListener('click', event => {
    const button = event.target.closest('[data-fix-input]');
    if (!button) return;
    const row = button.closest('[data-row-id]');
    const issue = button.dataset.fixInput;
    const target = inputTargets[issue] && row.querySelector(inputTargets[issue]);
    if (target) {
        if (target.closest('.advanced-column')) {
            $('showEngineeringColumns').checked = true;
            $('showEngineeringColumns').dispatchEvent(new Event('change'));
        }
        target.focus({preventScroll:true});
        target.scrollIntoView({block:'nearest', inline:'nearest'});
        return;
    }
    const record = workspace().rows.find(item => item.current_id === row.dataset.rowId);
    const host = openRowEditor(row, button);
    if (issue === 'Confirm inspection dates') {
        const dates = [
            ['previous_date', 'Previous inspection', record.previous_inspection_date],
            ['current_date', 'Current inspection', record.inspection_date],
        ];
        host.innerHTML = `<form><strong>Inspection dates for this comparison</strong>
            ${dates.map(([key, label, value]) => `<label>${label}<input type="date" name="${key}" value="${esc(value)}"></label>`).join('')}
            <button class="primary">Save dates</button></form>`;
        host.firstElementChild.onsubmit = event => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const values = Object.fromEntries(dates.filter(([key, , original]) => data.get(key) && data.get(key) !== original)
                .map(([key]) => [key, data.get(key)]));
            if (Object.keys(values).length) action('dates', values);
        };
    } else if (record.geometry === 'sleeve_tee') {
        sleeveEditor([record], host);
    } else {
        codeEditor(record.current_id, host);
    }
    const fields = {
        'Quality factor': 'E_quality',
        'Weld strength reduction factor': 'W_reduction',
        'Y coefficient': 'Y_coefficient',
        'Confirm construction code, edition, service and evidence': 'code_asset_type',
        'Allowable stress S': 'S_allow_psi',
        'UT position on the bend': 'bend_position',
        'Centerline bend radius': 'bend_radius_in',
        'Remaining wall allowance': 'allowance_mm',
        'Quality factor E': 'E_quality',
        'Design metal temperature for the allowable stress': 'temperature_F',
        'Physical fitting tag': 'qualification_tag',
        'Approved minimum-wall and pressure pairs': 'qualification_points',
        'Approved qualification and controlling UT coverage reference': 'qualification_reference',
        'Qualification temperature matching the design temperature': 'qualification_temperature_F',
        'For remaining life, enter the reviewed required wall and its reference for this exact fitting location.': 'required_thickness_mm',
        'Inside diameter': 'D_inside_in',
        'Joint efficiency': 'E_joint',
        'Enter the applicable inspection interval policy': 'interval_fraction',
        'Next inspection only: select the API 570 class if it applies, or enter the interval policy': 'api570_ut_class',
        'Review corrosion rate after an increase in measured wall': 'allow_increase',
    };
    let control = fields[issue] && host.querySelector(`[name="${fields[issue]}"]`);
    if (issue === 'Allowable stress S') {
        const material = record.material || 'the selected grade';
        const hint = document.createElement('p');
        hint.textContent = `No B31.3 library stress matched ${material} at the entered temperature. Check the grade and temperature, or enter a reviewed S with its reference.`;
        host.prepend(hint);
    }
    if (control) {
        const group = control.closest('details');
        if (group) group.open = true;
    } else {
        control = host.querySelector('form input, form select');
    }
    control?.focus({preventScroll:true});
    control?.scrollIntoView({block:'nearest', inline:'nearest'});
});

function detail(id){const r=workspace().rows.find(r=>r.id===id);if(!r)return;$('drawer').hidden=false;$('details').innerHTML=`<h2>${esc(r.location)}</h2><button id="editRow">Edit this row only</button>${r.current_id&&!r.previous_id?'<button id="pairRow">Use previous UT on same source row</button>':''}<p>Previous: ${esc(r.previous_inspection_date)} · ${esc(r.previous_cell)}<br>Current: ${esc(r.inspection_date)} · ${esc(r.current_cell)}</p><p>CR = (previous − current) / ((current date − previous date) / 365). Use selected CR only when calculated CR ≤ 0.</p><p>Required = MAX(pressure thickness, structural thickness).<br>Life = (current − required) / CR used.<br>Interval = MIN(10, life / 2).<br>t in MAWP = current − 2 × CR used × interval.</p><pre>${esc(JSON.stringify(r.row7||r.issues,null,2))}</pre>`;if($('pairRow'))$('pairRow').onclick=async()=>{await action('pair',{id:r.current_id});$('drawer').hidden=true;};$('editRow').onclick=()=>{selected=new Set([r.current_id]);$('batchForm').reset();const i=r.input_trace?.inputs||{};const fields={material:i.material,P_psi:i.pd_psi,D_outside_in:i.od_in,nominal_thickness_mm:i.nominal_mm,structural_minimum_mm:i.structural_mm,adopted_rate_mm_year:i.selected_cr,segment:r.segment};for(const [key,value] of Object.entries(fields))$('batchForm').elements.namedItem(key).value=value??'';dimensions();$('drawer').hidden=true;document.querySelector('.batch-panel').open=true;table();};}
function results() {
    const w = workspace();
    if (!w) return;
    const result = w.results[0];
    const current = result && !result.stale;
    const savedRows = current ? result.rows.filter(row => row.current_id) : [];
    const ready = savedRows.filter(row => row.pressure_thickness_mm != null || row.mawp_MPa != null ||
        row.remaining_life_years != null || row.fitting_progress?.straight_pipe_screen?.assessment);
    const fittings = savedRows.filter(row => row.fitting_check);
    $('metrics').innerHTML = `<div class="metric">${w.rows.length} locations</div>
        <div class="metric">${ready.length} saved draft calculations</div>
        <div class="metric">${w.rows.length - ready.length} without a saved pressure calculation</div>`;
    $('resultSummary').textContent = current
        ? `${ready.length} of ${savedRows.length} locations have draft pressure or remaining-life results.` +
            (fittings.length ? ` ${fittings.length} additional locations have documented fitting pressure checks.` : '')
        : 'Calculate ready locations to save the current results.';
    $('pipelineProjectLink').href = '/pipeline?' + new URLSearchParams({comparison: cid});
    $('exports').innerHTML = current ? '<button id="reviewCalculations">Review calculations</button>' : '';
    if (current) $('reviewCalculations').onclick = () => navigate('calculations');

}

async function showCalculations() {
    const w = workspace();
    const result = w?.results?.[0];
    const status = $('calculationStatus');
    const table = $('calculationTable');
    const region = $('calculationRegion');
    const download = $('downloadCalculations');
    region.hidden = download.hidden = true;
    table.tHead.replaceChildren();
    table.tBodies[0].replaceChildren();
    $('calculationScope').textContent = w ? `${w.comparison.asset} · ${w.comparison.current_selection[1]}` : '';
    if (!result || result.stale) {
        status.textContent = w ? 'Calculate ready locations in the inspection grid to review current results.' :
            'Open a UT comparison to review its calculations.';
        return;
    }
    status.textContent = 'Loading saved calculations…';
    const query = new URLSearchParams({result: result.id});
    try {
        const snapshot = await actionResponse(await fetch('/workspace/results.json?' + query));
        if (screen !== 'calculations' || workspace()?.results?.[0] !== result) return;
        const format = (value, kind) => {
            if (value == null || value === '') return '—';
            if (typeof value !== 'number') return esc(value);
            if (kind === 'pressure') return num(value, 0);
            if (kind === 'rate') return rateLabel(value);
            if (kind) return num(value, kind === 'years' ? 1 : 2);
            return esc(value);
        };
        table.tHead.innerHTML = '<tr>' + snapshot.columns.map(column =>
            `<th scope="col">${esc(column.label)}</th>`).join('') + '</tr>';
        table.tBodies[0].innerHTML = snapshot.rows.map(row => '<tr>' + row.map((value, index) => {
            const column = snapshot.columns[index];
            const content = format(value, column.format);
            return index === 0 ? `<th scope="row">${content}</th>` :
                `<td class="${column.format ? 'calculation-number' : ''}">${content}</td>`;
        }).join('') + '</tr>').join('');
        status.textContent = `${snapshot.rows.length} locations · Draft / not validated`;
        download.href = '/workspace/results.xlsx?' + query;
        download.hidden = region.hidden = !snapshot.rows.length;
    } catch (error) {
        if (screen === 'calculations' && workspace()?.results?.[0] === result) status.textContent = error.message;
    }
}

document.querySelectorAll('[data-screen]').forEach(button => {
    button.onclick = () => {
        if (button.dataset.screen !== 'workspace' || workspace()) navigate(button.dataset.screen);
    };
});
$('backToInspection').onclick = () => navigate(workspace() ? 'workspace' : 'import');
$('source').onchange = sheets;
$('openSheet').onclick = async () => {
    if (!$('source').value || !$('sheet').value) return message('Choose a workbook and UT sheet.', true);
    const opened = await action('import', {source_id:$('source').value, sheet:$('sheet').value,
        straight_pipe_fitting_screen:$('fittingImportMode').value === 'pipe'});
    if (opened?.comparison_id && !opened.reused) batchCodeEditor();
    else if (opened && !opened.comparison_id) navigate('import');
};
$('upload').onsubmit = async event => {
    event.preventDefault();
    $('busy').hidden = false;
    try {
        const response = await fetch('/workspace/upload', {method:'POST', body:new FormData(event.target)});
        const data = await actionResponse(response);
        await load();
        navigate('import');
        $('source').value = data.source_id;
        sheets();
        $('sheet').focus();
        message(data.message);
    } catch (error) {
        message(error.message, true);
    } finally {
        $('busy').hidden = true;
    }
};
$('comparison').onchange=async()=>{cid=$('comparison').value;selected.clear();try{await load();}catch(e){message(e.message,true);}};
$('changeCampaigns').onclick=()=>{const w=workspace();if(w)action('import',{source_id:w.comparison.current_selection[0],sheet:w.comparison.current_selection[1],previous:$('previousCampaign').value,current:$('currentCampaign').value,straight_pipe_fitting_screen:Boolean(w.comparison.straight_pipe_fitting_screen)});};$('resolveDates').onclick=()=>{const dates=Object.fromEntries([...document.querySelectorAll('[data-campaign-date]')].filter(el=>el.value).map(el=>[el.dataset.campaignDate,el.value]));if(!Object.keys(dates).length)return message('Enter an exact date for at least one inspection.',true);action('dates',{campaign_dates:dates});};
$('search').oninput=table;$('sectionFilter').onchange=table;$('componentFilter').onchange=table;$('selectComponent').onclick=()=>{const type=$('componentFilter').value;if(!type)return message('Choose straight pipes or fittings first.',true);visible().filter(r=>r.current_id).forEach(r=>selected.add(r.current_id));table();};$('selectVisible').onclick=()=>{visible().filter(r=>r.current_id).forEach(r=>selected.add(r.current_id));table();};$('clearSelection').onclick=()=>{selected.clear();table();};$('selectAll').onchange=e=>{visible().filter(r=>r.current_id).forEach(r=>e.target.checked?selected.add(r.current_id):selected.delete(r.current_id));table();};
$('locations').addEventListener('input', event => {
    if (!event.target.dataset.reading) return;
    const element = event.target.closest('tr');
    const row = workspace().rows.find(item => item.current_id === element.dataset.rowId);
    if (!row) return;
    const previous = element.querySelector('[aria-label="Previous UT"]');
    const current = element.querySelector('[aria-label="Current UT"]');
    if (!element.previewAssessment) {
        const panel = document.createElement('div');
        panel.className = 'live-assessment';
        panel.setAttribute('aria-live', 'polite');
        event.target.closest('td').append(panel);
        element.previewAssessment = liveAssessment(panel, row, () => ({
            readings: {previous: previous?.value ?? '', current: current?.value ?? ''},
        }));
    }
    element.previewAssessment();

});
$('locations').onchange=e=>{if(e.target.dataset.identity){action('identity',{id:e.target.dataset.row,values:{[e.target.dataset.identity]:e.target.value}});return;}if(e.target.dataset.previous){if(e.target.value)action('identity',{id:e.target.dataset.previous,previous_id:e.target.value});return;}if(e.target.dataset.component){const type=e.target.value;action('identity',{id:e.target.dataset.component,values:{component:type}});return;}if(e.target.dataset.engineering){inlineEdit(e.target);return;}if(e.target.dataset.select){e.target.checked?selected.add(e.target.dataset.select):selected.delete(e.target.dataset.select);table();}else if(e.target.dataset.reading)action('correct',{id:e.target.dataset.reading,value:e.target.value});};$('locations').onclick=e=>{const save=e.target.closest('[data-save-identity]');if(save){const fields=[...save.closest('tr').querySelectorAll('[data-identity]')];action('identity',{id:save.dataset.saveIdentity,values:Object.fromEntries(fields.map(el=>[el.dataset.identity,el.value]))});return;}const code=e.target.closest('[data-code]');if(code){codeEditor(code.dataset.code);return;}const b=e.target.closest('[data-detail]');if(b)detail(b.dataset.detail);};
$('closeDrawer').onclick=()=>$('drawer').hidden=true;document.onkeydown=e=>{if(e.key==='Escape'){if (!$('drawer').hidden) $('drawer').hidden=true;else closeRowEditor();}};
 $('tableXScroll').addEventListener('scroll',()=>syncTableScrollFrom($('tableXScroll'),$('tableScroll')));$('tableScroll').addEventListener('scroll',()=>syncTableScrollFrom($('tableScroll'),$('tableXScroll')));window.addEventListener('resize',()=>requestAnimationFrame(syncTableScroll));
$('locations').addEventListener('focusin', event => {
    const select = event.target.closest('[data-previous-section]');
    if (!select || select.dataset.loaded) return;
    select.dataset.loaded = 'yes';
    const choices = workspace()?.previous_choices_by_section?.[select.dataset.previousSection] || [];
    select.insertAdjacentHTML('beforeend', choices.filter(choice => choice.id !== select.value)
        .map(choice => `<option value="${esc(choice.id)}">${esc(previousLabel(choice))}</option>`).join(''));
});
$('pipeFamily').onchange=()=>{$('nps').value='';$('schedule').value='';dimensions();};$('nps').onchange=()=>{$('schedule').value='';dimensions();};$('schedule').onchange=()=>{dimensions();const d=dimension();if(d&&!d.issues.length){$('batchForm').elements.D_outside_in.value=d.od_in;$('batchForm').elements.nominal_thickness_mm.value=d.nominal_mm;}};
for(const key of ['D_outside_in','nominal_thickness_mm'])$('batchForm').elements.namedItem(key).oninput=()=>{$('nps').value='';$('schedule').value='';dimensions();};
$('batchForm').onsubmit=e=>{e.preventDefault();if(!requireSelected())return;const payload={ids:[...selected],values:values(),fill_missing:$('fillMissing').checked},d=dimension();if(d)payload.dimension_key=[d.family,d.nps,d.schedule];else if(payload.values.D_outside_in||payload.values.nominal_thickness_mm)Object.assign(payload.values,{nps:'Custom',schedule:'Custom'});action('apply',payload);};$('resetSelected').onclick=()=>{if(requireSelected())action('apply',{ids:[...selected],clear:true});};$('evaluate').onclick=()=>action('evaluate',{basis:'assigned'});$('undo').onclick=()=>action('undo');
load().then(()=>navigate(workspace()?'workspace':'import')).catch(e=>message(e.message,true));

let pendingCleanup=null;
function renderWorkbooks(){
 $('workbookList').innerHTML=state.sources.length?state.sources.map(s=>`<article class="source"><strong>${esc(s.file_name)}</strong><button data-delete-source="${esc(s.source_id)}">Delete workbook</button></article>`).join(''):'<p>No imported workbooks. Choose an Excel file above to begin.</p>';
 $('restoreCleanup').hidden=!state.cleanup_backup_available;
 if(!workspace()){$('locations').querySelector('tbody').innerHTML='';$('metrics').innerHTML='';$('resultSummary').textContent='';$('exports').innerHTML='';}
}
function cleanupDialog(kind,source){
 pendingCleanup={kind,source};const reset=kind==='reset';
 $('cleanupTitle').textContent=reset?'Start a clean project?':kind==='restore'?'Restore the last cleanup?':'Delete '+source.file_name+'?';
 $('cleanupDescription').textContent=reset?'Remove all imported workbooks, readings, inputs and saved evaluations from this project. A recovery backup is saved first. Your original files stay untouched.':kind==='restore'?'Replace the active project with the backup saved before the last delete or reset.':'Remove this imported workbook and its readings, inputs and evaluations. A recovery backup is saved first. Your original file stays untouched.';
 $('resetLabel').hidden=!reset;$('resetConfirmation').value='';$('confirmCleanup').textContent=reset?'Start clean':kind==='restore'?'Restore project':'Delete workbook';$('cleanupDialog').showModal();
}
$('manageWorkbooks').onclick=()=>navigate('import');$('startClean').onclick=()=>cleanupDialog('reset');
$('workbookList').onclick=e=>{const b=e.target.closest('[data-delete-source]');if(b)cleanupDialog('delete',state.sources.find(s=>s.source_id===b.dataset.deleteSource));};
$('restoreCleanup').onclick=()=>cleanupDialog('restore');$('cancelCleanup').onclick=()=>$('cleanupDialog').close();
$('confirmCleanup').onclick=async()=>{const p=pendingCleanup;if(!p)return;if(p.kind==='reset'&&$('resetConfirmation').value!=='RESET')return message('Type RESET to confirm starting clean.',true);$('cleanupDialog').close();await action(p.kind==='reset'?'reset_project':p.kind==='restore'?'restore_cleanup':'delete_source',p.kind==='reset'?{confirmation:'RESET'}:p.kind==='delete'?{source_id:p.source.source_id}:{});};

async function inlineEdit(el){
 const key=el.dataset.engineering,row=workspace().rows.find(r=>r.current_id===el.dataset.row),value=el.value;
 if(!row||value==='')return message('Enter a value; use Reset selected inputs to restore defaults.',true);
 const payload={ids:[row.current_id],values:{[key]:value}};
 if(key==='nps'){
  const d=state.dimensions.find(d=>d.family==='ferritic'&&d.nps===value&&!d.issues.length);
  if(!d)return message('Choose a supported pipe size.',true);
  const compatible=state.dimensions.find(option=>option.family===d.family&&option.nps===value&&option.schedule===row.schedule&&!option.issues.length);
  if(compatible)payload.dimension_key=[compatible.family,compatible.nps,compatible.schedule];
  else Object.assign(payload.values,{D_outside_in:d.od_in,schedule:'Unspecified'});
 }else if(key==='schedule'){
  const d=state.dimensions.find(d=>d.family==='ferritic'&&d.nps===row.nps&&d.schedule===value&&!d.issues.length);
  if(!d)return message('Choose a supported schedule for this NPS.',true);
  payload.dimension_key=[d.family,d.nps,d.schedule];
 }else if(['D_outside_in','nominal_thickness_mm'].includes(key))Object.assign(payload.values,{schedule:'Custom'});
 await action('apply',payload);
}

$('rematch').onclick=()=>action('identity');

$('showSharedInputs').onclick = () => {
    if (!requireSelected()) return;
    const panel = document.querySelector('.batch-panel');
    panel.open = true;
    $('inputScope').focus();
    panel.scrollIntoView({block:'nearest'});
};
document.querySelector('.measurement-grid').addEventListener('toggle', syncTableScroll);
