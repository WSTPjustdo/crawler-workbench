"""Portable checks: no account, network crawler, or private dataset required."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'webapp'))
import server
import xianyu


class RepositoryTests(unittest.TestCase):
    def test_empty_data_and_deduplication(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(xianyu, 'OUT', Path(directory)):
            self.assertEqual(xianyu.records(), [])
            runs = Path(directory) / 'runs'
            runs.mkdir()
            for index, query in enumerate(['ps', 'pr']):
                (runs / f'{index}.json').write_text(json.dumps({'records': [
                    {'id': '123', 'text': '求帮忙做海报', 'queries': [query]},
                    {'id': 'invalid', 'text': 'invalid', 'queries': []}]}), encoding='utf-8')
            rows = xianyu.records()
            self.assertEqual(len(rows), 1)
            self.assertEqual(set(rows[0]['queries']), {'ps', 'pr'})
            self.assertEqual(rows[0]['url'], 'https://www.goofish.com/item?id=123')

    def test_keywords(self):
        self.assertEqual(xianyu.validate_keywords('ps，pr\nps'), ['ps', 'pr'])
        for value in ['', None, ['ps'], 'a'*601, ','.join(map(str, range(11)))]:
            with self.assertRaises(ValueError):
                xianyu.validate_keywords(value)

    def test_process_completion_and_login_failure(self):
        original = dict(xianyu.STATE)
        try:
            process = MagicMock()
            process.stdout = iter([json.dumps(dict(event='xianyu', login='required', message='请登录'))])
            process.wait.return_value = 2
            xianyu.STATE.update(status='running', events=[])
            xianyu.watch(process)
            self.assertEqual(xianyu.STATE['status'], 'needs_login')
            xianyu.STATE['status'] = 'stopping'
            process.stdout = iter([])
            xianyu.watch(process)
            self.assertEqual(xianyu.STATE['status'], 'stopped')
        finally:
            xianyu.STATE.clear()
            xianyu.STATE.update(original)

    def test_fresh_server_and_request_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            with patch.object(server, 'PORT', httpd.server_port), patch.object(server, 'ROOT', root), \
                 patch.object(server, 'STATIC', root), patch.object(xianyu, 'OUT', root / 'outputs'):
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                base = f'http://127.0.0.1:{httpd.server_port}'
                try:
                    for path in ['/api/jobs', '/api/notes', '/api/xianyu/records']:
                        with urlopen(base + path) as response:
                            self.assertEqual(json.load(response), [])
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(base + '/api/xianyu/open', data=b'{}'))
                    self.assertEqual(error.exception.code, 403)
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(base + '/api/start', data=b'{"keywords":"test"}',
                                        headers={'X-Local-Token': server.TOKEN}))
                    self.assertEqual(error.exception.code, 400)
                    with self.assertRaises(HTTPError) as error:
                        urlopen(base + '/work/xianyu-browser-profile/Cookies')
                    self.assertEqual(error.exception.code, 404)
                finally:
                    httpd.shutdown()
                    httpd.server_close()


if __name__ == '__main__':
    unittest.main()
