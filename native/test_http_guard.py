"""Real HTTP requests exercise the local API boundary without an engine."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest
from http_guard import LocalRequestGuard, RequestPolicy


class Handler(LocalRequestGuard, BaseHTTPRequestHandler):
    calls = []
    def do_GET(self):
        self.calls.append(self.path)
        self.send_response(200);self.end_headers();self.wfile.write(b'ok')
    do_POST = do_GET
    def log_message(self, *args):
        pass


class RequestBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.request_policy = RequestPolicy.from_environment('0.0.0.0', {
            'STUDIO_DESKTOP_URL': 'https://studio.example.test:8843/studio/',
            'STUDIO_ALLOWED_HOSTS': 'embroidery.example.test,192.0.2.10'})
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self, hosts, extra=None, method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.putrequest(method, '/api/projects', skip_host=True)
        for host in hosts:
            connection.putheader('Host', host)
        for key, value in (extra or {}).items():
            connection.putheader(key, value)
        connection.endheaders()
        response = connection.getresponse();status=response.status;body=response.read()
        connection.close()
        return status, body
    def test_loopback_and_configured_proxy_hosts(self):
        for host in ('127.0.0.1:8801','localhost:8801','[::1]:8801','LOCALHOST:8801','localhost.:8801',
                     'studio.example.test:8844','embroidery.example.test','192.0.2.10:8797'):
            with self.subTest(host=host):self.assertEqual(self.request([host])[0],200)
    def test_rebinding_and_spoofed_forwarded_headers_are_blocked(self):
        before=len(Handler.calls)
        for host in ('evil.example:8801','localhost.evil.example','127.0.0.1.evil.example','2130706433','127.1','0.0.0.0'):
            with self.subTest(host=host):
                self.assertEqual(self.request([host],{'X-Forwarded-Host':'localhost:8801'})[0],403)
        self.assertEqual(len(Handler.calls),before)
    def test_ambiguous_and_malformed_hosts_are_blocked(self):
        for hosts in ([],['localhost','evil.example'],['localhost:99999'],['localhost:0'],
                      ['localhost:abc'],['user@localhost'],['localhost/anything'],['localhost,evil.example'],
                      ['::1'],['[::1]evil'],['localhost\\evil'],['localhost#evil']):
            with self.subTest(hosts=hosts):self.assertEqual(self.request(hosts)[0],403)
    def test_same_origin_clients_remain_supported(self):
        self.assertEqual(self.request(['127.0.0.1:8801'],{'Origin':'http://127.0.0.1:8801'},'POST')[0],200)
        self.assertEqual(self.request(['studio.example.test:8844'],{'Origin':'https://studio.example.test:8844'},'POST')[0],200)
        self.assertEqual(self.request(['localhost:8801'],method='POST')[0],200)
    def test_foreign_origins_cannot_read_or_write(self):
        for method in ('GET','POST'):
            for origin in ('https://evil.example','null','http://localhost:9999','http://localhost:8801/extra'):
                with self.subTest(method=method,origin=origin):
                    status,body=self.request(['localhost:8801'],{'Origin':origin},method)
                    self.assertEqual(status,403);self.assertIn('error',json.loads(body))
    def test_cross_site_fetch_is_blocked_but_editor_links_work(self):
        for site in ('cross-site','same-site'):
            self.assertEqual(self.request(['localhost:8801'],{'Sec-Fetch-Site':site,'Sec-Fetch-Mode':'no-cors','Sec-Fetch-Dest':'image'})[0],403)
            self.assertEqual(self.request(['localhost:8801'],{'Sec-Fetch-Site':site,'Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'})[0],200)
    def test_invalid_configuration_fails_closed(self):
        for env in ({'STUDIO_ALLOWED_HOSTS':'*'}, {'STUDIO_DESKTOP_URL':'javascript:bad()'}):
            with self.subTest(env=env), self.assertRaises(ValueError):RequestPolicy.from_environment('0.0.0.0',env)


if __name__=='__main__':unittest.main()
