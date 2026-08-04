#!/usr/bin/env python3
"""Check or deploy the supported z00_sync_git.py variants from this folder."""

from __future__ import annotations

import argparse
import ast
import re
import shutil
import sys
from pathlib import Path


SOURCE = Path(__file__).resolve().parent / "z00_sync_git.py"
FONT_DIR = Path("resources") / "fonts" / "ibm_plex_sans_kr"
VARIANTS = {
    "commontg": (
        Path("../../Sensor_Projects/CommonTG-Verification-Platform/z00_sync_git.py"),
        [
            "https://github.com/yjkim9670/CommonTG-Verification-Platform",
            "https://github.com/yjkim9670/GL-FW-DV-Constraint-Review",
        ],
    ),
    "gl_fw": (
        Path("../../Sensor_Projects/GL-FW-DV-Constraint-Review/z00_sync_git.py"),
        [
            "https://github.com/yjkim9670/GL-FW-DV-Constraint-Review",
            "https://github.com/yjkim9670/CommonTG-Verification-Platform",
        ],
    ),
    "documents": (
        Path("../../../Documents/Codex/2026-05-28/yjkim9670-codex-agent-git-https-github/z00_sync_git.py"),
        [
            "https://github.com/yjkim9670/CommonTG-Verification-Platform",
            "https://github.com/yjkim9670/GL-FW-DV-Constraint-Review",
            "https://github.com/yjkim9670/codex-agent",
        ],
    ),
}

REPO_BLOCK = re.compile(r"REPO_CHOICES = \[.*?\n\]", re.DOTALL)


def _repo_choices(source: str) -> list[str]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "REPO_CHOICES"
            for target in node.targets
        ):
            return list(ast.literal_eval(node.value))
    raise ValueError("REPO_CHOICES was not found")


def _with_repo_choices(source: str, choices: list[str]) -> str:
    block = "REPO_CHOICES = [\n" + "".join(f'    "{url}",\n' for url in choices) + "]"
    updated, count = REPO_BLOCK.subn(block, source, count=1)
    if count != 1:
        raise ValueError("unable to replace REPO_CHOICES")
    return updated


def _normalized(source: str) -> str:
    return _with_repo_choices(source, ["<variant configuration>"])


def _copy_fonts(destination_script: Path) -> None:
    source_dir = SOURCE.parent / FONT_DIR
    destination_dir = destination_script.parent / FONT_DIR
    destination_dir.mkdir(parents=True, exist_ok=True)
    for source_file in source_dir.iterdir():
        if source_file.is_file():
            shutil.copy2(source_file, destination_dir / source_file.name)


def check() -> int:
    source_text = SOURCE.read_text(encoding="utf-8")
    expected_source_repos = [
        "https://github.com/yjkim9670/codex-agent",
        "https://github.com/yjkim9670/CommonTG-Verification-Platform",
        "https://github.com/yjkim9670/GL-FW-DV-Constraint-Review",
    ]
    failures: list[str] = []
    if _repo_choices(source_text) != expected_source_repos:
        failures.append("workbench REPO_CHOICES is not the expected configuration")
    if 'DEFAULT_ARCHIVE_DIR = "D:/Multimedia/SendFiles"' not in source_text:
        failures.append("workbench archive default is incorrect")
    for name, (relative_path, expected_repos) in VARIANTS.items():
        target = (SOURCE.parent / relative_path).resolve()
        if not target.is_file():
            failures.append(f"{name}: script is missing: {target}")
            continue
        target_text = target.read_text(encoding="utf-8")
        if _repo_choices(target_text) != expected_repos:
            failures.append(f"{name}: REPO_CHOICES differs from its intended configuration")
        if 'DEFAULT_ARCHIVE_DIR = "D:/Multimedia/SendFiles"' not in target_text:
            failures.append(f"{name}: archive default is incorrect")
        if _normalized(target_text) != _normalized(source_text):
            failures.append(f"{name}: implementation differs from the workbench source")
        missing_fonts = [file.name for file in (SOURCE.parent / FONT_DIR).iterdir() if not (target.parent / FONT_DIR / file.name).is_file()]
        if missing_fonts:
            failures.append(f"{name}: missing bundled font files: {', '.join(missing_fonts)}")
    if failures:
        print("Variant check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("Variant check passed: configuration and implementation are aligned.")
    return 0


def deploy() -> int:
    source_text = SOURCE.read_text(encoding="utf-8")
    for name, (relative_path, repo_choices) in VARIANTS.items():
        target = (SOURCE.parent / relative_path).resolve()
        target.write_text(_with_repo_choices(source_text, repo_choices), encoding="utf-8")
        _copy_fonts(target)
        print(f"Deployed {name}: {target}")
    return check()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy", action="store_true", help="copy the workbench implementation to supported variants")
    args = parser.parse_args()
    return deploy() if args.deploy else check()


if __name__ == "__main__":
    sys.exit(main())
