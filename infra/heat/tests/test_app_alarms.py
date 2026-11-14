"""Kiem payload alarm cua HOT; khong thay Heat validate/evaluation tren cum."""
from pathlib import Path
import unittest
import yaml

HEAT = Path(__file__).resolve().parents[1]


def render(value, params, conditions):
    if isinstance(value, list):
        return [render(v, params, conditions) for v in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {'get_param'}:
        return params[value['get_param']]
    if set(value) == {'equals'}:
        a, b = render(value['equals'], params, conditions); return a == b
    if set(value) == {'not'}:
        return not render(value['not'][0], params, conditions)
    if set(value) == {'and'}:
        return all(render(v, params, conditions) for v in value['and'])
    if set(value) == {'if'}:
        condition, yes, no = value['if']
        return render(yes if render(conditions[condition], params, conditions) else no, params, conditions)
    if set(value) == {'get_attr'}:
        return 'FAKE_ACTION_' + '_'.join(value['get_attr'])
    if set(value) == {'get_resource'}:
        return value['get_resource']
    if set(value) == {'get_param'}:
        return params[value['get_param']]
    if set(value) == {'str_replace'}:
        spec = value['str_replace']; text = spec['template']
        for key, replacement in render(spec['params'], params, conditions).items():
            text = text.replace(key, str(replacement))
        return text
    if set(value) == {'map_merge'}:
        raise AssertionError('unexpected schema')
    return {k: render(v, params, conditions) for k, v in value.items()}


class AlarmTests(unittest.TestCase):
    def setUp(self):
        path = HEAT/'alarms.yaml'
        self.assertTrue(path.exists(), 'alarm HOT chua implement')
        self.template = yaml.safe_load(path.read_text())
        self.root = yaml.safe_load((HEAT/'root.yaml').read_text())

    def alarm_payloads(self, **overrides):
        params = {k: v.get('default', 'FAKE_INPUT') for k, v in self.template['parameters'].items()}
        params.update(overrides)
        # Mapping chi la du lieu HOT, khong phai tinh nang Heat can mo phong.
        params['high_threshold'] = 36e9
        params['low_threshold'] = 15e9
        return render(self.template['resources'], params, self.template.get('conditions', {}))

    def test_default_has_no_enabled_evaluation_actions_or_secret_outputs(self):
        for resource in self.alarm_payloads().values():
            p = resource['properties']
            self.assertFalse(p['enabled'])
            self.assertEqual(p['alarm_actions'], [])
            self.assertEqual(p['ok_actions'], [])
            self.assertEqual(p['insufficient_data_actions'], [])
        for output in self.template['outputs'].values():
            self.assertEqual(set(output['value']), {'get_resource'})

    def test_shadow_evaluation_and_correct_high_low_windows_without_action(self):
        resources = self.alarm_payloads(evaluation_enabled=True)
        for name, operator, periods, threshold in [('cpu_high', 'gt', 2, 36e9), ('cpu_low', 'lt', 3, 15e9)]:
            p = resources[name]['properties']
            self.assertTrue(p['enabled'])
            self.assertEqual((p['comparison_operator'], p['evaluation_periods'], p['threshold']),
                             (operator, periods, threshold))
            self.assertEqual((p['granularity'], p['metric'], p['resource_type'], p['aggregation_method']),
                             (60, 'cpu', 'instance', 'rate:mean'))
            self.assertFalse(p['repeat_actions'])
            self.assertEqual(p['alarm_actions'], [])

    def test_action_requires_enabled_evaluation_and_both_private_targets(self):
        for params in ({'actions_enabled': True},
                       {'evaluation_enabled': True, 'actions_enabled': True, 'high_action': 'FAKE_HIGH'},):
            for r in self.alarm_payloads(**params).values():
                self.assertEqual(r['properties']['alarm_actions'], [])
        ready = self.alarm_payloads(evaluation_enabled=True, actions_enabled=True,
                                   high_action='FAKE_HIGH', low_action='FAKE_LOW')
        self.assertEqual(ready['cpu_high']['properties']['alarm_actions'], ['FAKE_HIGH'])
        self.assertEqual(ready['cpu_low']['properties']['alarm_actions'], ['FAKE_LOW'])
        for key in ('high_action', 'low_action'):
            self.assertTrue(self.template['parameters'][key]['hidden'])

    def test_root_blocks_unverified_project_units_or_auth_and_only_passes_actions_when_ready(self):
        params = {k: p.get('default', 'FAKE_INPUT') for k, p in self.root['parameters'].items()}
        def nested(**extra):
            return render(self.root['resources']['cpu_alarms']['properties'],
                          dict(params, **extra), self.root['conditions'])
        self.assertFalse(nested()['evaluation_enabled'])
        self.assertEqual(nested()['high_action'], '')
        flags = dict(alarms_enabled=True, telemetry_verified=True,
                     telemetry_project_id='a'*32, cpu_rate_semantics='delta-ns')
        self.assertTrue(nested(**flags)['evaluation_enabled'])
        self.assertEqual(nested(**flags)['high_action'], '')
        self.assertFalse(nested(**dict(flags, telemetry_verified=False))['evaluation_enabled'])
        self.assertFalse(nested(**dict(flags, cpu_rate_semantics='unverified'))['evaluation_enabled'])
        self.assertFalse(nested(**dict(flags, telemetry_project_id=''))['evaluation_enabled'])
        self.assertEqual(nested(**dict(flags, scaling_actions_enabled=True))['high_action'], '')
        ready = nested(**dict(flags, scaling_actions_enabled=True, scaling_action_transport='native'))
        self.assertEqual(ready['high_action'], 'FAKE_ACTION_scale_out_signal_url')
        self.assertEqual(ready['low_action'], 'FAKE_ACTION_scale_in_signal_url')
        ready = nested(**dict(flags, scaling_actions_enabled=True, scaling_action_transport='signed'))
        self.assertEqual(ready['high_action'], 'FAKE_ACTION_scale_out_alarm_url')

    def test_query_is_project_and_live_group_scoped_not_a_fixed_list_of_vm_ids(self):
        import json
        resources = self.alarm_payloads(project_id='a'*32, group='campuslink-app')
        expected = {'and': [{'=': {'server_group': 'campuslink-app'}},
                             {'=': {'project_id': 'a'*32}}, {'=': {'ended_at': None}}]}
        for resource in resources.values():
            self.assertEqual(json.loads(resource['properties']['query']), expected)


if __name__ == '__main__':
    unittest.main()
