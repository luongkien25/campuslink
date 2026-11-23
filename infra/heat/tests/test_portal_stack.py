"""Kiem do thi Heat rieng cua portal va hop dong bootstrap."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

HEAT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HEAT / 'bootstrap'))


class PortalStackTests(unittest.TestCase):
    def setUp(self):
        self.hot = yaml.safe_load((HEAT / 'portal-stack.yaml').read_text())
        self.resources = self.hot['resources']

    def test_portal_has_one_private_vm_and_one_isolated_lb(self):
        expected = {
            'port': 'OS::Neutron::Port', 'config': 'OS::Heat::CloudConfig',
            'server': 'OS::Nova::Server', 'lb': 'OS::Octavia::LoadBalancer',
            'listener': 'OS::Octavia::Listener', 'pool': 'OS::Octavia::Pool',
            'monitor': 'OS::Octavia::HealthMonitor', 'member': 'OS::Octavia::PoolMember',
            'vip_fip': 'OS::Neutron::FloatingIP',
        }
        self.assertEqual({k: r['type'] for k, r in self.resources.items()}, expected)
        props = {k: r['properties'] for k, r in self.resources.items()}
        self.assertEqual(props['server']['networks'], [{'port': {'get_resource': 'port'}}])
        self.assertEqual(props['lb']['provider'], 'ovn')
        self.assertEqual(props['vip_fip']['port_id'], {'get_attr': ['lb', 'vip_port_id']})
        self.assertEqual(props['vip_fip']['floating_ip_address'], {'get_param': 'portal_fip_address'})
        self.assertEqual(props['listener']['protocol'], 'TCP')
        self.assertEqual(props['listener']['protocol_port'], 8081)
        self.assertEqual(props['pool']['lb_algorithm'], 'SOURCE_IP_PORT')
        self.assertEqual(props['monitor']['type'], 'TCP')
        self.assertEqual(props['member']['pool'], {'get_resource': 'pool'})
        self.assertEqual(props['member']['protocol_port'], 8081)
        self.assertIn('monitor', self.resources['member']['depends_on'])
        self.assertNotIn('server_group', props['server'].get('metadata', {}))

    def test_digest_is_required_and_bootstrap_material_is_hidden(self):
        params = self.hot['parameters']
        image = 'ghcr.io/dqh1215/campus-portal'
        pattern = params['portal_image_ref']['constraints'][0]['allowed_pattern']
        self.assertIsNotNone(re.fullmatch(pattern, image + '@sha256:' + 'a' * 64))
        for value in (image + ':latest', image + '@sha256:abc', 'other/' + image):
            self.assertIsNone(re.fullmatch(pattern, value))
        for key in ('bootstrap_credential_id', 'bootstrap_credential_secret'):
            self.assertTrue(params[key]['hidden'])
            self.assertNotIn('default', params[key])
            self.assertNotIn(key, repr(self.hot['outputs']))
        for item in self.resources['config']['properties']['cloud_config']['write_files']:
            if 'get_file' in item['content']:
                self.assertTrue((HEAT / item['content']['get_file']).is_file())


class PortalBootstrapTests(unittest.TestCase):
    def setUp(self):
        import portal_bootstrap
        self.boot = portal_bootstrap
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.config = {
            'credential_id': 'a' * 32, 'credential_secret': 'boot-sample-not-live',
            'keystone_url': 'http://10.11.0.10/identity',
            'swift_url': 'http://10.11.0.10:8080/v1/AUTH_test',
            'shlink_api_url': 'http://10.20.0.203:8080',
            'portal_image_ref': 'ghcr.io/dqh1215/campus-portal@sha256:' + 'a' * 64,
        }
        self.payload = {
            'portal_db_url': b'postgresql://campus_portal:sample@10.20.0.10/campus_portal',
            'portal_secret_key': b'portal-secret-sample-value',
            'redis_servers': b'tcp://default:redis-sample@10.20.0.10:6379',
            'swift_app_cred': b'id=' + b'b' * 32 + b'\nsecret=swift-secret-sample-value',
        }

    def request(self, method, url, *args, **kwargs):
        if method == 'POST':
            return b'{"token": {}}', 'X-Subject-Token: sample-token'
        self.assertEqual(kwargs['token'], 'sample-token')
        return self.payload[url.rsplit('/', 1)[-1]], ''

    def test_exact_objects_mounted_read_only_without_plaintext_in_argv(self):
        with patch.object(self.boot, 'request', side_effect=self.request) as request, patch.object(os, 'chown'):
            secrets = self.boot.fetch(self.config, self.state)
        self.assertEqual([args.args[1].split('/app/')[-1] for args in request.call_args_list[1:]], list(self.payload))
        argv = self.boot.docker_args(self.config, secrets)
        text = json.dumps(argv)
        for name, content in self.payload.items():
            self.assertNotIn(content.decode(), text)
            self.assertIn('/run/secrets/' + name + ',readonly', text)
        self.assertIn('1002:1002', argv)
        self.assertIn('8081:8081', argv)
        self.assertIn('QR_STORAGE=swift', argv)
        self.assertNotIn('boot-sample-not-live', text)
        self.assertTrue(all((secrets / n).stat().st_mode & 0o777 == 0o440 for n in self.payload))

    def test_bad_last_object_does_not_publish_a_partial_set(self):
        self.payload['swift_app_cred'] = b'<error page>'
        with patch.object(self.boot, 'request', side_effect=self.request), patch.object(os, 'chown'):
            with self.assertRaises(self.boot.Failure):
                self.boot.fetch(self.config, self.state)
        self.assertTrue(all(not (self.state / n).exists() for n in self.payload))

    def test_unpinned_image_and_same_host_or_public_http_endpoint_are_rejected(self):
        for change in (
            {'portal_image_ref': 'ghcr.io/dqh1215/campus-portal:latest'},
            {'shlink_api_url': 'http://127.0.0.1:8080'},
            {'shlink_api_url': 'http://example.org'},
        ):
            with self.subTest(change=change), self.assertRaises(self.boot.Failure):
                self.boot.settings(dict(self.config, **change))
