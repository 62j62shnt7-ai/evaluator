"""Read-only onboarding for calculation methods and reference coverage."""
from decimal import Decimal

from evaluator.engineering.draft import FORMULAS, REFERENCES, evaluate
from evaluator.engineering.reference_rules import GAS_5L_SMYS_PSI, GAS_SMYS_REFERENCE, GAS_TEMPERATURE_REFERENCE
from evaluator.engineering.references import dimension, material_stresses
from evaluator.desk_ui import shell
from evaluator.workflow_ui import E


GUIDES = (
    ('b313', 'ASME B31.3 · 2024', 'Straight process piping', (
        'Select the construction code and confirm the service boundary. The assigned-code calculation uses design pressure, outside diameter, allowable stress S, quality factor E, weld strength reduction factor W and coefficient Y.',
        'Use NPS and schedule to retrieve outside diameter and nominal wall from API RP 574. The limited B31.3 lookup covers A106 Grade B pipe and A234 WPB fittings at exact supported temperatures. A fitting stress lookup does not make the straight-pipe equation applicable to a fitting.',
        'The assigned-code result is pressure thickness. A separately supplied structural minimum can govern required thickness. The workspace’s pipe calculation is a separate simplified workflow, with fixed E = 1, W = 1 and Y = 0.4 implicit in its pressure equation. Its forecast uses the selected wall-loss rate and its built-in interval policy.',
    ), ('B31_3_304_1_2',)),
    ('b314', 'ASME B31.4 · 2025', 'Straight liquid pipeline', (
        'Enter design pressure, outside diameter, specified minimum yield strength (SMYS), design factor F and weld factor E. These factors and SMYS must come from reviewed line records or applicable code sources.',
        'The method calculates the pressure wall component. Review required allowances separately. The inverse calculation is a component pressure candidate. System operating limits, transient pressure and corrosion disposition need separate checks.',
    ), ('B31_4_403_2_1',)),
    ('b318', 'ASME B31.8 · 2025', 'Straight gas pipeline', (
        'Enter design pressure, outside diameter and SMYS, together with the applicable class, weld and temperature factors. For B31.8-2025, the app can derive T from the steel-pipe temperature table and retrieve SMYS for selected API 5L grades and manufacturing types. Enter the applicable design and weld factors.',
        'The method calculates a design wall candidate. Qualifying pressure tests, operating history, other components and applicable restrictions are needed to establish system MAOP.',
    ), ('B31_8_841_1_1',)),
    ('vessel', 'ASME VIII-1 / II-D Metric · 2025', 'Vessel shell and heads', (
        'For a cylindrical shell, enter inside diameter, design pressure, allowable stress S and joint efficiency E. The app derives inside radius. It calculates both hoop and longitudinal thickness, and the larger thickness governs. For inverse pressure the lower result governs.',
        'A 2:1 ellipsoidal head uses its inside diameter and its own equation. The engine also has a standard torispherical candidate that needs the inside crown radius. The main input editor currently supports the shell and 2:1 head paths.',
        'The embedded vessel lookup covers SA-516 Grade 70 plate at the exact points below. Confirm product form, metal temperature, edition and applicability of the cited notes. Other grades, forms or temperatures need a reviewed stress value.',
    ), ('VIII_UG27_HOOP', 'VIII_UG27_LONG', 'VIII_UG32_ELLIP', 'VIII_UG32_TORI')),
    ('history', 'API 570 / API 510', 'Inspection history and remaining life', (
        'Match the previous and current UT values by physical measurement location. The app keeps the source cells and inspection dates. Observed corrosion rate uses the thickness change divided by elapsed time. If wall loss is zero or readings increase, review the cause and rate basis before forecasting.',
        'Remaining life uses current thickness, the governing required thickness and an adopted positive rate. Pressure thickness and structural thickness serve different purposes. The component review and inspection policy determine which inputs can be used.',
    ), ('CR_ST', 'REMAINING_LIFE', 'API570_T_REQUIRED')),
    ('api650', 'API 650 · 14th edition, 2025', 'Tank shell design', (
        'Open Tank assessments. The SI one-foot method uses tank diameter, product and hydrotest heights above the course bottom, specific gravity, separate product and hydrotest stresses, and corrosion allowance. The method is limited to diameters up to 61 m.',
        'The app compares the product and hydrotest thicknesses with the reviewed nominal plate minimum. The app looks up the SI minimum by diameter and course position. Enter any higher project minimum and both stresses from applicable records. Other design loads require their own checks.',
    ), ('API650_ONE_FOOT_PRODUCT', 'API650_ONE_FOOT_HYDRO')),
    ('api653', 'API 653 · 5th edition through July 2025', 'In-service tanks', (
        'Map literal workbook cells to a course minimum, the reviewed local profile, or bottom-side and product-side minima. The saved assessment retains the worksheet, cells, inspection date and workbook hash. Manual entry is also available.',
        'Shell §4.3.3.1 uses diameter, liquid height, gravity, plate strengths and joint efficiency. The app takes the lower allowable stress limit from yield and tensile strength and applies the course-specific factors. Whole-course and local methods use different height datums. The liquid height candidate is capped at the original design height.',
        'For a local area (§4.3.2.1), compare the reviewed profile average with the shell minimum and the least thickness excluding pits with 60% of that minimum, accounting for future corrosion. The scattered-pit screen (§4.3.2.2) checks remaining wall under each pit and accumulated pit extent in sliding 200 mm windows.',
        'Bottom §4.4.5.1 projects the lesser side thickness forward using both corrosion rates. Critical-zone and nonseismic annular checks also show the outside weld toe thickness and projection margins. The annular path requires a reviewed API 653 Table 4.5a or API 650 Table 5.1a value, selected by product gravity.',
    ), ()),
)

