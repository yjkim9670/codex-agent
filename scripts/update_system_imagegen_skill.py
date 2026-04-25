#!/usr/bin/env python3
"""Patch the installed system imagegen skill with workbench-friendly rules.

The script is intentionally idempotent:
- it updates Workbench-local image output rules;
- it inserts a marked lineage block once;
- a later run replaces only that marked block;
- it creates a timestamped backup before writing when the target filesystem allows it.
"""

from __future__ import annotations

import argparse
import difflib
import os
from pathlib import Path
from datetime import datetime


START = "<!-- codex-workbench:imagegen-ima2-gen:start -->"
END = "<!-- codex-workbench:imagegen-ima2-gen:end -->"
ANCHOR = "\n## Transparent image requests\n"

PATCH_BLOCK = f"""{START}
## Iteration, Lineage, and Metadata

Use these rules for iterative, branching, multi-asset, or project-bound image work. They adapt useful workflow ideas from `ima2-gen` while preserving this skill's built-in-first execution policy.

### Lineage model
- Treat each accepted output as a lineage node with: prompt/spec, use-case slug, input image roles, parent asset when any, output path, selected variant, post-processing notes, and final decision.
- For child edits, use the immediate parent image as the active visual context unless the user explicitly asks to revisit a broader ancestry.
- Keep discarded drafts out of project references unless the user asks to retain them.

### Workbench-local output staging
- In Codex Workbench, use `CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR` if present; otherwise use workspace-local `output/imagegen/` for selected preview/final outputs.
- Use `CODEX_WORKBENCH_IMAGEGEN_TMP_DIR` if present; otherwise use workspace-local `tmp/imagegen/` only for transient sources and post-processing intermediates.
- Even for preview or brainstorming work, move or copy the selected built-in output into the Workbench output directory before finishing.
- The built-in tool may first write under `$CODEX_HOME/generated_images/...`; do not cite that as the final path and do not leave the selected asset only there.

### Regenerate vs variant
- **Regenerate** means retry the same asset contract because the output failed validation or the user wants a better take of the same idea. Keep the destination contract stable, but do not overwrite an accepted project asset unless replacement was explicitly requested.
- **Variant** means create a sibling candidate with a deliberate change in style, composition, content, or constraints. Save variants with clear versioned names such as `hero-v2.png`, `hero-cooler-light.png`, or `item-icon-alt-01.png`.
- **Edit child** means preserve parent invariants and change only the requested property. Repeat the invariants in every follow-up prompt.

### Style sheet
- For a coherent set of assets, create a compact reusable style sheet and keep it subordinate to the user's explicit prompt.
- Prefer these fields when helpful: Medium, Palette, Composition, Lighting/Mood, Subject Details, Text Treatment, Constraints, Avoid.
- Reuse the style sheet across the batch or branch, but update it deliberately when the user chooses a new direction.

### Reference scope
- Label every image input by role: edit target, style reference, composition reference, subject reference, compositing source, or supporting insert.
- Do not let old references silently influence later branches. Carry forward only the immediate parent and references that are still relevant to the user's current request.
- When multiple references conflict, state the priority order in the prompt/spec.

### Sidecar metadata
- For accepted project-bound assets, create a small sidecar when future edits, branching, or recovery would benefit.
- Prefer `<asset-name>.imagegen.json` next to the asset, or a local `.imagegen.json` index when managing a set.
- Store only lightweight metadata: schema version, created timestamp, mode (`built-in` or `cli`), operation (`generate`, `regenerate`, `variant`, `edit-child`), prompt/spec, style sheet, input roles, parent path, output path, post-processing, and notes.
- Never store base64 image payloads or secrets in sidecars.

Example sidecar shape:

```json
{{
  "schema": "codex-imagegen-lineage-v1",
  "mode": "built-in",
  "operation": "variant",
  "asset": "assets/hero-v2.png",
  "parent": "assets/hero.png",
  "use_case": "product-mockup",
  "prompt": "Use case: product-mockup...",
  "style_sheet": {{
    "medium": "clean product photography",
    "palette": "warm neutrals with restrained accent color",
    "composition": "wide hero crop with negative space",
    "avoid": "logos, watermark, distorted text"
  }},
  "inputs": [
    {{"path": "assets/hero.png", "role": "immediate parent"}}
  ],
  "post_processing": ["moved from generated_images", "no alpha changes"],
  "notes": "selected over v1 because product silhouette was clearer"
}}
```

### Validation and retry
- Inspect each generated or edited result against subject, composition, style, text accuracy, invariants, and avoid items before accepting it.
- Retry once for likely transient failures, empty/blank results, corrupt files, or obvious tool hiccups.
- After one retry, change the prompt deliberately, branch a variant, or ask the user before switching execution modes.
{END}
"""

