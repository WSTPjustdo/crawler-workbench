import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
from playwright.async_api import async_playwright

async def main():
    output = Path(__file__).resolve().parents[1] / 'outputs/xianyu/details'
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://127.0.0.1:9237')
        page = await browser.contexts[0].new_page()
        for item_id in sys.argv[1:]:
            if not item_id.isdigit():
                raise ValueError('Numeric item IDs only')
            await page.goto('https://www.goofish.com/item?id=' + item_id,
                            wait_until='domcontentloaded', timeout=45000)
            await page.wait_for_timeout(4000)
            body = (await page.locator('body').inner_text()).split('为你推荐')[0]
            record = {'id': item_id, 'url': page.url,
                      'time': datetime.now().isoformat(timespec='seconds'), 'text': body}
            (output / (item_id + '.json')).write_text(json.dumps(record,
                ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(record, ensure_ascii=False), flush=True)
            await page.screenshot(path=str(output / (item_id + '.png')))
        await page.close()

if __name__ == '__main__':
    asyncio.run(main())