RULE_LABELS = {
    'VIII_UG27_HOOP': 'Cylindrical shell, hoop stress',
    'VIII_UG27_LONG': 'Cylindrical shell, longitudinal stress',
    'VIII_UG32_ELLIP': '2:1 ellipsoidal head',
    'VIII_UG32_TORI': 'Standard torispherical head',
    'CR_ST': 'Observed short-term corrosion rate',
    'REMAINING_LIFE': 'Remaining life with an adopted rate',
    'API570_T_REQUIRED': 'Compare supplied pressure and structural minima',
    'API650_ONE_FOOT_PRODUCT': 'Product design thickness',
    'API650_ONE_FOOT_HYDRO': 'Hydrotest thickness',
}


def _number(value):
    return format(Decimal(str(value)), '.2f')


def _lookup_table():
    rows = sorted(material_stresses(), key=lambda r: (r['code_family'], r['material'], Decimal(r['temperature_F'])))
    body = []
    for row in rows:
        stress = _number(row['S_allow_psi']) + ' psi'
        if row.get('S_allow_MPa'):
            stress += ' / ' + row['S_allow_MPa'] + ' MPa'
        temperature = row['temperature_F'].removesuffix('.0') + ' °F'
        if row.get('temperature_C'):
            temperature += ' / ' + row['temperature_C'] + ' °C'
        cells = [row['code_family'] + ' ' + row['code_edition'], row['material'], row['product_form'],
                 temperature, stress, row['reference']]
        body.append('<tr>' + ''.join(f'<td>{E(cell)}</td>' for cell in cells) + '</tr>')
    return ('<div class="scroll"><table><thead><tr><th>Code</th><th>Material</th><th>Product</th>'
            '<th>Metal temperature</th><th>Allowable stress S</th><th>Source</th></tr></thead>'
            '<tbody>' + ''.join(body) + '</tbody></table></div>')


