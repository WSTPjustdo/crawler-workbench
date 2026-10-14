"""Open a dedicated local browser and inspect visible Xianyu search content."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
from urllib.parse import quote
from urllib.request import urlopen

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
PORT = 9237
ENDPOINT = f"http://127.0.0.1:{PORT}"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keyword', default='PS 作业 求助')
    parser.add_argument('--navigate', action='store_true')
    args = parser.parse_args()
    launched = False
    try:
        with urlopen(ENDPOINT + '/json/version', timeout=2) as response:
            json.load(response)
    except Exception:
        chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        profile = ROOT / 'work/xianyu-browser-profile'
        subprocess.Popen([
            str(chrome), f'--remote-debugging-port={PORT}',
            '--remote-debugging-address=127.0.0.1',
            f'--user-data-dir={profile}', '--no-first-run',
            '--no-default-browser-check', 'https://www.goofish.com/',
        ], creationflags=subprocess.CREATE_NO_WINDOW,
           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        launched = True
        await asyncio.sleep(4)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(ENDPOINT)
        context = browser.contexts[0]
        page = next((x for x in context.pages if 'goofish.com' in x.url), None)
        if page is None:
            page = await context.new_page()
        if launched or args.navigate or 'goofish.com' not in page.url:
            await page.goto('https://www.goofish.com/search?q=' + quote(args.keyword),
                            wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(5000)
        output = ROOT / 'outputs/xianyu'
        output.mkdir(parents=True, exist_ok=True)
        text = await page.locator('body').inner_text()
        links = await page.locator('a[href*="/item"]').evaluate_all(
            '(els) => els.map(a => ({text:a.innerText,url:a.href}))')
        snapshot = {'url': page.url, 'title': await page.title(),
                    'visible_text': text, 'item_links': links}
        (output / 'search-probe.json').write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
        await page.screenshot(path=str(output / 'search-probe.png'))
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        # Disconnect only: leave the dedicated browser available for manual login.


if __name__ == '__main__':
    asyncio.run(main())
