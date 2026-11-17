"""Fail-closed applicability routing; no pressure calculations are approved."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from evaluator.engineering.code_context import CodeContext, route_code


def context(**changes):
    fields = dict(component_id='PIPE-A', asset_type='process_piping',
                  geometry='straight_pipe', construction_code='ASME B31.3',
                  construction_edition='2024', owner_confirmed=True,
                  code_evidence='approved line list LL-13 rev 3')
    fields.update(changes)
    return CodeContext(**fields)


class CodeRoutingTests(unittest.TestCase):
    def test_process_pipe_route_is_candidate_not_mawp(self):
        r = route_code(context())
        self.assertTrue(r.can_attempt_arithmetic)
        self.assertEqual(r.candidate_rule_ids, ('B31_3_304_1_2',))
        self.assertNotIn('MAWP', r.output_kind)
        self.assertNotIn('APPROVED', r.status)

    def test_flowline_not_inferred_even_if_pipe_geometry_known(self):
        r = route_code(context(asset_type='production_flowline',
                               construction_code=None, owner_confirmed=False))
        self.assertEqual(r.status, 'NEEDS_CODE_CONFIRMATION')
        self.assertFalse(r.can_attempt_arithmetic)

    def test_flowline_requires_evidence_and_owner_confirmation(self):
        for fields in ({'code_evidence': ''}, {'owner_confirmed': False}):
            r = route_code(context(asset_type='production_flowline', **fields))
            self.assertEqual(r.status, 'NEEDS_CODE_CONFIRMATION')

    def test_confirmed_flowline_can_route_matching_code(self):
        r = route_code(context(asset_type='production_flowline',
                               construction_code='ASME B31.8', construction_edition='2025'))
        self.assertEqual(r.candidate_rule_ids, ('B31_8_841_1_1',))
        self.assertEqual(r.output_kind, 'P_DESIGN_CALCULATED')

    def test_wrong_code_is_blocked(self):
        r = route_code(context(asset_type='gas_transmission'))
        self.assertEqual(r.status, 'NOT_ASSESSED')
        self.assertFalse(r.can_attempt_arithmetic)

    def test_missing_edition_never_defaults_to_current_code(self):
        r = route_code(context(construction_edition=None))
        self.assertEqual(r.status, 'NEEDS_CODE_CONFIRMATION')

    def test_unreviewed_edition_has_no_arithmetic_route(self):
        r = route_code(context(construction_edition='2020'))
        self.assertEqual(r.status, 'NOT_ASSESSED')
        self.assertFalse(r.can_attempt_arithmetic)

    def test_unknown_asset_type_is_not_auto_assigned(self):
        r = route_code(context(asset_type='unknown'))
        self.assertEqual(r.status, 'NOT_ASSESSED')

    def test_missing_component_id_prevents_route(self):
        r = route_code(context(component_id='   '))
        self.assertEqual(r.status, 'NEEDS_COMPONENT_IDENTIFICATION')

    def test_elbow_cannot_be_silently_routed_as_straight_pipe(self):
        r = route_code(context(geometry='elbow'))
        self.assertEqual(r.status, 'NOT_ASSESSED')
        self.assertEqual(r.candidate_rule_ids, ())

    def test_vessel_shell_requires_two_arithmetic_branches(self):
        r = route_code(context(asset_type='pressure_vessel', geometry='cylindrical_shell',
                               construction_code='ASME VIII-1', construction_edition='2025'))
        self.assertEqual(r.candidate_rule_ids, ('VIII_UG27_HOOP', 'VIII_UG27_LONG'))
        self.assertEqual(r.output_kind, 'VESSEL_COMPONENT_PRESSURE_CANDIDATE')

    def test_tank_scope_is_recognized_but_unimplemented(self):
        r = route_code(context(asset_type='storage_tank', geometry='shell_course',
                               construction_code='API 650', construction_edition='2025'))
        self.assertEqual(r.status, 'NOT_ASSESSED')
        self.assertFalse(r.can_attempt_arithmetic)

    def test_no_fallback_for_unsupported_vessel_geometry(self):
        r = route_code(context(asset_type='pressure_vessel', geometry='nozzle',
                               construction_code='ASME VIII-1', construction_edition='2025'))
        self.assertEqual(r.status, 'NOT_ASSESSED')

    def test_invalid_object_is_rejected(self):
        with self.assertRaises(TypeError):
            route_code({'construction_code': 'ASME B31.3'})


if __name__ == '__main__':
    unittest.main()
