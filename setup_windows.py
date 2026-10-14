"""Create a fresh Windows runtime; optionally install the upstream XHS crawler."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
MEDIACRAWLER_REV = '156c602c8d689266e6c5e9130b36f0b70495f5f0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-xhs', action='store_true', help='Also install MediaCrawler for Xiaohongshu')
    args = parser.parse_args()
    if os.name != 'nt' or sys.version_info < (3, 11):
        raise SystemExit('Windows and Python 3.11+ are required.')
    if args.with_xhs and (not shutil.which('git') or not shutil.which('node')):
        raise SystemExit('Install Git and Node.js before using --with-xhs.')
    runtime = ROOT / 'work/mediacrawler-venv'
    python = runtime / 'Scripts/python.exe'
    for path in (ROOT / 'work', ROOT / 'outputs'):
        path.mkdir(parents=True, exist_ok=True)
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(runtime)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
    if args.with_xhs:
        source = ROOT / 'work/source/MediaCrawler-main'
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'init', str(source)], check=True)
            subprocess.run(['git', '-C', str(source), 'remote', 'add', 'origin',
                            'https://github.com/NanmiCoder/MediaCrawler.git'], check=True)
            subprocess.run(['git', '-C', str(source), 'fetch', '--depth', '1', 'origin', MEDIACRAWLER_REV], check=True)
            subprocess.run(['git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
        if not (source / 'requirements.txt').exists():
            raise SystemExit('MediaCrawler source is incomplete; inspect work/source/MediaCrawler-main before retrying.')
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(source / 'requirements.txt')], check=True)
        env = {**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': str(ROOT / 'work/browsers')}
        subprocess.run([str(python), '-m', 'playwright', 'install', 'chromium'], env=env, check=True)
    print('Setup complete. Double-click open-web.cmd to start the local UI.')


if __name__ == '__main__':
    main()
