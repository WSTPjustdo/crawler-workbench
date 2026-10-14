"""Small local trial; uses upstream crawler with bounded search settings."""
import asyncio
import base64
import os
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parent.parent
(workspace / 'outputs').mkdir(parents=True, exist_ok=True)
repo = workspace / "work/source/MediaCrawler-main"
os.chdir(repo)
sys.path.insert(0, str(repo))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(workspace / "work/browsers")

import config

config.ENABLE_CDP_MODE = False
config.HEADLESS = True
config.SAVE_LOGIN_STATE = True
config.CRAWLER_MAX_NOTES_COUNT = 20
config.MAX_CONCURRENCY_NUM = 1
config.ENABLE_GET_COMMENTS = False
config.ENABLE_GET_SUB_COMMENTS = False
config.ENABLE_GET_MEIDAS = False
config.CRAWLER_MAX_SLEEP_SEC = 3
config.KEYWORDS = "FDE 实习,AI 工作流 远程实习"
config.SORT_TYPE = "time_descending"
config.SAVE_DATA_OPTION = "jsonl"
config.SAVE_DATA_PATH = str(workspace / "work/crawl-data")

from tools import utils

def save_login_qrcode(encoded):
    target = workspace / "outputs/xhs-login.png"
    target.write_bytes(base64.b64decode(encoded.split(",", 1)[-1]))
    print("LOGIN_QR_READY: " + str(target), flush=True)

utils.show_qrcode = save_login_qrcode

import main

async def trial():
    try:
        await asyncio.wait_for(main.main(), timeout=480)
    except Exception:
        crawler = main.crawler
        page = getattr(crawler, 'context_page', None)
        if page:
            try:
                await page.screenshot(path=str(workspace / 'outputs/xhs-status.png'))
            except Exception:
                pass
        raise
    finally:
        await main.async_cleanup()

if __name__ == "__main__":
    asyncio.run(trial())
