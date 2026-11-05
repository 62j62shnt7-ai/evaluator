"""Explicit candidate-formula arithmetic; results never assert equipment fitness."""
from decimal import Decimal

REQUIRED={
 'CR_LT':('t_initial_mm','t_current_mm','elapsed_years'),
 'CR_ST':('t_previous_mm','t_current_mm','elapsed_years'),
 'REMAINING_LIFE':('t_current_mm','t_required_mm','approved_governing_CR_mm_per_year'),
 'VIII_UG27_HOOP':('P_MPa','R_inside_mm','S_allow_MPa','E_joint'),
 'VIII_UG27_LONG':('P_MPa','R_inside_mm','S_allow_MPa','E_joint'),
 'VIII_UG32_ELLIP':('P_MPa','D_inside_mm','S_allow_MPa','E_joint'),
 'VIII_UG32_TORI':('P_MPa','L_inside_crown_mm','S_allow_MPa','E_joint'),
 'B31_3_304_1_2':('P_MPa','D_outside_mm','S_B313_MPa','E_quality','W_reduction','Y_coefficient'),
 'B31_4_403_2_1':('P_MPa','D_outside_mm','F_design','E_weld','SMYS_MPa'),
 'B31_8_841_1_1':('P_MPa','D_outside_mm','SMYS_MPa','F_class','E_weld','T_temp'),
 'API570_T_REQUIRED':('t_pressure_mm','t_structural_mm'),
}


REFERENCES={
 'CR_LT':'API 510 11th edition §7.1.1.1 / API 570 5th edition §7.1.2',
 'CR_ST':'API 510 11th edition §7.1.1.1 / API 570 5th edition §7.1.2',
 'REMAINING_LIFE':'API 510 11th edition §7.2.1 / API 570 5th edition §7.2',
 'API570_T_REQUIRED':'API 570 5th edition §7.6',
 'VIII_UG27_HOOP':'ASME VIII-1 2025 UG-27(c)(1)',
 'VIII_UG27_LONG':'ASME VIII-1 2025 UG-27(c)(2)',
 'VIII_UG32_ELLIP':'ASME VIII-1 2025 UG-32(c)',
 'VIII_UG32_TORI':'ASME VIII-1 2025 UG-32(d)',
 'B31_3_304_1_2':'ASME B31.3 2024 §304.1.2 equation 3a',
 'B31_4_403_2_1':'ASME B31.4 2025 §403.2.1',
 'B31_8_841_1_1':'ASME B31.8 2025 §841.1.1',
}
FORMULAS={
 'CR_LT':'(t_initial_mm - t_current_mm) / elapsed_years',
 'CR_ST':'(t_previous_mm - t_current_mm) / elapsed_years',
 'REMAINING_LIFE':'(t_current_mm - t_required_mm) / selected_governing_rate_mm_year',
 'API570_T_REQUIRED':'max(t_pressure_mm, t_structural_mm)',
 'VIII_UG27_HOOP':'P*R / (S*E - 0.6*P)',
 'VIII_UG27_LONG':'P*R / (2*S*E + 0.4*P)',
 'VIII_UG32_ELLIP':'P*D / (2*S*E - 0.2*P)',
 'VIII_UG32_TORI':'0.885*P*L / (S*E - 0.1*P)',
 'B31_3_304_1_2':'P*D / (2*(S*E*W + P*Y))',
 'B31_4_403_2_1':'P*D / (2*F*E*SMYS)',
 'B31_8_841_1_1':'P*D / (2*SMYS*F*E*T)',
}

