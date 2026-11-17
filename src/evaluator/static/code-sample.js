'use strict';

const sampleForm = document.getElementById('sample-inputs');
const referenceData = JSON.parse(document.getElementById('sample-reference-data').textContent);
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
