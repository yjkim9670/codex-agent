#!/usr/bin/env python3
"""Add native in-image text guidance to the installed imagegen skill."""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import shutil
from pathlib import Path


DEFAULT_SKILL_PATH = (
    Path.home() / ".codex" / "skills" / ".system" / "imagegen" / "SKILL.md"
)

SECTION_HEADING = "## Native in-image text"

SECTION = """## Native in-image text

When the user asks for text to appear inside the final raster image, treat that
text as part of the image generation contract.

- Put the exact requested copy in the `Text (verbatim):` prompt field or an
  equivalent clearly labeled `EXACT VISIBLE TEXT TO RENDER:` block.
- Explicitly tell `image_gen` to render the text natively inside the image.
- Do not add local text overlays, SVG/HTML text layers, or deterministic
  post-processing text unless the user explicitly asks for that path.
- Keep generated text short, high-contrast, horizontal, and large enough to
  reduce spelling and layout errors.
- For dense or accuracy-critical text, tell the user native image text can still
  misspell words, validate the generated result, and retry once with a simpler
  prompt before proposing deterministic post-processing.
"""

PROMPTING_BULLET = (
    "- For requested in-image text, include exact copy in the generation prompt "
    "and ask the image model to render it natively; do not add text overlays "
    "unless the user explicitly asks for that."
)


def insert_before(text: str, marker: str, insertion: str) -> tuple[str, bool]:
    if insertion.strip() in text:
        return text, False
    index = text.find(marker)
    if index == -1:
        raise ValueError(f"Could not find insertion marker: {marker!r}")
    return text[:index] + insertion.rstrip() + "\n\n" + text[index:], True


def insert_after_line(text: str, line: str, insertion_line: str) -> tuple[str, bool]:
    if insertion_line in text:
        return text, False
    needle = line + "\n"
    index = text.find(needle)
    if index == -1:
        raise ValueError(f"Could not find line marker: {line!r}")
    index += len(needle)
    return text[:index] + insertion_line + "\n" + text[index:], True


def patch_text(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    text, changed = insert_before(text, "## Prompt augmentation", SECTION)
    if changed:
        changes.append(SECTION_HEADING)

    text, changed = insert_after_line(
        text,
        "- Quote exact text and specify typography + placement.",
        PROMPTING_BULLET,
    )
    if changed:
        changes.append("prompting best practices bullet")

    return text, changes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch imagegen SKILL.md to prefer native image_gen text rendering."
    )
    parser.add_argument("--skill-path", type=Path, default=DEFAULT_SKILL_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    skill_path = args.skill_path.expanduser().resolve()
    original = skill_path.read_text(encoding="utf-8")
    patched, changes = patch_text(original)

    if patched == original:
        print(f"No changes needed: {skill_path}")
        return 0

    print(f"Target: {skill_path}")
    print("Changes:")
    for change in changes:
        print(f"- {change}")

    if args.dry_run:
        diff = difflib.unified_diff(
            original.splitlines(),
            patched.splitlines(),
            fromfile=str(skill_path),
            tofile=f"{skill_path} (patched)",
            lineterm="",
        )
        print("\n".join(diff))
        return 0

    if not args.no_backup:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = skill_path.with_name(f"{skill_path.name}.bak-{stamp}")
        shutil.copy2(skill_path, backup_path)
        print(f"Backup: {backup_path}")

    skill_path.write_text(patched, encoding="utf-8")
    print("Patched successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
