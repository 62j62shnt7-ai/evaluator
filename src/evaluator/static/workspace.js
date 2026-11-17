'use strict';
const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>v===null||v===undefined||v===''?'—':Number(v).toLocaleString(undefined,{maximumFractionDigits:4});
let state,cid=new URLSearchParams(location.search).get('comparison'),selected=new Set(),screen='import';
const workspace=()=>state?.workspace;
function message(text,error=false){$('message').textContent=text;$('message').hidden=!text;$('message').classList.toggle('error',error);}
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
}
async function load(){const response=await fetch('/api/workspace'+(cid?'?'+new URLSearchParams({comparison:cid}):''));state=await response.json();if(!response.ok)throw Error(state.error);if(workspace()){cid=workspace().comparison.id;history.replaceState(null,'','/?'+new URLSearchParams({comparison:cid}));const valid=new Set(workspace().rows.map(r=>r.current_id));selected=new Set([...selected].filter(id=>valid.has(id)));}render();}
async function refreshRows(ids){if(!ids?.length)return;const response=await fetch('/api/workspace?'+new URLSearchParams({comparison:cid,ids:ids.join(',')}));const data=await response.json();if(!response.ok)throw Error(data.error||'Could not refresh changed readings');state.revision=data.revision;state.workspace.results.forEach(r=>r.stale=true);const changed=new Map(data.workspace.rows.map(r=>[r.current_id,r]));state.workspace.rows=state.workspace.rows.map(r=>changed.get(r.current_id)||r);let redraw=false;for(const row of changed.values()){const current=$('locations').querySelector(`[data-row-id="${CSS.escape(row.current_id)}"]`),isVisible=visible().some(r=>r.current_id===row.current_id);if(current&&isVisible)current.outerHTML=rowHtml(row);else if(current||isVisible)redraw=true;}if(redraw)table();else renderReadiness();requestAnimationFrame(syncTableScroll);results();$('revision').textContent='Revision '+state.revision;}
async function action(name,payload={}){$('busy').hidden=false;try{const response=await fetch('/api/workspace/'+name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({comparison_id:cid,revision:state.revision,...payload})});const data=await response.json();if(!response.ok)throw Error(data.error||'Action failed');if(name==='apply'&&workspace()&&!data.reset_workspace){await refreshRows(data.refresh_ids||payload.ids);message('Saved.');return data;}if(data.reset_workspace){cid=null;selected.clear();$('batchForm').reset();$('drawer').hidden=true;history.replaceState(null,'','/');}if(data.comparison_id){cid=data.comparison_id;selected.clear();}await load();navigate(data.reset_workspace?'import':name==='evaluate'?'results':workspace()?'workspace':'import');message(data.message||'Saved.');return data;}catch(e){message(e.message,true);}finally{$('busy').hidden=true;}}
function sheets(){const source=state.sources.find(s=>s.source_id===$('source').value);options('sheet',(source?.sheets||[]).map(s=>[s,s]),workspace()?.comparison.current_selection[1]);}
function render(){const w=workspace();renderWorkbooks();$('revision').textContent='Revision '+state.revision;options('source',state.sources.map(s=>[s.source_id,s.file_name]),w?.comparison.current_selection[0]||$('source').value);sheets();options('comparison',state.comparisons.map(c=>[c.id,c.asset+' · '+c.sheet]),cid);dimensions();for(const button of document.querySelectorAll('[data-screen]'))button.disabled=button.dataset.screen!=='import'&&!w;if(!w)return;$('asset').textContent=w.comparison.asset;$('scope').textContent=w.comparison.current_selection[1];const campaigns=w.campaigns.map(c=>[c.campaign,(c.label||c.campaign)+' · '+c.count+' readings']);options('previousCampaign',campaigns,w.comparison.baseline[2]);options('currentCampaign',campaigns,w.comparison.current_selection[2]);$('campaignDateFields').innerHTML=w.campaigns.filter(c=>!c.campaign.startsWith('auto:')).map(c=>`<label>${esc(c.campaign)} exact date<input type="date" data-campaign-date="${esc(c.campaign)}"></label>`).join('');options('sectionFilter',[...new Set(w.rows.map(r=>r.segment))].map(v=>[v,v]),$('sectionFilter').value,'All sections');table();results();}
function visible(){const q=$('search').value.toLowerCase(),component=$('componentFilter').value;return (workspace()?.rows||[]).filter(r=>{const type=r.match_identity?.component||r.geometry||'unknown';const fits=!component||(component==='straight_pipe'?type==='straight_pipe':type!=='straight_pipe'&&type!=='unknown');return fits&&(!$('sectionFilter').value||r.segment===$('sectionFilter').value)&&[r.location,r.segment,r.material].join(' ').toLowerCase().includes(q);});}
function edit(r,key,value){return `<input class="engineering-input" type="number" min="0" step="any" data-engineering="${key}" data-row="${esc(r.current_id)}" value="${esc(value??'')}" aria-label="${key} for ${esc(r.location)}">`;}
function rowSelect(r,key,value,items){return `<select data-engineering="${key}" data-row="${esc(r.current_id)}" aria-label="${key} for ${esc(r.location)}">${[...new Set([value||'',...items])].map(v=>`<option value="${esc(v)}" ${String(v)===String(value??'')?'selected':''}>${esc(v||'Choose…')}</option>`).join('')}</select>`;}
function codeEditor(id){const r=workspace().rows.find(x=>x.current_id===id);if(!r)return;$('drawer').hidden=false;const codes=['ASME B31.3','ASME B31.4','ASME B31.8','ASME VIII-1','API 650'],assets=['process_piping','liquid_transmission','gas_transmission','production_flowline','pressure_vessel','storage_tank'];$('details').innerHTML=`<h2>Code basis · ${esc(r.location)}</h2><p>Set the construction basis for this component. Code routing only selects an existing draft method; it does not establish MAWP or engineering approval. Flowlines require an explicit service boundary.</p><form id="codeBasisForm" data-row="${esc(id)}"><label>Asset / service boundary<select name="code_asset_type" required><option value="">Choose…</option>${assets.map(v=>`<option value="${v}" ${r.code_asset_type===v?'selected':''}>${v.replaceAll('_',' ')}</option>`).join('')}</select></label><label>Construction code<select name="code_family" required><option value="">Choose…</option>${codes.map(v=>`<option ${r.code_family===v?'selected':''}>${v}</option>`).join('')}</select></label><label>Edition year<input name="code_edition" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" value="${esc(r.code_edition||'')}" placeholder="e.g. 2024" required></label><label class="wide">Code basis evidence<input name="code_evidence" value="${esc(r.code_evidence||'')}" placeholder="Document, line list, drawing or approved basis reference" required></label><label class="check"><input type="checkbox" name="code_owner_confirmed" value="yes" ${r.code_owner_confirmed?'checked':''} required>I confirmed this code’s applicability and boundary for this component.</label><label>Calculation geometry<select name="geometry" required><option value="">Choose…</option>${['straight_pipe','elbow','tee','reducer','branch','nozzle','shell','cylindrical_shell','ellipsoidal_head_2to1','head_unspecified','unknown'].map(v=>`<option value="${v}" ${r.geometry===v?'selected':''}>${v.replaceAll('_',' ')}</option>`).join('')}</select></label><fieldset id="methodFields"><legend>Inputs for this calculation</legend>
<label>Process piping method<select name="pipe_method">
<option value="example">Pipe workflow (E = 1, W = 1, Y = 0.4)</option>
<option value="code" ${r.input_trace?.overrides?.pipe_method==='code'?'selected':''}>B31.3 with entered E, W and Y</option>
</select></label><p id="methodHint" aria-live="polite"></p>
<div class="fields">
<label>Material from code library<select id="referenceMaterial"></select></label>
<label>Reference temperature<select id="referenceTemperature"></select></label>
</div><label>Basic B31.8 pipeline class (only where the basic factor applies)
<select name="gas_basic_class"><option value="manual">Use manual factor</option>
${['1 Division 1','1 Division 2','2','3','4'].map(value=>`<option value="${value}" ${r.input_trace?.overrides?.gas_basic_class===value?'selected':''}>Class ${value}</option>`).join('')}</select></label>
<output id="referencePreview" aria-live="polite"></output>
<label>Material specification and grade<input name="material" value="${esc(r.material||'')}" placeholder="SA-516 Grade 70"></label>
<label>Product form<select name="product_form"><option value="">Choose…</option><option value="plate" ${r.profile?.product_form==='plate'?'selected':''}>Plate</option>${['LFW','HFW','SMLS','SAWL','SAWH','COWL','COWH'].map(form=>`<option value="${form}" ${r.profile?.product_form===form?'selected':''}>${form}</option>`).join('')}</select></label>
${Object.entries({D_outside_in:'Outside diameter (in)',nominal_thickness_mm:'Nominal wall (mm)',adopted_rate_mm_year:'Adopted corrosion rate (mm/year)',temperature_F:'Design metal temperature (°F)',D_inside_in:'Inside diameter (in)',P_psi:'Design pressure (psi)',E_joint:'Joint efficiency',structural_minimum_mm:'Structural minimum (mm)',E_quality:'Pipe quality factor',W_reduction:'Weld strength reduction factor',Y_coefficient:'Y coefficient',F_class:'Gas pipeline class factor',F_design:'Liquid pipeline design factor',E_weld:'Pipeline weld factor',T_temp:'Gas pipeline temperature factor',SMYS_psi:'Pipeline SMYS (psi)',interval_fraction:'Inspection interval fraction of remaining life',interval_cap_years:'Inspection interval cap (years)'}).map(([key,label])=>`<label>${label}<input type="number" step="any" name="${key}" value="${esc(r.input_trace?.overrides?.[key]??r.profile?.fields?.[key]?.value??'')}"></label>`).join('')}
<label>Manual allowable stress (psi), if needed<input type="number" step="any" name="S_allow_psi" value="${esc(r.input_trace?.overrides?.S_allow_psi??'')}"></label>
<label>Manual material property reference<input name="material_reference" value="${esc(r.input_trace?.overrides?.material_reference??'')}"></label>
</fieldset><label class="check"><input type="checkbox" name="reviewed" value="yes">I checked the component assignment and calculation inputs against the source records.</label><button class="primary">Save code basis</button></form><p class="muted">Current routing: ${esc(r.routing?.status||'NEEDS_CODE_CONFIRMATION')} · results remain DRAFT / NOT VALIDATED.</p>`;bindReferenceSelectors($('codeBasisForm'));}
function batchCodeEditor() {
    const w = workspace();
    if (!w) return;
    const rows = w.rows.filter(row => row.current_id);
    const common = key => rows.length && rows.every(row => row[key] === rows[0][key]) ? rows[0][key] || '' : '';
    $('drawer').hidden = false;
    $('details').innerHTML = `<h2>Set code basis</h2>
        <p>Apply one construction basis to ${esc(w.comparison.current_selection[1])}. Review component inputs separately.</p>
        <form id="batchCodeBasisForm">
            <label>Apply to<select name="scope">
                <option value="sheet">Entire current sheet · ${rows.length} locations</option>
                <option value="selected" ${selected.size ? '' : 'disabled'}>Selected locations · ${selected.size}</option>
            </select></label>
            <label>Asset / service boundary<select name="code_asset_type" required><option value="">Choose…</option></select></label>
            <label>Construction code<select name="code_family" required><option value="">Choose…</option></select></label>
            <label>Edition year<input name="code_edition" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" value="${esc(common('code_edition'))}" required></label>
            <label>Code basis evidence<input name="code_evidence" placeholder="Document, line list, drawing or approved basis reference" value="${esc(rows.every(row => row.code_owner_confirmed) ? common('code_evidence') : '')}" required></label>
            <label class="check"><input type="checkbox" name="code_owner_confirmed" value="yes" required>
                I confirm this code and service boundary apply to all locations in this scope.
            </label>
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
    }
    updateCodes(common('code_family'));
    asset.onchange = () => updateCodes(code.value);
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const {scope, ...values} = Object.fromEntries(new FormData(form));
        if (await action('apply_code_basis', {scope, ids:[...selected], values})) $('drawer').hidden = true;
    });
}
$('editBatchCode').onclick = batchCodeEditor;

function bindReferenceSelectors(form) {
    const material = $('referenceMaterial');
    const temperature = $('referenceTemperature');
    const preview = $('referencePreview');
    const field = key => form.elements.namedItem(key);
    const get = key => field(key)?.value || '';
    let generation = 0;

    function availableRows() {
        const geometry = get('geometry');
        const product = get('code_family') === 'ASME VIII-1'
            ? (['shell','cylindrical_shell','ellipsoidal_head_2to1','standard_torispherical_head'].includes(geometry)
                ? get('product_form') || 'plate' : '')
            : geometry === 'straight_pipe' ? 'pipe'
            : ['elbow','tee','reducer','branch'].includes(geometry) ? 'fitting' : '';
        return state.material_stresses.filter(row => row.code_family === get('code_family') &&
            row.code_edition === get('code_edition') && row.product_form === product);
    }

    function showMethodFields() {
        const code = get('code_family');
        const geometry = get('geometry');
        const straight = geometry === 'straight_pipe';
        const vessel = code === 'ASME VIII-1' && ['shell','cylindrical_shell','ellipsoidal_head_2to1'].includes(geometry);
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
        include(processFitting, 'material temperature_F');
        include(supported && !simplified, 'interval_fraction interval_cap_years');
        include(gas || liquid || process, 'D_outside_in');
        include(process, 'pipe_method');
        include(simplified, 'nominal_thickness_mm');
        include(process && !simplified, 'E_quality W_reduction Y_coefficient');
        include(vessel || gas, 'product_form');
        include(process || vessel || gas, 'temperature_F');
        include(process || vessel, 'S_allow_psi');
        include(supported, 'material_reference');
        include(vessel, 'D_inside_in E_joint');
        include(gas || liquid, 'SMYS_psi E_weld');
        include(gas, 'gas_basic_class F_class T_temp');
        include(liquid, 'F_design');
        for (const control of $('methodFields').querySelectorAll('[name]')) {
            control.disabled = !fields.has(control.name);
            control.closest('label').hidden = control.disabled;
        }
        const lookup = supported || processFitting;
        material.closest('label').hidden = !lookup;
        temperature.closest('label').hidden = !(process || processFitting || vessel || gas);
        preview.hidden = !lookup;
        $('methodHint').textContent = supported ? '' : code === 'API 650'
            ? 'Use Tank assessments for tank inputs and calculations.'
            : 'Choose the code and a supported component geometry to see its inputs.';
    }

    async function refresh() {
        showMethodFields();
        const current = ++generation;
        const editions = {'ASME B31.3':'2024', 'ASME B31.4':'2025', 'ASME B31.8':'2025', 'ASME VIII-1':'2025'};
        const libraryEdition = editions[get('code_family')];
        field('code_edition').placeholder = libraryEdition ? 'Library edition: ' + libraryEdition : 'Enter source edition';
        const rows = availableRows();
        const gas = get('code_family') === 'ASME B31.8' && get('code_edition') === '2025' &&
            get('geometry') === 'straight_pipe';
        const materials = [...new Set(rows.map(row => row.material))];
        if (gas) materials.push(...state.gas_pipe_grades.map(grade => 'API 5L ' + grade));
        const liquid = get('code_family') === 'ASME B31.4' && get('code_edition') === '2025' &&
            get('geometry') === 'straight_pipe';
        if (liquid) materials.push(...state.liquid_pipe_grades);
        options(material.id, materials.map(value => [value, value]), get('material'),
            materials.length ? 'Choose a grade' : !get('code_edition') ? 'Enter the code edition first' : 'No library grades for this selection');
        material.disabled = !materials.length;
        const points = rows.filter(row => row.material === get('material')).map(row => [
            row.temperature_F, row.temperature_F + ' °F']);
        if (gas) points.push(...[250,300,350,400,450].map(value => [String(value), value + ' °F']));
        options(temperature.id, points, get('temperature_F'), points.length ? 'Choose a temperature' : 'Enter temperature below');
        temperature.disabled = !points.length;
        if (preview.hidden) return;
        preview.textContent = 'Checking reference values…';
        try {
            const response = await fetch('/api/workspace/reference_preview', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({values:Object.fromEntries(new FormData(form))}),
            });
            const result = await response.json();
            if (!response.ok) throw Error(result.error || 'Reference lookup failed');
            if (current !== generation) return;
            preview.innerHTML = result.entries.map(entry =>
                `<div><strong>${esc(entry.label)}: ${esc(entry.value)}</strong> <small>${esc(entry.reference)}</small></div>`).join('')
                || 'No automatic value for this selection. Enter a reviewed value if required.';
        } catch (error) {
            if (current === generation) preview.textContent = error.message;
        }
    }
    function clearMaterialProperties() {
        for (const key of ['S_allow_psi','SMYS_psi','material_reference']) field(key).value = '';
    }

    field('code_edition').addEventListener('input', () => {
        clearMaterialProperties();
        refresh();
    });
    form.addEventListener('change', event => {
        if (event.target === field('gas_basic_class') && get('gas_basic_class') !== 'manual') field('F_class').value = '';
        if (event.target === material && material.value) {
            field('material').value = material.value;
            if (get('code_family') === 'ASME VIII-1' && !get('product_form')) field('product_form').value = 'plate';
        }
        if (event.target === temperature && temperature.value) field('temperature_F').value = temperature.value;
        if (['code_family','geometry','product_form','material','temperature_F'].includes(event.target.name) ||
            event.target === material || event.target === temperature) {
            clearMaterialProperties();
        }
        refresh();
    });
    refresh();
}
function identityInputs(r){const i=r.match_identity||{},meta=[i.section||r.segment,i.joint?`Joint ${i.joint}`:'',i.band?`Band ${i.band}`:'',i.size?`NPS ${i.size}`:''].filter(Boolean).join(' · ');return `<div class="identity-summary"><strong>${esc(r.location||'Unassigned location')}</strong><small>${esc(meta||'Location details unavailable')}</small></div><div class="identity-actions"><details class="identity-editor"><summary>Edit match</summary><div class="identity-fields">${['section','joint','band','size'].map(k=>`<label class="identity-field">${esc(k)}<input data-identity="${k}" data-row="${esc(r.current_id)}" value="${esc(i[k]||'')}" aria-label="Matching ${k} for ${esc(r.location)}"></label>`).join('')}</div><button data-save-identity="${esc(r.current_id)}">Save match</button><small class="match-warning">${esc((r.match_flags||[]).join('; '))}</small></details><button class="detail-action" data-code="${esc(r.current_id)}">Code basis · ${esc(r.routing?.status||'NEEDS_CODE_CONFIRMATION')}</button><button class="detail-action" data-detail="${esc(r.id)}">Calculation details</button></div>`;}
function componentInput(r){const current=r.match_identity?.component||'unknown';return `<select data-component="${esc(r.current_id)}" aria-label="Component type for ${esc(r.location)}">${['unknown','straight_pipe','elbow','tee','reducer','fitting'].map(v=>`<option value="${v}" ${v===current?'selected':''}>${v.replaceAll('_',' ')}</option>`).join('')}</select>`;}
function previousLabel(c){return `${c.identity.joint} / ${c.identity.band} / NPS ${c.identity.size||'?'} · ${c.date} · ${c.value} mm · ${c.cell}`;}
function previousInput(r){const c=(workspace()?.previous_choices_by_section?.[r.previous_section]||[]).find(x=>x.id===r.previous_id);return `<select data-previous="${esc(r.current_id)}" data-previous-section="${esc(r.previous_section||'')}" aria-label="Previous reading for ${esc(r.location)}">${r.previous_id?`<option value="${esc(r.previous_id)}" selected>${esc(previousLabel(c||{identity:{joint:'',band:''},date:'',value:'',cell:''}))}</option>`:'<option value="">Choose previous UT…</option>'}</select>`;}
function rowHtml(r){const c=r.row7||{},fields=r.profile?.fields||{},i=r.input_trace?.inputs||{
pd_psi:fields.P_psi?.value,od_in:fields.D_outside_in?.value,nominal_mm:fields.nominal_thickness_mm?.value,
structural_mm:r.input_trace?.overrides?.structural_minimum_mm,selected_cr:r.input_trace?.overrides?.adopted_rate_mm_year},dims=state.dimensions.filter(d=>d.family==='ferritic'&&!d.issues.length),result=c.result?`DRAFT / NOT VALIDATED · ${c.result}`:'Inputs needed',resultClass='review';return `<tr data-row-id="${esc(r.current_id)}"><td class="select-cell">${r.current_id?`<input type="checkbox" data-select="${esc(r.current_id)}" ${selected.has(r.current_id)?'checked':''} aria-label="Select ${esc(r.location)}">`:''}</td><td class="identity-cell">${identityInputs(r)}</td><td>${componentInput(r)}</td><td class="reading-cell"><div class="ut-reading"><small class="ut-date">${esc(r.previous_inspection_date||'Date missing')}</small>${reading(r.previous_id,r.previous_thickness_mm,'Previous')}</div><div class="previous-match">${previousInput(r)}</div></td><td class="reading-cell"><div class="ut-reading"><small class="ut-date">${esc(r.inspection_date||'Date missing')}</small>${reading(r.current_id,r.current_thickness_mm,'Current')}</div></td><td>${rowSelect(r,'material',r.material,['A106 B','A234 WPB','API 5L X52'])}<small class="allowable-stress">S: ${num(c.s_psi||r.S_allow_psi)}</small></td><td>${rowSelect(r,'nps',r.nps,dims.map(d=>d.nps))}${rowSelect(r,'schedule',r.schedule,dims.filter(d=>d.nps===r.nps).map(d=>d.schedule))}</td><td>${edit(r,'P_psi',i.pd_psi)}</td><td>${edit(r,'D_outside_in',i.od_in)}</td><td>${edit(r,'nominal_thickness_mm',i.nominal_mm)}</td><td>${edit(r,'structural_minimum_mm',i.structural_mm)}</td><td>${edit(r,'adopted_rate_mm_year',i.selected_cr)}</td>${[c.pressure_mm,c.required_mm,c.calculated_cr,c.cr_used,c.remaining_life,c.interval,c.mawp_thickness_mm,c.mawp_psi].map(v=>`<td>${num(v)}</td>`).join('')}<td class="result-cell"><span class="result-badge ${resultClass}">${esc(result)}</span><small>${esc(c.cr_basis||r.issues.join('; '))}</small></td><td>${esc(c.next_inspection||'—')}</td></tr>`;}
function syncTableScroll(){const rail=$('tableXScroll'),scroller=$('tableScroll'),table=$('locations');if(!rail||!scroller||!table)return;rail.firstElementChild.style.width=table.scrollWidth+'px';rail.hidden=table.scrollWidth<=scroller.clientWidth+1;const railMax=rail.scrollWidth-rail.clientWidth,tableMax=scroller.scrollWidth-scroller.clientWidth;rail.scrollLeft=tableMax>0?scroller.scrollLeft/tableMax*railMax:0;}
function syncTableScrollFrom(source,target){const sourceMax=source.scrollWidth-source.clientWidth,targetMax=target.scrollWidth-target.clientWidth,next=sourceMax>0?source.scrollLeft/sourceMax*targetMax:0;if(Math.abs(target.scrollLeft-next)>1)target.scrollLeft=next;}
function readiness(row) {
    const profile = row.profile || {};
    const fields = profile.fields || {};
    const overrides = row.input_trace?.overrides || {};
    const value = key => overrides[key] ?? fields[key]?.value;
    const missing = [];
    const notes = [];
    const requireValue = (key, label) => {
        if (value(key) == null || value(key) === '') missing.push(label);
    };
    if (!row.previous_id) missing.push('Match the previous UT reading');
    if (!row.previous_inspection_date || !row.inspection_date) missing.push('Confirm inspection dates');

    const code = row.code_family;
    const vessel = code === 'ASME VIII-1';
    const pipeline = ['ASME B31.4', 'ASME B31.8'].includes(code);
    const pipe = code === 'ASME B31.3';
    const assigned = Boolean(code && row.code_edition && row.code_asset_type &&
        row.code_owner_confirmed && row.code_evidence?.trim());
    if (!assigned) missing.push('Confirm construction code, edition, service and evidence');
    if (!row.reviewed) missing.push('Review the component assignment and calculation inputs');

    if (vessel || pipeline || pipe) {
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
            if (pipe && (workspace()?.settings?.basis === 'recalculate' || overrides.pipe_method === 'code')) {
                requireValue('E_quality', 'Quality factor');
                requireValue('W_reduction', 'Weld strength reduction factor');
                requireValue('Y_coefficient', 'Y coefficient');
            } else if (pipe) {
                requireValue('nominal_thickness_mm', 'Nominal wall thickness');
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
            else missing.push('Design temperature for stress lookup, or reviewed allowable stress');
        }
    }
    if (assigned && !vessel && !pipeline && !pipe) notes.push('Use the applicable assessment screen for this code.');
    if (row.routing?.status === 'NOT_ASSESSED' &&
        !(vessel && workspace()?.settings?.basis === 'row7')) {
        notes.push(...(row.routing.issues || []));
    }
    if (row.issues?.includes('PROFILE_CURRENT_CONFLICT')) notes.push('Resolve the conflict between the source record and measured UT.');
    if (row.issues?.includes('INSPECTION_POLICY_REQUIRED')) missing.push('Inspection interval policy');
    if (row.previous_id && Number(row.previous_thickness_mm) <= Number(row.current_thickness_mm)) {
        notes.push('No positive observed wall loss. Review the rate before forecasting.');
    }

    const sourced = ['S_allow_psi', 'SMYS_psi', 'D_outside_in', 'nominal_thickness_mm']
        .filter(key => fields[key]?.kind === 'reference_derived' && fields[key]?.value != null)
        .map(key => {
            const labels = {S_allow_psi:'Allowable stress (psi)', SMYS_psi:'SMYS (psi)',
                D_outside_in:'OD (in)', nominal_thickness_mm:'Nominal wall (mm)'};
            return [labels[key], fields[key].value, fields[key].basis];
        });
    const design = row.input_trace?.normalized_design || {};
    if (design.SMYS_MPa?.reference) sourced.push(['SMYS (psi)', design.SMYS_MPa.value_psi, design.SMYS_MPa.reference]);
    if (design.F_class?.reference) sourced.push(['Basic design factor F', design.F_class.value, design.F_class.reference]);
    if (design.T_temp?.reference) sourced.push(['Temperature factor T', design.T_temp.value, design.T_temp.reference]);
    return {missing, notes, sourced};
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
    renderSuggestedGroups(rows);
    const records = rows.map(row => ({row, ...readiness(row)}));
    const outstanding = records.filter(record => record.missing.length || record.notes.length).length;
    $('readinessCount').textContent = '· ' + outstanding + ' of ' + records.length + ' shown need attention';
    const reading = (thickness, cell, date, sheet) => thickness == null ? 'Unavailable' :
        num(thickness) + ' mm · ' + esc(date || 'Date missing') + ' · ' + esc([sheet, cell].filter(Boolean).join('!'));
    $('readinessTable').querySelector('tbody').innerHTML = records.map(({row, missing, notes, sourced}) =>
        `<tr><td>${esc(row.location)}</td>
        <td>Previous: ${reading(row.previous_thickness_mm, row.previous_cell, row.previous_inspection_date, row.previous_sheet)}<br>
        Current: ${reading(row.current_thickness_mm, row.current_cell, row.inspection_date, row.current_sheet)}</td>
        <td>${sourced.map(([label,value,basis]) => `<div>${esc(label)}: ${num(value)} <small>${esc(basis)}</small></div>`).join('') || 'No code lookup applied'}</td>
        <td>${[...missing,...notes].map(item => `<div>${esc(item)}</div>`).join('') || 'No missing inputs identified'}</td>
        <td><button data-readiness-code="${esc(row.current_id)}">Code and inputs</button>
        <button data-readiness-select="${esc(row.current_id)}">${selected.has(row.current_id) ? 'Deselect' : 'Select for shared inputs'}</button></td></tr>`).join('');
}

function table(){const rows=visible();renderReadiness(rows);$('locations').querySelector('tbody').innerHTML=rows.map(rowHtml).join('');$('selectedCount').textContent=selected.size+' selected';$('rowCount').textContent=rows.length+' of '+(workspace()?.rows.length||0)+' locations';const ids=rows.map(r=>r.current_id).filter(Boolean);$('selectAll').checked=ids.length>0&&ids.every(id=>selected.has(id));$('selectAll').indeterminate=ids.some(id=>selected.has(id))&&!$('selectAll').checked;$('inputScope').textContent=selected.size===1?'Batch inputs · one selected reading':'Batch inputs · '+selected.size+' selected readings';requestAnimationFrame(syncTableScroll);}
function reading(id,value,label){return id?`<input class="reading" type="number" min="0" step="any" data-reading="${esc(id)}" value="${esc(value)}" aria-label="${label} UT">`:'—';}
function dimensions(){if(!state)return;const nps=$('nps').value,schedule=$('schedule').value;const rows=state.dimensions.filter(d=>d.family===$('pipeFamily').value);options('nps',[...new Set(rows.map(d=>d.nps))].map(n=>[n,n+' in']),nps,'Custom / keep existing');options('schedule',rows.filter(d=>d.nps===$('nps').value).map(d=>[d.schedule,d.schedule+(d.issues.length?' · unavailable':'')]),schedule,'Keep existing');const d=dimension();$('dimensions').textContent=d?`${d.od_in} in OD · ${d.nominal_mm} mm nominal${d.issues.length?' · reference discrepancy; choose another entry':''}`:'Select size and schedule, or enter custom dimensions.';}
function dimension(){return state?.dimensions.find(d=>d.family===$('pipeFamily').value&&d.nps===$('nps').value&&d.schedule===$('schedule').value);}
function values(){const out=Object.fromEntries([...new FormData($('batchForm'))].filter(([k,v])=>v!==''&&k!=='materialCustom'));if($('materialGrade').value==='Custom…'){out.material=$('materialCustom').value.trim();}return out;}
function requireSelected(){if(selected.size)return true;message('Select one or more readings first.',true);return false;}
function detail(id){const r=workspace().rows.find(r=>r.id===id);if(!r)return;$('drawer').hidden=false;$('details').innerHTML=`<h2>${esc(r.location)}</h2><button id="editRow">Edit this row only</button>${r.current_id&&!r.previous_id?'<button id="pairRow">Use previous UT on same source row</button>':''}<p>Previous: ${esc(r.previous_inspection_date)} · ${esc(r.previous_cell)}<br>Current: ${esc(r.inspection_date)} · ${esc(r.current_cell)}</p><p>CR = (previous − current) / ((current date − previous date) / 365). Use selected CR only when calculated CR ≤ 0.</p><p>Required = MAX(pressure thickness, structural thickness).<br>Life = (current − required) / CR used.<br>Interval = MIN(10, life / 2).<br>t in MAWP = current − 2 × CR used × interval.</p><pre>${esc(JSON.stringify(r.row7||r.issues,null,2))}</pre>`;if($('pairRow'))$('pairRow').onclick=async()=>{await action('pair',{id:r.current_id});$('drawer').hidden=true;};$('editRow').onclick=()=>{selected=new Set([r.current_id]);$('batchForm').reset();const i=r.input_trace?.inputs||{};const fields={material:i.material,P_psi:i.pd_psi,D_outside_in:i.od_in,nominal_thickness_mm:i.nominal_mm,structural_minimum_mm:i.structural_mm,adopted_rate_mm_year:i.selected_cr,segment:r.segment};for(const [key,value] of Object.entries(fields))$('batchForm').elements.namedItem(key).value=value??'';dimensions();$('drawer').hidden=true;document.querySelector('.batch-panel').open=true;table();};}
function results() {
    const w = workspace();
    if (!w) return;
    const result = w.results[0];
    const current = result && !result.stale;
    const savedRows = current ? result.rows.filter(row => row.current_id) : [];
    const ready = savedRows.filter(row => row.pressure_thickness_mm != null);
    const traceLink = row => `<a href="/workspace/calculation?${new URLSearchParams({result:result.id,row:row.id})}">How was this calculated?</a>`;
    $('codeResults').innerHTML = ready.length ? `<table><thead><tr><th>Location</th><th>Method</th>
        <th>Pressure thickness (mm)</th><th>Required thickness (mm)</th><th>Corrosion rate (mm/year)</th>
        <th>Remaining life (years)</th><th>Pressure candidate (MPa)</th><th>Details</th></tr></thead><tbody>
        ${ready.map(row => `<tr><td>${esc(row.location)}</td><td>${esc(row.rule)}</td>
        <td>${num(row.pressure_thickness_mm)}</td><td>${num(row.required_thickness_mm)}</td>
        <td>${num(row.apparent_rate_mm_year)}</td><td>${num(row.remaining_life_years)}</td>
        <td>${num(row.mawp_MPa)}</td><td>${traceLink(row)}</td></tr>`).join('')}</tbody></table>` : '';
    $('metrics').innerHTML = `<div class="metric">${w.rows.length} locations</div>
        <div class="metric">${ready.length} saved draft calculations</div>
        <div class="metric">${w.rows.length - ready.length} without a saved pressure calculation</div>`;
    $('resultSummary').textContent = current
        ? `${ready.length} of ${savedRows.length} locations have DRAFT / NOT VALIDATED pressure calculations.`
        : 'Calculate ready locations to save the current results.';
    $('exports').innerHTML = current
        ? `<a href="/workspace/results.csv?${new URLSearchParams({result:result.id})}">Download evaluation CSV</a>` : '';
    const review = (current ? savedRows : w.rows).filter(row => row.issues?.length);
    $('reviewSummary').innerHTML = review.map(row => `<li>${esc(row.location)}: ${esc(row.issues.join('; '))}
        ${current ? traceLink(row) : ''}</li>`).join('') || '<li>No review items for the displayed rows.</li>';
}

document.querySelectorAll('[data-screen]').forEach(b=>b.onclick=()=>navigate(b.dataset.screen));$('source').onchange=sheets;$('openSheet').onclick=()=>{if(!$('source').value||!$('sheet').value)return message('Choose a workbook and UT sheet.',true);action('import',{source_id:$('source').value,sheet:$('sheet').value});};
$('upload').onsubmit=async e=>{e.preventDefault();$('busy').hidden=false;try{const response=await fetch('/workspace/upload',{method:'POST',body:new FormData(e.target)}),data=await response.json();if(!response.ok)throw Error(data.error);cid=data.comparison_id||cid;await load();navigate(data.comparison_id?'workspace':'import');message(data.message||'Workbook imported.');}catch(e){message(e.message,true);}finally{$('busy').hidden=true;}};
$('comparison').onchange=async()=>{cid=$('comparison').value;selected.clear();try{await load();}catch(e){message(e.message,true);}};
$('changeCampaigns').onclick=()=>{const w=workspace();if(w)action('import',{source_id:w.comparison.current_selection[0],sheet:w.comparison.current_selection[1],previous:$('previousCampaign').value,current:$('currentCampaign').value});};$('resolveDates').onclick=()=>{const dates=Object.fromEntries([...document.querySelectorAll('[data-campaign-date]')].filter(el=>el.value).map(el=>[el.dataset.campaignDate,el.value]));if(!Object.keys(dates).length)return message('Enter an exact date for at least one inspection.',true);action('dates',{campaign_dates:dates});};
$('search').oninput=table;$('sectionFilter').onchange=table;$('componentFilter').onchange=table;$('selectComponent').onclick=()=>{const type=$('componentFilter').value;if(!type)return message('Choose straight pipes or fittings first.',true);visible().filter(r=>r.current_id).forEach(r=>selected.add(r.current_id));table();};$('selectVisible').onclick=()=>{visible().filter(r=>r.current_id).forEach(r=>selected.add(r.current_id));table();};$('clearSelection').onclick=()=>{selected.clear();table();};$('selectAll').onchange=e=>{visible().filter(r=>r.current_id).forEach(r=>e.target.checked?selected.add(r.current_id):selected.delete(r.current_id));table();};
$('locations').onchange=e=>{if(e.target.dataset.identity){action('identity',{id:e.target.dataset.row,values:{[e.target.dataset.identity]:e.target.value}});return;}if(e.target.dataset.previous){if(e.target.value)action('identity',{id:e.target.dataset.previous,previous_id:e.target.value});return;}if(e.target.dataset.component){const type=e.target.value;action('identity',{id:e.target.dataset.component,values:{component:type}});return;}if(e.target.dataset.engineering){inlineEdit(e.target);return;}if(e.target.dataset.select){e.target.checked?selected.add(e.target.dataset.select):selected.delete(e.target.dataset.select);table();}else if(e.target.dataset.reading)action('correct',{id:e.target.dataset.reading,value:e.target.value});};$('locations').onclick=e=>{const save=e.target.closest('[data-save-identity]');if(save){const fields=[...save.closest('tr').querySelectorAll('[data-identity]')];action('identity',{id:save.dataset.saveIdentity,values:Object.fromEntries(fields.map(el=>[el.dataset.identity,el.value]))});return;}const code=e.target.closest('[data-code]');if(code){codeEditor(code.dataset.code);return;}const b=e.target.closest('[data-detail]');if(b)detail(b.dataset.detail);};$('details').onsubmit=e=>{if(e.target.id!=='codeBasisForm')return;e.preventDefault();const values=Object.fromEntries([...new FormData(e.target)].filter(([,v])=>v!==''));values.reviewed=values.reviewed||'no';action('apply',{ids:[e.target.dataset.row],values}).then(saved=>{if(saved)codeEditor(e.target.dataset.row);});};$('readinessTable').onclick = event => {
    const target = event.target.closest('[data-readiness-code]');
    if (target) {
        codeEditor(target.dataset.readinessCode);
        return;
    }
    const select = event.target.closest('[data-readiness-select]');
    if (select) {
        const id = select.dataset.readinessSelect;
        if (selected.has(id)) selected.delete(id);
        else selected.add(id);
        table();
    }
};
$('closeDrawer').onclick=()=>$('drawer').hidden=true;document.onkeydown=e=>{if(e.key==='Escape')$('drawer').hidden=true;};
 $('tableXScroll').addEventListener('scroll',()=>syncTableScrollFrom($('tableXScroll'),$('tableScroll')));$('tableScroll').addEventListener('scroll',()=>syncTableScrollFrom($('tableScroll'),$('tableXScroll')));window.addEventListener('resize',()=>requestAnimationFrame(syncTableScroll));
 $('locations').onfocusin=e=>{const select=e.target.closest('[data-previous-section]');if(!select||select.dataset.loaded)return;select.dataset.loaded='yes';const choices=workspace()?.previous_choices_by_section?.[select.dataset.previousSection]||[];select.insertAdjacentHTML('beforeend',choices.map(c=>`<option value="${esc(c.id)}" ${c.id===select.value?'selected':''}>${esc(previousLabel(c))}</option>`).join(''));};
$('pipeFamily').onchange=()=>{$('nps').value='';$('schedule').value='';dimensions();};$('nps').onchange=()=>{$('schedule').value='';dimensions();};$('schedule').onchange=()=>{dimensions();const d=dimension();if(d&&!d.issues.length){$('batchForm').elements.D_outside_in.value=d.od_in;$('batchForm').elements.nominal_thickness_mm.value=d.nominal_mm;}};
for(const key of ['D_outside_in','nominal_thickness_mm'])$('batchForm').elements.namedItem(key).oninput=()=>{$('nps').value='';$('schedule').value='';dimensions();};
$('materialGrade').onchange=()=>{$('materialCustom').hidden=$('materialGrade').value!=='Custom…';if($('materialGrade').value==='Custom…')$('materialCustom').focus();};$('batchForm').onsubmit=e=>{e.preventDefault();if(!requireSelected())return;const payload={ids:[...selected],values:values(),fill_missing:$('fillMissing').checked},d=dimension();if(d)payload.dimension_key=[d.family,d.nps,d.schedule];else if(payload.values.D_outside_in||payload.values.nominal_thickness_mm)Object.assign(payload.values,{nps:'Custom',schedule:'Custom'});action('apply',payload);};$('resetSelected').onclick=()=>{if(requireSelected())action('apply',{ids:[...selected],clear:true});};$('evaluate').onclick=()=>action('evaluate',{basis:'assigned'});$('undo').onclick=()=>action('undo');$('backWorkspace').onclick=()=>navigate('workspace');
const initialView = new URLSearchParams(location.search).get('view');
load().then(()=>navigate(workspace()?(initialView==='results'?'results':'workspace'):'import')).catch(e=>message(e.message,true));

let pendingCleanup=null;
function renderWorkbooks(){
 $('workbookList').innerHTML=state.sources.length?state.sources.map(s=>`<article class="source"><strong>${esc(s.file_name)}</strong><button data-delete-source="${esc(s.source_id)}">Delete workbook</button></article>`).join(''):'<p>No imported workbooks. Choose an Excel file above to begin.</p>';
 $('restoreCleanup').hidden=!state.cleanup_backup_available;
 if(!workspace()){$('locations').querySelector('tbody').innerHTML='';$('metrics').innerHTML='';$('resultSummary').textContent='';$('exports').innerHTML='';$('reviewSummary').innerHTML='';}
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
  Object.assign(payload.values,{D_outside_in:d.od_in,schedule:'Custom'});
 }else if(key==='schedule'){
  const d=state.dimensions.find(d=>d.family==='ferritic'&&d.nps===row.nps&&d.schedule===value&&!d.issues.length);
  if(d)payload.dimension_key=[d.family,d.nps,d.schedule];
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
