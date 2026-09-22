#!/usr/bin/env python3
"""Run one deterministic Playwright smoke check against a browser-facing URL."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = SCRIPT_DIR / 'playwright.config.cjs'
PACKAGE_ROOT = REPO_ROOT
LOCAL_PLAYWRIGHT_CLI = PACKAGE_ROOT / 'node_modules' / '.bin' / 'playwright'
PLAYWRIGHT_BROWSERS_PATH = PACKAGE_ROOT / '.playwright-browsers'


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Load one URL in headless Chromium and check HTTP, DOM, and console errors.',
    )
    parser.add_argument('--url', required=True, help='HTTP(S) URL to verify.')
    parser.add_argument('--selector', default='body', help='CSS selector that must be visible.')
    parser.add_argument('--timeout-ms', type=int, default=20_000, help='Per-check timeout (default: 20000).')
    parser.add_argument('--output-dir', help='Failure artifact directory. A temporary directory is used by default.')
    return parser.parse_args()


def _validate_args(args):
    parsed = urlparse(str(args.url or '').strip())
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('--url must be an absolute http:// or https:// URL.')
    if not str(args.selector or '').strip():
        raise ValueError('--selector must not be empty.')
    if not 1_000 <= int(args.timeout_ms) <= 120_000:
        raise ValueError('--timeout-ms must be between 1000 and 120000.')


def _browser_executable_path(env):
    """Return the Chromium path expected by this project's pinned Playwright."""
    command = [
        'node',
        '-e',
        "const { chromium } = require('playwright'); process.stdout.write(chromium.executablePath());",
    ]
    result = subprocess.run(
        command,
        cwd=str(PACKAGE_ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return None
    return Path(result.stdout.strip()) if result.stdout.strip() else None


def _installation_error(expected_browser=None):
    details = [
        'browser verification unavailable: the project-local Playwright runtime is incomplete.',
        f'Required CLI: {LOCAL_PLAYWRIGHT_CLI}',
    ]
    if expected_browser:
        details.append(f'Required Chromium executable: {expected_browser}')
    details.extend([
        'Recovery:',
        f'  cd {PACKAGE_ROOT}',
        '  npm install',
        '  npm run playwright:install',
    ])
    return '\n'.join(details)


def main():
    args = _parse_args()
    try:
        _validate_args(args)
    except ValueError as exc:
        print(f'browser verification configuration error: {exc}', file=sys.stderr)
        return 2

    # Never fall back to a PATH/global CLI: its package version and browser
    # revision can drift independently from this repository.
    if not LOCAL_PLAYWRIGHT_CLI.is_file():
        print(_installation_error(), file=sys.stderr)
        return 127

    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        remove_on_success = False
    else:
        output_dir = Path(tempfile.mkdtemp(prefix='codex-browser-verify-'))
        remove_on_success = True

    env = os.environ.copy()
    env['PLAYWRIGHT_BROWSERS_PATH'] = str(PLAYWRIGHT_BROWSERS_PATH)
    env['CODEX_VERIFY_URL'] = str(args.url).strip()
    env['CODEX_VERIFY_SELECTOR'] = str(args.selector).strip()
    env['CODEX_VERIFY_TIMEOUT_MS'] = str(int(args.timeout_ms))
    expected_browser = _browser_executable_path(env)
    if not expected_browser or not expected_browser.is_file():
        print(_installation_error(expected_browser), file=sys.stderr)
        return 127

    command = [
        str(LOCAL_PLAYWRIGHT_CLI),
        'test',
        '--config',
        str(CONFIG_PATH),
        '--workers=1',
        '--retries=0',
        '--reporter=line',
        '--output',
        str(output_dir),
    ]
    result = subprocess.run(command, cwd=str(REPO_ROOT), env=env, check=False)
    if result.returncode == 0:
        if remove_on_success:
            shutil.rmtree(output_dir, ignore_errors=True)
        print(f'browser verification passed: {args.url} [{args.selector}]')
        return 0

    print(
        f'browser verification failed (exit {result.returncode}); failure artifacts: {output_dir}',
        file=sys.stderr,
    )
    return int(result.returncode or 1)


if __name__ == '__main__':
    raise SystemExit(main())