SAVE_POLICY_OLD = """Built-in save-path policy:
- In built-in tool mode, Codex saves generated images under `$CODEX_HOME/*` by default.
- Do not describe or rely on OS temp as the default built-in destination.
- Do not describe or rely on a destination-path argument (if any) on the built-in `image_gen` tool. If a specific location is needed, generate first and then move or copy the selected output from `$CODEX_HOME/generated_images/...`.
- Save-path precedence in built-in mode:
  1. If the user names a destination, move or copy the selected output there.
  2. If the image is meant for the current project, move or copy the final selected image into the workspace before finishing.
  3. If the image is only for preview or brainstorming, render it inline; the underlying file can remain at the default `$CODEX_HOME/*` path.
- Never leave a project-referenced asset only at the default `$CODEX_HOME/*` path.
- Do not overwrite an existing asset unless the user explicitly asked for replacement; otherwise create a sibling versioned filename such as `hero-v2.png` or `item-icon-edited.png`.
"""

SAVE_POLICY_NEW = """Built-in save-path policy:
- In built-in tool mode, Codex may first save generated images under `$CODEX_HOME/*` by default.
- Do not describe or rely on OS temp as the default built-in destination.
- Do not describe or rely on a destination-path argument (if any) on the built-in `image_gen` tool. If a specific location is needed, generate first and then move or copy the selected output from `$CODEX_HOME/generated_images/...`.
- When running inside Codex Workbench, treat the execution cwd as the Workbench-managed workspace. The Workbench may expose `CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR` and `CODEX_WORKBENCH_IMAGEGEN_TMP_DIR`; if present, use those absolute paths.
- If no explicit destination is named in Workbench, save selected preview/final outputs under `CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR`, or `output/imagegen/` under the current workspace if the env var is absent. Use `CODEX_WORKBENCH_IMAGEGEN_TMP_DIR`, or `tmp/imagegen/`, only for transient sources and post-processing intermediates.
- Save-path precedence in built-in mode:
  1. If the user names a destination, move or copy the selected output there.
  2. If the image is meant for the current project, move or copy the final selected image into the workspace before finishing.
  3. If running in Workbench and no destination is named, move or copy the selected output into `CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR` or workspace-local `output/imagegen/` before finishing, even for preview or brainstorming.
  4. Outside Workbench, preview-only images may remain at the default `$CODEX_HOME/*` path if no filesystem artifact is needed.
- Never leave a project-referenced asset only at the default `$CODEX_HOME/*` path.
- In Workbench, do not leave the selected generated asset only under `$CODEX_HOME/*` or an OS temp path.
- Do not overwrite an existing asset unless the user explicitly asked for replacement; otherwise create a sibling versioned filename such as `hero-v2.png` or `item-icon-edited.png`.
"""

