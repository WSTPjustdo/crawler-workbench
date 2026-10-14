"""Local Xianyu job lifecycle and searchable historical records."""
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/xianyu'
LOCK = threading.Lock()
PROCESS = None
STATE = dict(status='idle', message='先打开闲鱼登录窗口，再检查登录状态。', login='unknown',
             completed=0, total=0, count=0, run_id=None, events=[])


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return fallback


def classify(text):
    demand = re.search(r'求助|求做|求代做|求帮|求一个|求个|急求|找人|找个|谁会|谁能|帮我|有没有人|求指导|求教学|需要绘制|急招', text)
    seller = re.search(r'接单|承接|包修改|包满意|工作室|一校一[卖出]|下单流程|拍下秒发|可接急单|我提供|提供.{0,8}服务', text)
    if demand and seller:
        return '待判断', '同时出现需求与服务广告用语，请核对原帖。'
    if seller:
        return '疑似广告', '包含接单、出售或服务用语，规则初筛。'
    if demand:
        return '疑似需求', '包含求助或委托用语，尚未核对身份及用途。'
    return '待判断', '仅凭搜索摘要无法判断，请核对原帖。'


def records():
    merged = {}
    sources = [(OUT / 'all-search-records.json', None)]
    sources += [(path, path.stem) for path in sorted((OUT / 'runs').glob('*.json'))]
    for path, run_id in sources:
        data = read_json(path, [])
        rows = data.get('records', []) if isinstance(data, dict) else data
        for raw in rows:
            item_id = str(raw.get('id', ''))
            if not item_id.isdigit():
                continue
            old = merged.get(item_id, {})
            text = str(raw.get('text', ''))
            category, reason = classify(text)
            merged[item_id] = dict(id=item_id, title=text.split('\n')[0][:180] or '无标题',
                text=text, url=f'https://www.goofish.com/item?id={item_id}',
                queries=sorted(set(old.get('queries', []) + raw.get('queries', []))),
                runs=sorted(set(old.get('runs', []) + ([run_id] if run_id else []))),
                collected_at=raw.get('collected_at', old.get('collected_at', '')),
                category=category, reason=reason, budget='', reviewed_at='', review_note='')
    for lead in read_json(OUT / 'reviewed-leads.json', {}).get('reviewed_leads', []):
        item_id = lead.get('id')
        if item_id not in merged:
            continue
        row = merged[item_id]
        row.update(title=lead['title'], category='历史已核对',
                   reason=lead['category'], budget=lead['budget'], reviewed_at=lead['verified_at'],
                   review_note=lead['note'], location=lead['location'],
                   requirement=lead['requirement'])
    return sorted(merged.values(), key=lambda row: (row['collected_at'], row['reviewed_at']), reverse=True)


def state():
    with LOCK:
        return {**STATE, 'events': list(STATE['events'])}


def event(message):
    STATE['message'] = message
    STATE['events'] = (STATE['events'] + [dict(time=time.strftime('%H:%M:%S'), message=message)])[-30:]


def validate_keywords(value):
    if not isinstance(value, str) or len(value) > 600:
        raise ValueError('关键词总长度不能超过600字')
    words = list(dict.fromkeys(w.strip() for w in re.split('[,，\n]', value) if w.strip()))
    if not 1 <= len(words) <= 10 or any(len(w) > 60 or any(ord(c) < 32 for c in w) for w in words):
        raise ValueError('请输入1–10组关键词，每组不超过60字，用逗号或换行分隔')
    return words


def watch(process):
    for line in process.stdout:
        try:
            update = json.loads(line)
        except ValueError:
            continue
        if not isinstance(update, dict) or update.get('event') != 'xianyu':
            continue
        with LOCK:
            for key in ('login', 'completed', 'total', 'count'):
                if key in update:
                    STATE[key] = update[key]
            if update.get('message'):
                event(update['message'])
    code = process.wait()
    with LOCK:
        if STATE['status'] == 'stopping':
            STATE['status'] = 'stopped'
            event('已停止，已经采集的结果已保留。')
        elif code == 0:
            STATE['status'] = 'completed'
        else:
            STATE['status'] = 'needs_login' if STATE['login'] == 'required' else 'failed'
            if not STATE['events']:
                event('运行失败，请检查浏览器、网络后重试。')


def start(action, keywords=None):
    global PROCESS
    if action not in ('open', 'check', 'search'):
        raise ValueError('不支持的操作')
    words = validate_keywords(keywords) if action == 'search' else []
    with LOCK:
        if STATE['status'] in ('running', 'stopping'):
            raise RuntimeError('闲鱼任务正在运行，请等待或先停止')
        run_id = time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6]
        command = [str(ROOT / 'work/mediacrawler-venv/Scripts/python.exe'), '-u',
                   str(ROOT / 'work/xianyu_web_worker.py'), action, '--run-id', run_id]
        if words:
            command += ['--keywords-json', json.dumps(words, ensure_ascii=False)]
        PROCESS = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        STATE.update(status='running', completed=0, total=len(words), count=0, events=[],
                     run_id=run_id if action == 'search' else STATE['run_id'])
        event('正在启动闲鱼搜索…' if words else '正在连接闲鱼浏览器…')
        threading.Thread(target=watch, args=(PROCESS,), daemon=True).start()


def stop():
    with LOCK:
        if STATE['status'] != 'running' or PROCESS is None or PROCESS.poll() is not None:
            raise RuntimeError('当前没有运行中的闲鱼任务')
        STATE['status'] = 'stopping'
        event('正在停止采集…')
        # Only terminate the worker; retain the user's login browser.
        PROCESS.terminate()
