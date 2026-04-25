"""Compatibility package for the renamed Codex Workbench web app directory.

The implementation lives in ``codex-web-app/`` so the on-disk folder can keep
the requested name.  Python package imports still use ``codex_agent.*`` because
hyphens are not valid in import names.
"""

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent / "codex-web-app"

if not _PACKAGE_DIR.is_dir():
    raise ImportError(f"Codex web app package directory not found: {_PACKAGE_DIR}")

__path__ = [str(_PACKAGE_DIR)]
