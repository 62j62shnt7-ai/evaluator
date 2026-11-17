"""Fail-closed routing for code/edition scoped *draft* calculations.

This module selects a *candidate calculation family* only. It never retrieves
material properties, proves code applicability, or establishes a pressure limit.
The calling workflow must separately verify rule prerequisites, inspections,
operating constraints, owner approvals, and any other limiting component.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


CODES_BY_ASSET: Final[dict[str, frozenset[str]]] = {
    'gas_transmission': frozenset({'ASME B31.8'}),
    'liquid_transmission': frozenset({'ASME B31.4'}),
    'production_flowline': frozenset({'ASME B31.3', 'ASME B31.4', 'ASME B31.8'}),
    'process_piping': frozenset({'ASME B31.3'}),
    'pressure_vessel': frozenset({'ASME VIII-1'}),
    'storage_tank': frozenset({'API 650'}),
}

# These are *implemented arithmetic candidate* identifiers in the current app.
# This router must not invent an API 650 calculator just because the code exists.
_RULES: Final[dict[tuple[str, str], tuple[str, ...]]] = {
    ('ASME B31.3', 'straight_pipe'): ('B31_3_304_1_2',),
    ('ASME B31.4', 'straight_pipe'): ('B31_4_403_2_1',),
    ('ASME B31.8', 'straight_pipe'): ('B31_8_841_1_1',),
    ('ASME VIII-1', 'cylindrical_shell'): ('VIII_UG27_HOOP', 'VIII_UG27_LONG'),
    ('ASME VIII-1', 'ellipsoidal_head_2to1'): ('VIII_UG32_ELLIP',),
    ('ASME VIII-1', 'standard_torispherical_head'): ('VIII_UG32_TORI',),
}

_OUTPUT_BY_CODE: Final[dict[str, str]] = {
    'ASME B31.3': 'PRESSURE_THICKNESS_CANDIDATE',
    'ASME B31.4': 'P_DESIGN_CALCULATED',
    'ASME B31.8': 'P_DESIGN_CALCULATED',
    'ASME VIII-1': 'VESSEL_COMPONENT_PRESSURE_CANDIDATE',
    'API 650': 'TANK_SHELL_THICKNESS_CANDIDATE',
}

_SUPPORTED_EDITIONS: Final[dict[str, frozenset[str]]] = {
    'ASME B31.3': frozenset({'2024'}),
    'ASME B31.4': frozenset({'2025'}),
    'ASME B31.8': frozenset({'2025'}),
    'ASME VIII-1': frozenset({'2025'}),
}


@dataclass(frozen=True, slots=True)
class CodeContext:
    """Verified metadata for one physical component and its service boundary.

    Values must come from actual reviewed engineering records, not defaults.
    ``owner_confirmed`` means someone has explicitly confirmed code scope;
    it is *not* engineering approval of any calculated pressure or MAWP.
    """

    component_id: str
    asset_type: str
    geometry: str
    construction_code: str | None = None
    construction_edition: str | None = None
    code_evidence: str | None = None
    owner_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class RoutingResult:
    status: str
    component_id: str
    candidate_rule_ids: tuple[str, ...]
    output_kind: str | None
    issues: tuple[str, ...]
    note: str = ('Routing is not a design, operating, fitness, or engineering approval.')

    @property
    def can_attempt_arithmetic(self) -> bool:
        return self.status == 'ROUTE_SELECTED' and bool(self.candidate_rule_ids)


def route_code(context: CodeContext) -> RoutingResult:
    """Identify a suitable pre-existing *draft* arithmetic branch, or block.

    In particular, a production flowline never receives a B31 code from its
    name alone, and an unimplemented method never falls back to straight pipe.
    """
    if not isinstance(context, CodeContext):
        raise TypeError('context must be CodeContext')

    component = context.component_id.strip() if isinstance(context.component_id, str) else ''
    if not component:
        return RoutingResult('NEEDS_COMPONENT_IDENTIFICATION', '', (), None,
                             ('Component identity is required to select code scope.',))

    allowed = CODES_BY_ASSET.get(context.asset_type)
    if allowed is None:
        return RoutingResult('NOT_ASSESSED', component, (), None,
                             ('Unsupported asset category; do not infer governing code.',))

    if not context.construction_code or not context.construction_edition:
        return RoutingResult('NEEDS_CODE_CONFIRMATION', component, (), None,
                             ('Construction code and exact edition are required.',))
    code = context.construction_code.strip()
    edition = context.construction_edition.strip()
    if not code or not edition:
        return RoutingResult('NEEDS_CODE_CONFIRMATION', component, (), None,
                             ('Construction code and exact edition are required.',))
    if code not in allowed:
        return RoutingResult('NOT_ASSESSED', component, (), None,
                             (f'{code} is outside the supported scope for {context.asset_type}.',))
    if not context.owner_confirmed or not context.code_evidence or not context.code_evidence.strip():
        return RoutingResult('NEEDS_CODE_CONFIRMATION', component, (), None,
                             ('Owner-confirmed applicability and traceable code-basis evidence are required.',))
    if not edition.isdigit() or len(edition) != 4:
        return RoutingResult('NEEDS_CODE_CONFIRMATION', component, (), None,
                             ('Construction edition must be an exact four-digit year.',))
    if edition not in _SUPPORTED_EDITIONS.get(code, frozenset()):
        return RoutingResult('NOT_ASSESSED', component, (), None,
                             (f'No reviewed arithmetic reference is available for {code} {edition}.',))
    if not context.geometry or not context.geometry.strip():
        return RoutingResult('NOT_ASSESSED', component, (), None,
                             ('Component geometry is unknown.',))

    rules = _RULES.get((code, context.geometry.strip()), ())
    if not rules:
        return RoutingResult('NOT_ASSESSED', component, (), None,
                             (f'No qualified arithmetic branch for {code} / {context.geometry}.',))

    return RoutingResult('ROUTE_SELECTED', component, rules, _OUTPUT_BY_CODE[code],
                         ('Input provenance, rule applicability and full-system limits remain unverified.',))