WORKFLOW_TRANSPARENT_OLD = "11. For transparent-output requests, follow the transparent image guidance below: generate with built-in `image_gen` on a flat chroma-key background, copy the selected output into the workspace or `tmp/imagegen/`, run the installed `$CODEX_HOME/skills/.system/imagegen/scripts/remove_chroma_key.py` helper, and validate the alpha result before using it. If this path looks unsuitable or fails, ask before switching to CLI `gpt-image-1.5`."
WORKFLOW_TRANSPARENT_NEW = "11. For transparent-output requests, follow the transparent image guidance below: generate with built-in `image_gen` on a flat chroma-key background, copy the selected chroma-key source into `CODEX_WORKBENCH_IMAGEGEN_TMP_DIR` or workspace-local `tmp/imagegen/`, run the installed `$CODEX_HOME/skills/.system/imagegen/scripts/remove_chroma_key.py` helper, save the final alpha asset into the named destination or `CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR` / `output/imagegen/`, and validate the alpha result before using it. If this path looks unsuitable or fails, ask before switching to CLI `gpt-image-1.5`."

WORKFLOW_PREVIEW_OLD = """14. For preview-only work, render the image inline; the underlying file may remain at the default `$CODEX_HOME/generated_images/...` path.
15. For project-bound work, move or copy the selected artifact into the workspace and update any consuming code or references. Never leave a project-referenced asset only at the default `$CODEX_HOME/generated_images/...` path."""

WORKFLOW_PREVIEW_NEW = """14. For preview-only work in Workbench, render the image inline and move or copy the selected output into `CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR` or workspace-local `output/imagegen/`; outside Workbench it may remain at the default `$CODEX_HOME/generated_images/...` path if no filesystem artifact is needed.
15. For project-bound work, move or copy the selected artifact into the workspace and update any consuming code or references. Never leave a project-referenced or Workbench-selected asset only at the default `$CODEX_HOME/generated_images/...` path."""

TRANSPARENT_STEP_3_OLD = "3. After generation, move or copy the selected source image from `$CODEX_HOME/generated_images/...` into the workspace or `tmp/imagegen/`."
TRANSPARENT_STEP_3_NEW = "3. After generation, move or copy the selected source image from `$CODEX_HOME/generated_images/...` into `CODEX_WORKBENCH_IMAGEGEN_TMP_DIR` or workspace-local `tmp/imagegen/`."

TRANSPARENT_STEP_6_OLD = "6. Save the final alpha PNG/WebP in the project if the asset is project-bound. Never leave a project-referenced transparent asset only under `$CODEX_HOME/*`."
TRANSPARENT_STEP_6_NEW = "6. Save the final alpha PNG/WebP in the named destination, the project path, or `CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR` / workspace-local `output/imagegen/` if running in Workbench. Never leave a project-referenced or Workbench-selected transparent asset only under `$CODEX_HOME/*`."

CLI_CONVENTIONS_OLD = """### Temp and output conventions
These conventions apply only to the CLI fallback. They do not describe built-in `image_gen` output behavior.
- Use `tmp/imagegen/` for intermediate files (for example JSONL batches); delete them when done.
- Write final artifacts under `output/imagegen/`.
- Use `--out` or `--out-dir` to control output paths; keep filenames stable and descriptive."""

CLI_CONVENTIONS_NEW = """### Temp and output conventions
These conventions apply only to the CLI fallback. They do not describe built-in `image_gen` output behavior.
- In Codex Workbench, prefer `CODEX_WORKBENCH_IMAGEGEN_TMP_DIR` and `CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR` when present.
- Otherwise, use `tmp/imagegen/` for intermediate files (for example JSONL batches); delete them when done.
- Write final artifacts under `output/imagegen/`.
- Use `--out` or `--out-dir` to control output paths; keep filenames stable and descriptive."""

