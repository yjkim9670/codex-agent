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


def _node_modules_root(playwright_cli):
    resolved = Path(playwright_cli).resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name == 'node_modules':
            return parent
    return None


def main():
    args = _parse_args()
    try:
        _validate_args(args)
    except ValueError as exc:
        print(f'browser verification configuration error: {exc}', file=sys.stderr)
        return 2

    playwright_cli = shutil.which('playwright')
    if not playwright_cli:
        print(
            'browser verification unavailable: `playwright` was not found on PATH. '
            'Install the Playwright CLI and Chromium before retrying.',
            file=sys.stderr,
        )
        return 127

    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        remove_on_success = False
    else:
        output_dir = Path(tempfile.mkdtemp(prefix='codex-browser-verify-'))
        remove_on_success = True

    env = os.environ.copy()
    env['CODEX_VERIFY_URL'] = str(args.url).strip()
    env['CODEX_VERIFY_SELECTOR'] = str(args.selector).strip()
    env['CODEX_VERIFY_TIMEOUT_MS'] = str(int(args.timeout_ms))
    node_modules_root = _node_modules_root(playwright_cli)
    if node_modules_root:
        existing_node_path = env.get('NODE_PATH', '').strip()
        env['NODE_PATH'] = os.pathsep.join(
            item for item in (str(node_modules_root), existing_node_path) if item
        )

    command = [
        playwright_cli,
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
