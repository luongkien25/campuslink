"""Hop dong HOT: do thi phu thuoc va ownership, chua thay Heat validate tren cum."""
from pathlib import Path
import unittest
import yaml

HEAT = Path(__file__).resolve().parents[1]


def load(name):
    return yaml.safe_load((HEAT / name).read_text())


def walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def dependencies(resources):
    graph = {}
    for name, resource in resources.items():
        explicit = resource.get('depends_on', [])
        found = set([explicit] if isinstance(explicit, str) else explicit)
        for node in walk(resource.get('properties', {})):
            if isinstance(node, dict):
                if 'get_resource' in node:
                    found.add(node['get_resource'])
                if 'get_attr' in node:
                    found.add(node['get_attr'][0])
        graph[name] = found
    return graph


def ancestors(graph, name, seen=None):
    seen = set() if seen is None else seen
    for dep in graph[name]:
        if dep not in seen:
            seen.add(dep)
            ancestors(graph, dep, seen)
    return seen


class AppStackTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HEAT / 'root.yaml').is_file(), 'root app chua implement')
        self.root = load('root.yaml')
        self.unit = load('app-unit.yaml')

    def test_member_requires_real_wait_and_delete_reverses_member_delay_server(self):
        r = self.unit['resources']; g = dependencies(r)
        self.assertIn('ready', ancestors(g, 'member'))
        self.assertIn('drain', ancestors(g, 'member'))
        self.assertIn('server', ancestors(g, 'drain'))
        self.assertEqual(r['drain']['properties']['actions'], ['DELETE'])
        self.assertEqual(r['ready']['type'], 'OS::Heat::WaitCondition')
        self.assertEqual(r['ready']['properties'], {'count': 1, 'handle': {'get_resource': 'handle'}, 'timeout': 300})
        self.assertEqual(r['handle']['properties']['signal_transport'], 'TOKEN_SIGNAL')
        for name in g:
            self.assertNotIn(name, ancestors(g, name), 'dependency cycle')

    def test_b_waits_for_entire_a_and_capacity_is_two_to_three(self):
        r = self.root['resources']; g = dependencies(r)
        self.assertIn('app_a', ancestors(g, 'asg_b'))
        asg = r['asg_b']['properties']
        self.assertEqual((asg['min_size'], asg['max_size'], asg['desired_capacity']), (1, 2, 1))
        self.assertEqual(asg['resource']['type'], 'app-unit.yaml')
        self.assertNotIn('handle', r)
        for key, adjustment in [('scale_out', 1), ('scale_in', -1)]:
            policy = r[key]['properties']
            self.assertEqual(policy['adjustment_type'], 'change_in_capacity')
            self.assertEqual(policy['scaling_adjustment'], adjustment)
            self.assertGreaterEqual(policy['cooldown'], 180)

    def test_ovn_tcp_private_app_external_data_and_safe_outputs(self):
        r = self.root['resources']; u = self.unit['resources']
        self.assertEqual(r['lb']['properties']['provider'], 'ovn')
        self.assertEqual(r['listener']['properties']['protocol_port'], 8080)
        self.assertEqual(r['pool']['properties']['lb_algorithm'], 'SOURCE_IP_PORT')
        self.assertEqual(r['monitor']['properties']['type'], 'TCP')
        all_resources = list(r.values()) + list(u.values())
        types = [v['type'] for v in all_resources]
        self.assertEqual(types.count('OS::Neutron::FloatingIP'), 1)
        self.assertFalse(set(types) & {'OS::Cinder::Volume', 'OS::Neutron::Net', 'OS::Neutron::Router', 'OS::Neutron::SecurityGroup'})
        self.assertEqual(u['server']['properties']['networks'], [{'port': {'get_resource': 'port'}}])
        self.assertEqual(u['server']['properties']['metadata']['campus_role'], 'app')
        for template in (self.root, self.unit):
            for name in ('bootstrap_credential_id', 'bootstrap_credential_secret'):
                self.assertTrue(template['parameters'][name]['hidden'])
            for node in walk(template.get('outputs', {})):
                if isinstance(node, dict) and 'get_attr' in node:
                    self.assertFalse(set(node['get_attr'][1:]) & {'token', 'endpoint', 'signal', 'curl_cli', 'user_data'})

    def test_nested_parameters_and_local_files_resolve(self):
        names = set(self.unit['parameters'])
        r = self.root['resources']
        for params in (r['app_a']['properties'], r['asg_b']['properties']['resource']['properties']):
            self.assertEqual(set(params), names)
        example = load('env.example.yaml')['parameters']
        self.assertEqual(set(example), set(self.root['parameters']))
        for name in ('root.yaml', 'app-unit.yaml'):
            template = load(name)
            for node in walk(template):
                if isinstance(node, dict) and 'get_file' in node:
                    path = (HEAT / node['get_file']).resolve()
                    self.assertTrue(path.is_file(), str(path))
                if isinstance(node, dict) and 'get_param' in node:
                    param = node['get_param']
                    self.assertIn(param if isinstance(param, str) else param[0],
                                  set(template['parameters']) | {'OS::stack_id', 'OS::stack_name', 'OS::project_id'})

    def test_pending_activation_and_failure_handlers_exist_for_every_layer(self):
        config = self.unit['resources']['config']['properties']['cloud_config']
        writes = {f['path']: f for f in config['write_files']}
        self.assertNotIn('/etc/campuslink/bootstrap.json', writes)
        self.assertEqual(writes['/etc/campuslink/bootstrap.pending.json']['permissions'], '0600')
        self.assertEqual(writes['/etc/campuslink/heat.pending.json']['permissions'], '0600')
        for unit in ('secrets', 'guard', 'shlink', 'ready'):
            self.assertIn('/etc/systemd/system/campuslink-' + unit + '.service.d/heat-failure.conf', writes)
        self.assertIn(['/usr/bin/python3', '-B', '/opt/campuslink/bootstrap/heat_bootstrap.py'], config['runcmd'])

    def test_diagnostic_ssh_groups_optional_and_only_used_on_owned_ports(self):
        self.assertEqual(self.root['parameters'].get('diagnostic_security_groups', {}).get('default'), [])
        groups = self.unit['resources']['port']['properties']['security_groups']
        self.assertEqual(groups, {'list_concat': [[{'get_param':'security_group'}], {'get_param':'diagnostic_security_groups'}]})
        writes = self.unit['resources']['config']['properties']['cloud_config']['write_files']
        self.assertNotIn({'get_param':'diagnostic_security_groups'}, list(walk(writes)))


if __name__ == '__main__':
    unittest.main()