TEXT_REPLACEMENTS = (
    ("built-in save-path policy", SAVE_POLICY_OLD, SAVE_POLICY_NEW),
    ("transparent workflow step", WORKFLOW_TRANSPARENT_OLD, WORKFLOW_TRANSPARENT_NEW),
    ("preview workflow steps", WORKFLOW_PREVIEW_OLD, WORKFLOW_PREVIEW_NEW),
    ("transparent source staging step", TRANSPARENT_STEP_3_OLD, TRANSPARENT_STEP_3_NEW),
    ("transparent final save step", TRANSPARENT_STEP_6_OLD, TRANSPARENT_STEP_6_NEW),
    ("CLI temp/output conventions", CLI_CONVENTIONS_OLD, CLI_CONVENTIONS_NEW),
)


def parse_args() -> argparse.Namespace:
    default_target = (
        Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        / "skills"
        / ".system"
        / "imagegen"
        / "SKILL.md"
    )
    parser = argparse.ArgumentParser(
        description="Patch ~/.codex/skills/.system/imagegen/SKILL.md with lineage/style/sidecar workflow rules."
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=default_target,
        help=f"Path to SKILL.md. Default: {default_target}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing.",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Print a unified diff. Implied by --dry-run.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a .bak timestamp backup before writing.",
    )
    return parser.parse_args()


def _replace_section(text: str, label: str, old: str, new: str) -> tuple[str, str | None]:
    if old in text:
        return text.replace(old, new, 1), f"updated {label}"
    if new in text:
        return text, None
    raise SystemExit(f"Could not find the expected {label} section in SKILL.md.")


def patch_text(original: str) -> tuple[str, str]:
    updated = original
    actions = []
    for label, old, new in TEXT_REPLACEMENTS:
        updated, action = _replace_section(updated, label, old, new)
        if action:
            actions.append(action)

    block = PATCH_BLOCK.rstrip() + "\n\n"
    if START in updated or END in updated:
        if START not in updated or END not in updated:
            raise SystemExit(
                "Found only one patch marker. Refusing to guess; restore from backup or remove the partial block first."
            )
        start = updated.index(START)
        end = updated.index(END, start) + len(END)
        tail = updated[end:]
        if tail.startswith("\n\n"):
            tail = tail[2:]
        elif tail.startswith("\n"):
            tail = tail[1:]
        patched = updated[:start] + block + tail
        if patched != updated:
            actions.append("updated existing marked block")
        return patched, "; ".join(actions) or "no changes"

    if ANCHOR not in updated:
        raise SystemExit(
            "Could not find the expected '## Transparent image requests' anchor in SKILL.md."
        )
    insert_at = updated.index(ANCHOR) + 1
    actions.append("inserted new marked block")
    return updated[:insert_at] + block + updated[insert_at:], "; ".join(actions)


def print_diff(before: str, after: str, target: Path) -> None:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=str(target),
        tofile=f"{target} (patched)",
    )
    print("".join(diff), end="")


def main() -> int:
    args = parse_args()
    target = args.target.expanduser()
    if target.is_dir():
        target = target / "SKILL.md"
    if not target.exists():
        raise SystemExit(f"Target not found: {target}")

    original = target.read_text(encoding="utf-8")
    updated, action = patch_text(original)

    if updated == original:
        print(f"No changes needed: {target}")
        return 0

    if args.dry_run or args.diff:
        print_diff(original, updated, target)

    if args.dry_run:
        print(f"Dry run only: {action}; no file was written.")
        return 0

    if not args.no_backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = target.with_name(f"{target.name}.bak_{stamp}")
        try:
            backup.write_text(original, encoding="utf-8")
        except OSError as exc:
            raise SystemExit(
                f"Could not write backup beside {target}: {exc}. "
                "If the skill directory is read-only in this Codex session, run this script from the host "
                "environment that owns CODEX_HOME, or rerun with --no-backup only if you accept no backup."
            ) from exc
        print(f"Backup written: {backup}")

    try:
        target.write_text(updated, encoding="utf-8")
    except OSError as exc:
        raise SystemExit(
            f"Could not write {target}: {exc}. "
            "Run this script from the host environment that owns CODEX_HOME, or fix the skill directory "
            "permissions first."
        ) from exc

    print(f"Updated {target}: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
