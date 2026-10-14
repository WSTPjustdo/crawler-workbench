"""Local, single-user UI for the existing bounded MediaCrawler runner."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import xianyu

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).parent / 'static'
TOKEN = secrets.token_urlsafe(32)
PORT = int(os.environ.get('CRAWLER_UI_PORT', '8765'))
LOCK = threading.Lock()
PROCESS = None
STATE = {'status': 'idle', 'message': '就绪，可以开始新的搜索', 'started': None, 'keywords': '', 'events': [], 'exit_code': None}


def collect_notes():
    rows = {}
    for file in sorted((ROOT / 'work/crawl-data').rglob('*contents*.jsonl')):
        for line in file.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
                if not row.get('note_id'):
                    continue
                stamp = row.get('time')
                date = datetime.fromtimestamp(stamp / 1000, timezone(timedelta(hours=8))).isoformat() if isinstance(stamp, (int, float)) else str(stamp or '')
                url = row.get('note_url') or f"https://www.xiaohongshu.com/explore/{row['note_id']}"
                if urlparse(url).scheme != 'https' or urlparse(url).hostname not in ('www.xiaohongshu.com', 'xiaohongshu.com'):
                    url = f"https://www.xiaohongshu.com/explore/{row['note_id']}"
                rows[row['note_id']] = {'id': row['note_id'], 'title': row.get('title') or '无标题', 'keyword': row.get('source_keyword') or '', 'published': date, 'url': url}
            except (ValueError, TypeError, OverflowError):
                # A writer may currently be appending the last JSONL line.
                continue
    return sorted(rows.values(), key=lambda r: r['published'], reverse=True)


def validate_keywords(value):
    if not isinstance(value, str) or len(value) > 180:
        raise ValueError('请输入不超过 180 字的关键词')
    words = list(dict.fromkeys(w.strip() for w in value.replace('，', ',').replace('\n', ',').split(',') if w.strip()))
    if not 1 <= len(words) <= 3 or any(len(w) > 60 for w in words):
        raise ValueError('每次请输入 1–3 组关键词，每组不超过 60 字')
    if any(ord(c) < 32 for w in words for c in w):
        raise ValueError('关键词含有不支持的控制字符')
    return ','.join(words)


def event(message):
    STATE['message'] = message
    STATE['events'].append({'time': time.strftime('%H:%M:%S'), 'message': message})
    STATE['events'] = STATE['events'][-30:]


def watch(process):
    # Raw crawler output may contain account/session data: expose only fixed messages.
    for line in process.stdout:
        message = None
        if 'LOGIN_QR_READY:' in line:
            message = '请用小红书 App 扫描页面二维码，并在手机上确认'
        elif 'Login successful' in line or 'Login success' in line:
            message = '登录成功，继续搜索'
        elif 'Search Xiaohongshu keyword' in line or 'search keyword' in line.lower():
            message = '正在搜索并采集帖子'
        elif 'store_content' in line:
            message = '已收到帖子，正在保存结果'
        if message:
            with LOCK:
                if not STATE['events'] or STATE['events'][-1]['message'] != message:
                    event(message)
    code = process.wait()
    with LOCK:
        STATE['exit_code'] = code
        if STATE['status'] == 'stopping':
            STATE['status'] = 'stopped'
            event('任务已停止，已保存的帖子仍可查看')
        else:
            STATE['status'] = 'completed' if code == 0 else 'failed'
            event('搜索完成，帖子库已更新' if code == 0 else f'本次运行未完成（退出码 {code}）；可能是登录、网络或平台验证问题。已保存的帖子仍可查看。')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, payload, status=200, mime='application/json; charset=utf-8'):
        body = json.dumps(payload, ensure_ascii=False).encode() if mime.startswith('application/json') else payload
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def local_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{PORT}', f'localhost:{PORT}')

    def do_GET(self):
        if not self.local_host():
            return self.send({'error': '仅支持本机访问'}, 403)
        path = urlparse(self.path).path
        if path == '/api/state':
            with LOCK:
                result = dict(STATE)
                qr = ROOT / 'outputs/xhs-login.png'
                result['qr'] = qr.stat().st_mtime if STATE['status'] == 'running' and qr.exists() and qr.stat().st_mtime >= (STATE['started'] or time.time()) else None
                result['token'] = TOKEN
                self.send(result)
        elif path == '/api/xianyu/state':
            self.send(xianyu.state())
        elif path == '/api/xianyu/records':
            self.send(xianyu.records())
        elif path == '/api/notes':
            self.send(collect_notes())
        elif path == '/api/jobs':
            self.send(xianyu.read_json(STATIC / 'jobs.json', []))
        else:
            files = {'/xianyu.js': (STATIC / 'xianyu.js', 'text/javascript; charset=utf-8'), '/': (STATIC / 'index.html', 'text/html; charset=utf-8'), '/app.js': (STATIC / 'app.js', 'text/javascript; charset=utf-8'), '/style.css': (STATIC / 'style.css', 'text/css; charset=utf-8'), '/qr.png': (ROOT / 'outputs/xhs-login.png', 'image/png'), '/report.md': (ROOT / 'outputs/AI企业交付与远程实习岗位.md', 'text/plain; charset=utf-8')}
            if path not in files or not files[path][0].exists():
                return self.send({'error': '未找到页面'}, 404)
            file, mime = files[path]
            self.send(file.read_bytes(), mime=mime)

    def do_POST(self):
        global PROCESS
        origin = self.headers.get('Origin')
        if not self.local_host() or self.headers.get('X-Local-Token') != TOKEN or (origin and origin not in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}')):
            return self.send({'error': '请从本地网页操作'}, 403)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError('请求大小不正确')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('请求格式不正确')
        except (ValueError, TypeError):
            return self.send({'error': '请求格式不正确'}, 400)
        path = urlparse(self.path).path
        if path.startswith('/api/xianyu/'):
            action = path.rsplit('/', 1)[-1]
            try:
                if action == 'stop':
                    xianyu.stop()
                else:
                    xianyu.start(action, data.get('keywords'))
                return self.send({'ok': True})
            except ValueError as exc:
                return self.send({'error': str(exc)}, 400)
            except RuntimeError as exc:
                return self.send({'error': str(exc)}, 409)
            except OSError:
                return self.send({'error': '无法启动闲鱼采集，请检查本地Python环境'}, 500)
        if path == '/api/start':
            if not (ROOT / 'work/source/MediaCrawler-main/main.py').exists():
                return self.send({'error': '小红书采集依赖尚未安装，请运行 python setup_windows.py --with-xhs'}, 400)
            try:
                keywords = validate_keywords(data.get('keywords'))
            except ValueError as exc:
                return self.send({'error': str(exc)}, 400)
            with LOCK:
                if STATE['status'] in ('running', 'stopping'):
                    return self.send({'error': '已有任务运行中，请等待完成'}, 409)
                command = [str(ROOT / 'work/mediacrawler-venv/Scripts/python.exe'), '-u', str(ROOT / 'work/run_mediacrawler.py'), '--platform', 'xhs', '--lt', 'qrcode', '--type', 'search', '--keywords', keywords]
                env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
                try:
                    PROCESS = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                except OSError:
                    return self.send({'error': '无法启动爬虫，请检查本地 Python 环境是否完整'}, 500)
                STATE.update(status='running', started=time.time(), keywords=keywords, events=[], exit_code=None)
                event('正在启动浏览器，首次启动可能需要一些时间')
                threading.Thread(target=watch, args=(PROCESS,), daemon=True).start()
            self.send({'ok': True})
        elif path == '/api/stop':
            with LOCK:
                process = PROCESS
                if not process or process.poll() is not None or STATE['status'] != 'running':
                    return self.send({'error': '当前没有正在运行的任务'}, 409)
                STATE['status'] = 'stopping'
                event('正在停止当前任务')
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                process.terminate()
            self.send({'ok': True})
        else:
            self.send({'error': '未知操作'}, 404)


if __name__ == '__main__':
    print(f'Open http://127.0.0.1:{PORT}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
