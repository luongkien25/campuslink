"""Kiem thu hanh vi lab LB; khong ket noi OpenStack."""

import contextlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

import yaml


LAB = Path(__file__).resolve().parents[1]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def serving(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class StubTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((LAB / "stub.py").is_file(), "HTTP stub chua duoc trien khai")
        self.stub = load_module(LAB / "stub.py")

    def test_identifies_backend_on_root_and_health(self):
        with serving(self.stub.make_handler("app-a")) as url:
            for route in ("/", "/health"):
                with urlopen(url + route, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    body = json.load(response)
                self.assertEqual(body["service"], "campuslink-lb-stub")
                self.assertEqual(body["backend"], "app-a")
                self.assertTrue(body["hostname"])

    def test_does_not_impersonate_shlink_health_or_redirect(self):
        with serving(self.stub.make_handler("app-b")) as url:
            for route in ("/rest/health", "/unknown"):
                with self.assertRaises(HTTPError) as error:
                    urlopen(url + route, timeout=2)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()

    def test_rejects_invalid_backend_label(self):
        for backend in ("", "x\nINJECTED", "x" * 65):
            with self.subTest(backend=repr(backend)), self.assertRaises(ValueError):
                self.stub.make_handler(backend)


class SamplerTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((LAB / "sample_lb.py").is_file(), "Cong cu lay mau chua duoc trien khai")
        self.sampler = load_module(LAB / "sample_lb.py")

    def handler(self, bodies, status=200, content_type="application/json"):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            index = 0
            client_ports = set()

            def do_GET(self):
                type(self).client_ports.add(self.client_address[1])
                payload = bodies[type(self).index % len(bodies)]
                type(self).index += 1
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        return Handler

    def payload(self, backend):
        return json.dumps({"service": "campuslink-lb-stub", "backend": backend}).encode()

    def test_reports_both_backends_with_fresh_connections(self):
        handler = self.handler([self.payload("app-a"), self.payload("app-b")])
        with serving(handler) as url:
            report = self.sampler.sample(url, {"app-a", "app-b"}, 6, 1)
        self.assertTrue(report["passed"])
        self.assertEqual(report["counts"], {"app-a": 3, "app-b": 3})
        self.assertEqual(report["errors"], {})
        self.assertEqual(len(handler.client_ports), 6)

    def test_truncated_chunked_response_is_reported_without_aborting_run(self):
        class BrokenResponse(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                self.send_response(200)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(b"10\r\n{}\r\n")
                self.close_connection = True

            def log_message(self, *args):
                pass

        with serving(BrokenResponse) as url:
            report = self.sampler.sample(url, {"app-a"}, 2, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["errors"], {"connection_error": 2})

    def test_redirect_is_not_followed_or_counted_as_backend_evidence(self):
        class Redirect(BaseHTTPRequestHandler):
            requests = 0

            def do_GET(self):
                type(self).requests += 1
                self.send_response(302)
                self.send_header("Location", "/destination")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        with serving(Redirect) as url:
            report = self.sampler.sample(url, {"app-a"}, 2, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["errors"], {"HTTP_302": 2})
        self.assertEqual(Redirect.requests, 2)

    def test_truncated_content_length_never_counts_valid_json_as_success(self):
        payload = self.payload("app-a")

        class BrokenResponse(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload) + 100))
                self.end_headers()
                self.wfile.write(payload)
                self.close_connection = True

            def log_message(self, *args):
                pass

        with serving(BrokenResponse) as url:
            report = self.sampler.sample(url, {"app-a"}, 2, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["counts"], {})
        self.assertEqual(report["errors"], {"connection_error": 2})

    def test_fails_when_one_expected_backend_never_receives_traffic(self):
        with serving(self.handler([self.payload("app-a")])) as url:
            report = self.sampler.sample(url, {"app-a", "app-b"}, 3, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["missing"], ["app-b"])

    def test_does_not_accept_arbitrary_json_as_backend_evidence(self):
        cases = [b'{"backend":"app-a"}', self.payload("other"), b'not-json', b'[]', b'x' * 4097]
        for body in cases:
            with self.subTest(body=body[:30]):
                with serving(self.handler([body])) as url:
                    report = self.sampler.sample(url, {"app-a"}, 1, 1)
                self.assertFalse(report["passed"])
                self.assertEqual(sum(report["errors"].values()), 1)

    def test_http_error_does_not_count_as_success(self):
        with serving(self.handler([self.payload("app-a")], status=503)) as url:
            report = self.sampler.sample(url, {"app-a"}, 2, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["errors"], {"HTTP_503": 2})

    def test_refuses_secret_urls_and_unbounded_inputs_before_network(self):
        cases = [
            ("http://user:password@example.org/", {"a"}, 1, 1),
            ("file:///etc/passwd", {"a"}, 1, 1),
            ("http://example.org/?token=secret", {"a"}, 1, 1),
            ("http://example.org/", set(), 1, 1),
            ("http://example.org/", {"a"}, 0, 1),
            ("http://example.org/", {"a"}, 1, 0),
            ("http://example.org/", {"a"}, 1, float("nan")),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.sampler.sample(*args)

    def test_cli_exit_status_and_json_report(self):
        with serving(self.handler([self.payload("app-a")])) as url:
            result = subprocess.run(
                [sys.executable, str(LAB / "sample_lb.py"), url, "--expect", "app-a", "--expect", "app-b", "--requests", "2"],
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["missing"], ["app-b"])


class HeatContractTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((LAB / "root.yaml").is_file(), "Template lab chua duoc trien khai")
        self.root = yaml.safe_load((LAB / "root.yaml").read_text())
        self.unit = yaml.safe_load((LAB / "stub-unit.yaml").read_text())

    def test_lb_contract_uses_ovn_tcp_and_private_vms(self):
        resources = self.root["resources"]
        self.assertEqual(resources["lb"]["properties"]["provider"], "ovn")
        self.assertEqual(resources["listener"]["properties"]["protocol"], "TCP")
        self.assertEqual(resources["listener"]["properties"]["protocol_port"], 8080)
        self.assertEqual(resources["pool"]["properties"]["lb_algorithm"], "SOURCE_IP_PORT")
        self.assertEqual(resources["monitor"]["properties"]["type"], "TCP")
        # FIP duy nhat chi gan VIP, khong gan port cua VM.
        fips = [r for r in resources.values() if r["type"] == "OS::Neutron::FloatingIP"]
        self.assertEqual(len(fips), 1)
        self.assertEqual(fips[0]["properties"]["port_id"], {"get_attr": ["lb", "vip_port_id"]})
        self.assertNotIn("OS::Neutron::FloatingIP", [r["type"] for r in self.unit["resources"].values()])

    def test_backend_placement_and_octavia_mutations_are_serialized(self):
        resources = self.root["resources"]
        self.assertEqual(resources["app_a"]["properties"]["availability_zone"], {"get_param": "az_a"})
        self.assertEqual(resources["app_b"]["properties"]["availability_zone"], {"get_param": "az_b"})
        self.assertEqual(resources["app_b"]["depends_on"], "app_a")
        self.assertEqual(resources["app_a"]["depends_on"], "monitor")
        member = self.unit["resources"]["member"]["properties"]
        self.assertEqual(member["address"], {"get_attr": ["port", "fixed_ips", 0, "ip_address"]})
        self.assertEqual(self.unit["resources"]["member"]["depends_on"], "server")

    def test_nested_parameters_and_local_files_resolve(self):
        for name in ("app_a", "app_b"):
            resource = self.root["resources"][name]
            self.assertTrue((LAB / resource["type"]).is_file())
            self.assertEqual(set(resource["properties"]), set(self.unit["parameters"]))

        def visit(value, template):
            if isinstance(value, list):
                for item in value:
                    visit(item, template)
            elif isinstance(value, dict):
                for key, item in value.items():
                    if key == "get_file":
                        self.assertTrue((LAB / item).is_file(), item)
                    elif key in ("get_resource", "get_attr"):
                        target = item[0] if isinstance(item, list) else item
                        self.assertIn(target, template["resources"])
                    elif key == "get_param":
                        target = item[0] if isinstance(item, list) else item
                        self.assertIn(target, set(template["parameters"]) | {"OS::stack_name"})
                    visit(item, template)

        visit(self.root, self.root)
        visit(self.unit, self.unit)


if __name__ == "__main__":
    unittest.main()
