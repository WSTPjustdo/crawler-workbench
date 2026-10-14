"""Read Xianyu's rendered pages using a dedicated, user-controlled browser."""
import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote, urlparse, parse_qs
from urllib.request import urlopen

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'http://127.0.0.1:9237'


def emit(message, **values):
    print(json.dumps(dict(event='xianyu', message=message, **values), ensure_ascii=False), flush=True)


def connected():
    try:
        with urlopen(ENDPOINT + '/json/version', timeout=1) as response:
            return bool(json.load(response).get('webSocketDebuggerUrl'))
    except Exception:
        return False


async def ensure_browser():
    if connected():
        return
    candidates = [Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
                  Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')]
    executable = next((p for p in candidates if p.exists()), None)
    if not executable:
        raise RuntimeError('未找到Chrome或Edge，请先安装浏览器。')
    subprocess.Popen([str(executable), '--remote-debugging-port=9237',
        '--remote-debugging-address=127.0.0.1', f'--user-data-dir={ROOT / "work/xianyu-browser-profile"}',
        '--no-first-run', '--no-default-browser-check', 'https://www.goofish.com/'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    for _ in range(30):
        await asyncio.sleep(.5)
        if connected():
            return
    raise RuntimeError('浏览器连接超时，请关闭独立的闲鱼窗口后重试。')


async def login_state(page):
    body = await page.locator('body').inner_text()
    if any(s in body for s in ('请完成安全验证', '拖动滑块', '访问过于频繁', '请向右滑动')):
        return 'verification'
    for label in ('登录', '立即登录'):
        nodes = page.get_by_text(label, exact=True)
        for i in range(await nodes.count()):
            if await nodes.nth(i).is_visible():
                return 'required'
    if '订单' in body or await page.locator('a[href*="/item"]').count():
        return 'ready'
    return 'unknown'


async def run(args):
    if args.action == 'check' and not connected():
        emit('闲鱼窗口未打开，请先点击“打开登录窗口”。', login='closed')
        return 0
    await ensure_browser()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(ENDPOINT)
        context = browser.contexts[0]
        login_page = next((page for page in context.pages if 'goofish.com' == urlparse(page.url).hostname or 'www.goofish.com' == urlparse(page.url).hostname), None)
        if args.action != 'search':
            if login_page is None:
                login_page = await context.new_page()
                await login_page.goto('https://www.goofish.com/', wait_until='domcontentloaded', timeout=45000)
            if args.action == 'open':
                await login_page.bring_to_front()
            await login_page.wait_for_timeout(2500)
            status = await login_state(login_page)
            message = {'ready': '页面显示已登录，可以开始采集；搜索时仍会再次检查。',
                       'required': '请在独立的闲鱼窗口完成登录，再点击“检查登录”。',
                       'verification': '请在闲鱼窗口手动完成平台验证，再检查登录。',
                       'unknown': '暂时无法确认登录状态，请等待页面加载后重试。'}[status]
            emit(message, login=status)
            return 0

        words = json.loads(args.keywords_json)
        output = ROOT / 'outputs/xianyu/runs' / (args.run_id + '.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        rows, coverage = {}, []
        page = await context.new_page()
        def save():
            tmp = output.with_suffix('.tmp')
            tmp.write_text(json.dumps(dict(run_id=args.run_id, coverage=coverage, records=list(rows.values())),
                                      ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(output)
        save()
        for index, query in enumerate(words):
            emit(f'正在搜索“{query}”的第一页…', completed=index, total=len(words), count=len(rows))
            try:
                await page.goto('https://www.goofish.com/search?q=' + quote(query), wait_until='domcontentloaded', timeout=45000)
                for _ in range(15):
                    await page.wait_for_timeout(1000)
                    body = await page.locator('body').inner_text()
                    if await page.locator('a[href*="/item"]').count() or any(s in body for s in ('暂无宝贝', '没有找到', '立即登录', '请完成安全验证')):
                        break
                status = await login_state(page)
                if status in ('required', 'verification'):
                    coverage.append(dict(query=query, page=1, status=status, cards=0))
                    save()
                    await page.bring_to_front()
                    emit('需要登录或平台验证，请在闲鱼窗口处理后重新开始；已采集结果保留。', login=status)
                    return 2
                cards = await page.locator('a[href*="/item"]').evaluate_all('(els)=>els.map(a=>({text:a.innerText,url:a.href}))')
                stamp = datetime.now().astimezone().isoformat(timespec='seconds')
                for card in cards:
                    parsed = urlparse(card['url'])
                    item_id = parse_qs(parsed.query).get('id', [''])[0]
                    if not item_id.isdigit() or parsed.hostname not in ('www.goofish.com', 'goofish.com'):
                        continue
                    row = rows.setdefault(item_id, dict(id=item_id, text=card['text'], queries=[], collected_at=stamp))
                    if query not in row['queries']:
                        row['queries'].append(query)
                coverage.append(dict(query=query, page=1, status='ok' if cards else 'empty_or_unloaded', cards=len(cards), time=stamp))
                save()
                emit(f'“{query}”：读取{len(cards)}条；本次去重后{len(rows)}条。' + ('未读到结果，可能为空或未加载。' if not cards else ''),
                     login=status, completed=index + 1, total=len(words), count=len(rows))
                await page.wait_for_timeout(2000)
            except Exception:
                coverage.append(dict(query=query, page=1, status='error', cards=0))
                save()
                emit(f'“{query}”读取失败，已保留结果，请稍后重试。', completed=index + 1)
        await page.close()
        uncertain = sum(c['status'] != 'ok' for c in coverage)
        emit(f'采集结束：{len(rows)}条去重结果，{uncertain}组搜索为空或未能确认。新结果仅做规则初筛，需核对原帖。', completed=len(words), count=len(rows))
        return 0 if not any(c['status'] == 'error' for c in coverage) else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['open', 'check', 'search'])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--keywords-json', default='[]')
    args = parser.parse_args()
    try:
        code = asyncio.run(asyncio.wait_for(run(args), timeout=600))
    except Exception:
        emit('连接或采集失败，请检查闲鱼窗口、网络与登录状态后重试；已保存结果保留。')
        code = 1
    raise SystemExit(code)