def page():
    nav = ' '.join(f'<a class="pill" href="#{key}">{E(title)}</a>' for key, title, *_ in GUIDES)
    parts = [
        '<h1>Codes &amp; Calculations</h1><p>Learn which method applies, where each input comes from, and how to read the result.</p>',
        '<section><h2>Start with your report</h2><ol>'
        '<li>Import Excel and check the matched previous and current thicknesses, dates and locations.</li>'
        '<li>Assign the governing code, edition, component geometry and source evidence.</li>'
        '<li>Enter missing equipment facts from drawings, material certificates and design records. Apply shared inputs to compatible locations.</li>'
        '<li>Review the values the app retrieved, confirm the inputs, and calculate by assigned code. For tank zones use Tank assessments.</li>'
        '<li>Review the governing check and any withheld outputs before using an assessment.</li></ol>'
        '<p><strong>Workbook</strong> supplies UT readings and dates. <strong>Equipment records</strong> supply facts such as geometry, service, material and pressure. '
        '<strong>Code references</strong> supply verified lookup values. <strong>The app</strong> calculates thickness, rate, life and method-specific candidates.</p>'
        '<p><strong>DRAFT / NOT VALIDATED</strong> applies to calculated results. Each method has its own applicability and input review.</p></section>',
        '<nav class="pills" aria-label="Jump to code">' + nav + '<a class="pill" href="#lookups">Material values</a></nav>',
    ]
    for key, title, subtitle, steps, rules in GUIDES:
        parts.append(f'<section id="{key}"><h2>{E(title)}</h2><h3>{E(subtitle)}</h3>')
        parts.extend(f'<p>{E(step)}</p>' for step in steps)
        if key == 'api653':
            parts.append('<h3>Calculation paths</h3><ul>'
                         '<li>Whole shell course: tmin = max(2.5 mm, 4.9 × D × (H − 0.3) × G ÷ (S × E)). '
                         'The local equation uses H without the 0.3 m offset.</li>'
                         '<li>Bottom: projected thickness = min(bottom-side wall, product-side wall) − years × sum of both corrosion rates.</li>'
                         '<li>Critical zone: compare projected thickness with max(2.5 mm, min(3 mm, half the lower shell minimum)).</li>'
                         '<li>Scattered shell pits: at least half the shell minimum under each pit and at most 50 mm of pit extent in each 200 mm window.</li></ul>')
        if rules:
            parts.append('<h3>Equations used</h3><dl>')
            for rule in rules:
                parts.append(f'<dt><strong>{E(RULE_LABELS.get(rule, "Pressure thickness"))}</strong></dt>'
                             f'<dd><code>{E(FORMULAS[rule])}</code><br><small>{E(REFERENCES[rule])}</small></dd>')
            parts.append('</dl>')
        parts.append('</section>')

    size = dimension('ferritic', '8', '80')
    hoop = evaluate('VIII_UG27_HOOP', dict(P_MPa=1, R_inside_mm=600, S_allow_MPa=138, E_joint='.85'))
    longitudinal = evaluate('VIII_UG27_LONG', dict(P_MPa=1, R_inside_mm=600, S_allow_MPa=138, E_joint='.85'))
    parts.extend([
        '<section><h2>Worked examples with assumed equipment data</h2>'
        f'<p><strong>Pipe dimensions.</strong> NPS 8 Schedule 80 ferritic pipe gives {E(size["od_in"])} in outside diameter '
        f'and {E(size["nominal_mm"])} mm nominal wall. <small>{E(size["reference"])} · PDF page {size["pdf_page"]}</small></p>'
        '<p><strong>Observed wall loss.</strong> 11.8 mm to 11.2 mm over two years gives (11.8 − 11.2) ÷ 2 = 0.30 mm/year. '
        'If the reviewed required thickness is 5.0 mm and 0.30 mm/year is adopted, remaining life is (11.2 − 5.0) ÷ 0.30 = 20.67 years.</p>'
        '<p><strong>Vessel shell.</strong> Assume P = 1 MPa, inside diameter = 1,200 mm, E = 0.85 and SA-516 Grade 70 plate at 150 °C, '
        'giving S = 138 MPa from II-D Table 1A. The app derives R = 600 mm.</p>'
        '<ul><li>Hoop: 1 × 600 ÷ (138 × 0.85 − 0.6 × 1) = ' + _number(hoop['value']) + ' mm.</li>'
        '<li>Longitudinal: 1 × 600 ÷ (2 × 138 × 0.85 + 0.4 × 1) = ' + _number(longitudinal['value']) + ' mm.</li></ul>'
        '<p>The hoop result governs pressure thickness in this example. A higher structural minimum would govern required thickness.</p></section>',
        '<section><h2>Symbols and units</h2><p>In the pipe and vessel formulas, P and S are in MPa, '
        'D and R are diameter and radius in mm, L is inside crown radius in mm, and the calculated thickness is in mm. '
        'The screen also accepts values in the displayed imperial units and converts them for the assigned-code calculation. '
        'In the tank equations, D and H are in metres, G is specific gravity, and CA is corrosion allowance in mm. '
        'E, W, Y, F and T are the method-specific factors described in each code section.</p></section>',
        '<section id="lookups"><h2>Material stress values currently in the app</h2>'
        '<p>Allowable stress S is matched to the exact code edition, material, product form and listed temperature. '
        'Confirm table notes and the actual equipment inputs before use. Pipeline SMYS is a different property.</p>' + _lookup_table() + '</section>',
        '<section><h2>Coverage boundaries</h2><p>ASME B31G metal-loss assessment, system MAOP/MOP, and whole-tank approval are outside the current calculation paths. A production flowline needs its construction code assigned from records.</p></section>',
    ])
    gas_values = ', '.join(f'{grade}: {value:,} psi' for grade, value in GAS_5L_SMYS_PSI.items())
    parts.append('<section><h2>Gas pipeline reference inputs</h2>'
                 f'<p>API 5L SMYS for listed manufacturing types: {E(gas_values)}.</p>'
                 f'<p><small>{E(GAS_SMYS_REFERENCE["reference"])}</small></p>'
                 '<p>Temperature factor uses the supplied table through 450 °F, including interpolation between entries.</p>'
                 f'<p><small>{E(GAS_TEMPERATURE_REFERENCE["reference"])}</small></p></section>')
    return shell('Code reference library', ''.join(parts), active='/codes')
