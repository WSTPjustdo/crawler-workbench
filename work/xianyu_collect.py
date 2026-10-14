"""Collect visible search cards; no private API or messaging operations."""
import asyncio
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from urllib.parse import quote, urlparse, parse_qs

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/xianyu'
QUERIES = [
    'ps作业', 'pr作业', 'ai作业', '求做ps', '求做pr', '求做ai',
    'ps作业求助', 'pr作业求助', 'ai作业求助',
    '找人做海报', '找人剪辑作业', '求做作业',
    'Photoshop作业', 'Premiere作业', 'Illustrator作业',
    '有偿ps作业', '有偿pr作业', '有偿ai作业',
]
DEMAND = re.compile(r'求助|求做|求代|求帮|求个|求一|急求|找人|找个|找位|谁会|谁能|帮我|帮忙做|有没有|有偿求|需要.{0,12}(做|帮|剪|设计)|不会做')
SELLER = re.compile(r'接单|承接|代做|包修改|包满意|工作室|提供.{0,8}服务|本人.{0,8}(擅长|专业)|专业.{0,8}(制作|设计|剪辑)|价格优惠|经验丰富')


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queries', nargs='+')
    parser.add_argument('--name', default='search-results')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    coverage = []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://127.0.0.1:9237')
        page = await browser.contexts[0].new_page()
        for query in args.queries or QUERIES:
            try:
                await page.goto('https://www.goofish.com/search?q=' + quote(query),
                                wait_until='domcontentloaded', timeout=45000)
                for _ in range(12):
                    await page.wait_for_timeout(1000)
                    body = await page.locator('body').inner_text()
                    if await page.locator('a[href*="/item"]').count() or '暂无' in body or '没有找到' in body:
                        break
                if any(s in body for s in ['请完成安全验证', '拖动滑块', '访问过于频繁']):
                    coverage.append({'query': query, 'status': 'verification_required'})
                    print('STOP: verification required', flush=True)
                    break
                cards = await page.locator('a[href*="/item"]').evaluate_all(
                    '(els) => els.map(a => ({text:a.innerText,url:a.href}))')
                coverage.append({'query': query, 'cards': len(cards), 'page': 1,
                                 'time': datetime.now().isoformat(timespec='seconds'),
                                 'status': 'ok' if cards else 'empty_or_unloaded'})
                for card in cards:
                    item_id = parse_qs(urlparse(card['url']).query).get('id', [''])[0]
                    if not item_id:
                        continue
                    if item_id not in records:
                        records[item_id] = {'id': item_id, 'url': 'https://www.goofish.com/item?id=' + item_id,
                                            'text': card['text'], 'queries': []}
                    if query not in records[item_id]['queries']:
                        records[item_id]['queries'].append(query)
                (OUT / (args.name + '.json')).write_text(json.dumps(
                    {'coverage': coverage, 'records': list(records.values())},
                    ensure_ascii=False, indent=2), encoding='utf-8')
                print(f'{query}: {len(cards)} cards; {len(records)} unique', flush=True)
                await page.wait_for_timeout(1800)
            except Exception as exc:
                coverage.append({'query': query, 'status': 'error', 'error': str(exc)[:250]})
                print(f'{query}: {type(exc).__name__}', flush=True)
        candidates = []
        for record in records.values():
            record['demand_signals'] = list(dict.fromkeys(DEMAND.findall(record['text'])))
            record['seller_signals'] = list(dict.fromkeys(SELLER.findall(record['text'])))
            if record['demand_signals']:
                candidates.append(record)
        (OUT / (args.name + '.json')).write_text(json.dumps(
            {'coverage': coverage, 'records': list(records.values())},
            ensure_ascii=False, indent=2), encoding='utf-8')
        (OUT / (args.name + '-candidates.json')).write_text(json.dumps(candidates,
            ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'DONE: {len(records)} unique; {len(candidates)} candidates', flush=True)
        await page.close()


if __name__ == '__main__':
    asyncio.run(main())
