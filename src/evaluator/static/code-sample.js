'use strict';

const codePicker = document.querySelector('.sample-picker');
codePicker.querySelectorAll('select').forEach(select => {
    select.addEventListener('change', () => codePicker.requestSubmit());
});
document.getElementById('apply-calculation-code').hidden = true;

const referenceElement = document.getElementById('sample-reference-data');
if (referenceElement) bindReferences(JSON.parse(referenceElement.textContent));

function bindReferences(referenceData) {
    const sampleForm = document.getElementById('sample-inputs');
    const control = name => sampleForm.elements.namedItem(name);
    const sources = sampleForm.querySelector('.sample-sources');
    const groups = [];

    function setOptions(name, options, selected = '') {
        const select = control(name);
        select.replaceChildren(new Option('Manual entry', ''));
        for (const [value, label] of options) select.add(new Option(label, value));
        select.value = options.some(([value]) => value === selected) ? selected : '';
    }

    const choices = values => [...new Set(values)].map(value => [value, value]);

    function showSources() {
        sources.textContent = groups.flatMap(group => {
            const match = group();
            if (!match) return [];
            const edited = Object.entries(match.fields).some(([name, value]) =>
                control(name).value === '' || Number(control(name).value) !== Number(value));
            return [edited ? 'Manual value differs from ' + match.reference : match.reference];
        }).join(' · ');
    }

    function populateGroup(match, targets) {
        for (const name of targets) control(name).value = match?.fields[name] ?? '';
        showSources();
    }

    if (referenceData.dimensions) {
        const rows = referenceData.dimensions;
        const familyRows = () => rows.filter(row => row.family === control('pipe_family').value);
        const sizeRows = () => familyRows().filter(row => row.nps === control('nps').value);
        const setSizes = selected => setOptions('nps', choices(familyRows().map(row => row.nps)), selected);
        const setSchedules = selected => setOptions('schedule', choices(sizeRows().map(row => row.schedule)), selected);
        const lookup = () => {
            const row = sizeRows().find(item => item.schedule === control('schedule').value);
            return row && {fields: {D_outside_mm: row.od, nominal_mm: row.wall}, reference: row.reference};
        };
        const apply = () => populateGroup(lookup(), ['D_outside_mm', 'nominal_mm']);
        setOptions('pipe_family', [['ferritic', 'Ferritic / carbon steel'], ['stainless', 'Stainless steel']],
                   referenceData.selection.pipe_family);
        setSizes(referenceData.selection.nps);
        setSchedules(referenceData.selection.schedule);
        control('pipe_family').addEventListener('change', () => { setSizes(); setSchedules(); apply(); });
        control('nps').addEventListener('change', () => { setSchedules(); apply(); });
        control('schedule').addEventListener('change', apply);
        groups.push(lookup);
    }

    if (referenceData.stresses) {
        const rows = referenceData.stresses;
        const materialRows = () => rows.filter(row => row.material === control('material').value);
        const setTemperatures = selected => setOptions('temperature',
            materialRows().map(row => [row.temperature, row.label]), selected);
        const lookup = () => {
            const row = materialRows().find(item => item.temperature === control('temperature').value);
            return row && {fields: {[referenceData.stressTarget]: row.stress}, reference: row.reference};
        };
        const apply = () => populateGroup(lookup(), [referenceData.stressTarget]);
        setOptions('material', choices(rows.map(row => row.material)), referenceData.selection.material);
        setTemperatures(referenceData.selection.temperature);
        control('material').addEventListener('change', () => { setTemperatures(); apply(); });
        control('temperature').addEventListener('change', apply);
        groups.push(lookup);
    }

    if (referenceData.liquidStrength) {
        const grades = referenceData.liquidStrength;
        const lookup = () => {
            const row = grades[control('material').value];
            return row && {fields: {SMYS_MPa: row.value}, reference: row.reference};
        };
        setOptions('material', choices(Object.keys(grades)), referenceData.selection.material);
        control('material').addEventListener('change', () => populateGroup(lookup(), ['SMYS_MPa']));
        groups.push(lookup);
    }

    if (referenceData.liquidWeld) {
        const weld = referenceData.liquidWeld;
        const lookup = () => {
            const value = weld.values[control('liquid_weld').value];
            return value && {fields: {E_weld: value}, reference: weld.reference};
        };
        setOptions('liquid_weld', choices(Object.keys(weld.values)), referenceData.selection.liquid_weld);
        control('liquid_weld').addEventListener('change', () => populateGroup(lookup(), ['E_weld']));
        groups.push(lookup);
    }

    if (referenceData.gas) {
        const gas = referenceData.gas;
        const bind = (name, options, lookup, target) => {
            setOptions(name, options, referenceData.selection[name]);
            const apply = () => populateGroup(lookup(), [target]);
            control(name).addEventListener('change', apply);
            groups.push(lookup);
            return apply;
        };
        const match = (target, value, reference) => value && {fields: {[target]: value}, reference};
        setOptions('product_form', choices(gas.forms), referenceData.selection.product_form);
        const updateGrade = bind('material', choices(Object.keys(gas.grades)), () =>
            match('SMYS_MPa', control('product_form').value && gas.grades[control('material').value],
                  gas.smys_reference), 'SMYS_MPa');
        control('product_form').addEventListener('change', updateGrade);
        bind('temperature', Object.keys(gas.temperatures).map(value => [value, value + ' °F']), () =>
            match('T_temp', gas.temperatures[control('temperature').value], gas.temperature_reference), 'T_temp');
        bind('basic_class', Object.keys(gas.classes).map(value => [value, 'Class ' + value]), () =>
            match('F_class', gas.classes[control('basic_class').value], gas.class_reference), 'F_class');
    }

    sampleForm.addEventListener('input', showSources);
    showSources();
}

const libraryFilters = document.querySelector('.dimension-filters');
if (libraryFilters) {
    const family = document.getElementById('library-family');
    const nps = document.getElementById('library-nps');
    const schedule = document.getElementById('library-schedule');
    const rows = [...document.querySelectorAll('#pipe-dimensions tbody tr')];

    function resetOptions(select, values, label) {
        const current = select.value;
        const unique = [...new Set(values)];
        select.replaceChildren(new Option(label, ''), ...unique.map(value => new Option(value, value)));
        select.value = unique.includes(current) ? current : '';
    }

    function filterLibrary() {
        const byFamily = rows.filter(row => !family.value || row.dataset.family === family.value);
        resetOptions(nps, byFamily.map(row => row.dataset.nps), 'All sizes');
        const bySize = byFamily.filter(row => !nps.value || row.dataset.nps === nps.value);
        resetOptions(schedule, bySize.map(row => row.dataset.schedule), 'All schedules');
        const visible = new Set(bySize.filter(row => !schedule.value || row.dataset.schedule === schedule.value));
        for (const row of rows) row.hidden = !visible.has(row);
        document.getElementById('dimension-count').textContent = visible.size + ' of ' + rows.length + ' entries';
    }

    libraryFilters.addEventListener('change', filterLibrary);
    libraryFilters.hidden = false;
    filterLibrary();
}
