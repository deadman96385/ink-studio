"""Request boundaries for the local editor, including DNS-rebinding protection."""
import json
import os
import re
from urllib.parse import urlsplit


def authority(value):
    if not isinstance(value, str) or not value or re.search(r'[\s\\/@?#,]', value):
        raise ValueError('Invalid request host.')
    parsed = urlsplit('//' + value)
    if parsed.username or parsed.password or not parsed.hostname:
        raise ValueError('Invalid request host.')
    host = parsed.hostname.lower().rstrip('.')
    port = parsed.port  # also rejects malformed and out-of-range ports
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('Invalid request host.')
    if ':' in host:
        import ipaddress
        host = str(ipaddress.IPv6Address(host))
        if not value.startswith('['):
            raise ValueError('IPv6 request hosts must be bracketed.')
    elif not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host):
        raise ValueError('Invalid request host.')
    return host, port


class RequestPolicy:
    def __init__(self, hosts):
        self.hosts = frozenset(hosts)

    @classmethod
    def from_environment(cls, bind_host, env=None):
        env = os.environ if env is None else env
        hosts = {'localhost', '127.0.0.1', '::1'}
        if bind_host not in ('', '0.0.0.0', '::'):
            hosts.add(authority('[' + bind_host + ']' if ':' in bind_host else bind_host)[0])
        # Preserve an explicitly configured reverse-proxy deployment. Forwarded
        # headers supplied by the client are never used to expand this list.
        for key in ('STUDIO_DESKTOP_URL',):
            value = env.get(key, '')
            if value:
                url = urlsplit(value)
                if url.scheme not in ('http', 'https') or not url.netloc:
                    raise ValueError(key + ' must be an HTTP(S) URL.')
                hosts.add(authority(url.netloc)[0])
        for value in env.get('STUDIO_ALLOWED_HOSTS', '').split(','):
            if value.strip():
                hosts.add(authority(value.strip())[0])
        return cls(hosts)

    def check(self, headers):
        values = headers.get_all('Host', [])
        if len(values) != 1:
            raise ValueError('Send one request host.')
        requested = authority(values[0])
        if requested[0] not in self.hosts:
            raise ValueError('This request host is not allowed.')
        origins = headers.get_all('Origin', [])
        if len(origins) > 1:
            raise ValueError('Send one request origin.')
        if origins:
            origin = urlsplit(origins[0])
            if origin.scheme not in ('http', 'https') or origin.path or origin.query or origin.fragment:
                raise ValueError('Cross-site requests are not allowed.')
            if authority(origin.netloc) != requested:
                raise ValueError('Cross-site requests are not allowed.')
        # Opening the editor through an ordinary external link remains allowed.
        # Embedded resources and fetches from an unrelated website are blocked.
        if headers.get('Sec-Fetch-Site', '').lower() in ('cross-site', 'same-site'):
            if not (headers.get('Sec-Fetch-Mode') == 'navigate' and headers.get('Sec-Fetch-Dest') == 'document'):
                raise ValueError('Cross-site requests are not allowed.')


class LocalRequestGuard:
    def parse_request(self):
        if not super().parse_request():
            return False
        try:
            self.server.request_policy.check(self.headers)
        except (ValueError, TypeError) as error:
            body = json.dumps({'error': str(error)}).encode('utf-8')
            self.close_connection = True
            self.send_response(403)
            for key, value in [('Content-Type', 'application/json'), ('Content-Length', str(len(body))),
                               ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                               ('Connection', 'close')]:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            return False
        return True