def evaluate(rule, inputs):
    if rule not in REQUIRED: raise ValueError('Unsupported rule')
    missing=[k for k in REQUIRED[rule] if inputs.get(k) in (None,'')]
    result={'rule':rule,'version':'draft-0.1','status':'DRAFT / NOT VALIDATED','value':None,'issues':[],'source_reference':REFERENCES[rule],'formula':FORMULAS[rule],'unit':'mm/year' if rule.startswith('CR_') else ('years' if rule=='REMAINING_LIFE' else 'mm')}
    if missing: result['issues']=['Missing '+', '.join(missing)]; return result
    v={k:Decimal(str(inputs[k])) for k in REQUIRED[rule]}
    if any(not x.is_finite() for x in v.values()): raise ValueError('Inputs must be finite')
    if any(x<0 for k,x in v.items() if k!='approved_governing_CR_mm_per_year'): raise ValueError('Inputs must be nonnegative')
    d=Decimal; value=None
    def divide(a,b):
        if b<=0: raise ValueError('Denominator must be positive')
        return a/b
    if rule.startswith('CR_'):
        baseline=v['t_initial_mm'] if rule=='CR_LT' else v['t_previous_mm']
        value=divide(baseline-v['t_current_mm'],v['elapsed_years'])
        if value<=0: result['issues'].append('Nonpositive historical rate requires resolution')
    elif rule=='REMAINING_LIFE':
        rate=v['approved_governing_CR_mm_per_year']
        if rate<=0: result['issues'].append('RATE_UNRESOLVED')
        elif v['t_current_mm']<=v['t_required_mm']: result['issues'].append('BELOW_OR_AT_REQUIRED_THICKNESS')
        else: value=divide(v['t_current_mm']-v['t_required_mm'],rate)
    elif rule=='API570_T_REQUIRED': value=max(v.values())
    else:
        if any(x<=0 for k,x in v.items() if k!='Y_coefficient'): raise ValueError('Geometry, pressure and factors must be positive')
        for key in ('E_joint','E_quality','W_reduction','E_weld','F_class','T_temp'):
            if key in v and v[key]>1: raise ValueError(key+' cannot exceed 1')
        if rule=='B31_4_403_2_1' and v['F_design']>d('.72'): raise ValueError('B31.4 design factor exceeds 0.72')
        if rule=='B31_3_304_1_2' and v['P_MPa']/(v['S_B313_MPa']*v['E_quality'])>d('.385'): raise ValueError('B31.3 pressure/stress domain requires special analysis')
        p=v['P_MPa']
        if rule=='VIII_UG27_HOOP': value=divide(p*v['R_inside_mm'],v['S_allow_MPa']*v['E_joint']-d('.6')*p)
        elif rule=='VIII_UG27_LONG': value=divide(p*v['R_inside_mm'],2*v['S_allow_MPa']*v['E_joint']+d('.4')*p)
        elif rule=='VIII_UG32_ELLIP': value=divide(p*v['D_inside_mm'],2*v['S_allow_MPa']*v['E_joint']-d('.2')*p)
        elif rule=='VIII_UG32_TORI': value=divide(d('.885')*p*v['L_inside_crown_mm'],v['S_allow_MPa']*v['E_joint']-d('.1')*p)
        elif rule=='B31_3_304_1_2': value=divide(p*v['D_outside_mm'],2*(v['S_B313_MPa']*v['E_quality']*v['W_reduction']+p*v['Y_coefficient']))
        elif rule=='B31_4_403_2_1': value=divide(p*v['D_outside_mm'],2*v['F_design']*v['E_weld']*v['SMYS_MPa'])
        elif rule=='B31_8_841_1_1': value=divide(p*v['D_outside_mm'],2*v['SMYS_MPa']*v['F_class']*v['E_weld']*v['T_temp'])
        if rule=='B31_3_304_1_2' and value>=v['D_outside_mm']/6: raise ValueError('B31.3 thickness domain requires special analysis')
        if rule=='VIII_UG27_HOOP' and value>v['R_inside_mm']/2 and p>d('.385')*v['S_allow_MPa']*v['E_joint']: raise ValueError('VIII shell thickness/pressure domain exceeded')
        if rule=='VIII_UG27_LONG' and value>v['R_inside_mm']/2 and p>d('1.25')*v['S_allow_MPa']*v['E_joint']: raise ValueError('VIII shell thickness/pressure domain exceeded')
        result['issues'].append('Candidate arithmetic only; applicability and other loads require verification')
    result['value']=str(value) if value is not None else None
    result['inputs']={k:str(x) for k,x in v.items()}
    return result
