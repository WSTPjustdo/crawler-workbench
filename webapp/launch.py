"""Start the local service and open it without changing shell execution policy."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

root = Path(__file__).resolve().parent.parent
(root / 'work').mkdir(parents=True, exist_ok=True)
(root / 'outputs').mkdir(parents=True, exist_ok=True)
url = 'http://127.0.0.1:8765'

def ready():
    try:
        with urlopen(url + '/api/state', timeout=1) as response:
            state = json.load(response)
        return 'status' in state and 'token' in state
    except Exception:
        return False

if not ready():
    env = {**os.environ, 'PYTHONUTF8': '1', 'CRAWLER_UI_PORT': '8765'}
    with (root / 'work/webapp.stdout.log').open('a') as out, (root / 'work/webapp.stderr.log').open('a') as err:
        process = subprocess.Popen([sys.executable, str(root / 'webapp/server.py')], cwd=root, env=env, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    for _ in range(30):
        if ready():
            break
        if process.poll() is not None:
            raise SystemExit('Service exited. See work/webapp.stderr.log.')
        time.sleep(.4)
if not ready():
    raise SystemExit('Service did not start. See work/webapp.stderr.log.')
webbrowser.open(url)
print('Ready: ' + url)
