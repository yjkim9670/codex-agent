#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import gzip
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


SOURCE_PATHS = (
    "model_agent",
    "run_model_chat_server.py",
    "run_model_chat_server.sh",
    "run_model_chat_server_tg.sh",
    "model_agent_config.json",
)

SKIP_PARTS = {"__pycache__", ".DS_Store"}


def _iter_source_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in SOURCE_PATHS:
        src = repo_root / rel
        if not src.exists():
            raise FileNotFoundError(f"Source path not found: {src}")
        if src.is_file():
            files.append(src)
            continue
        for candidate in sorted(src.rglob("*")):
            if not candidate.is_file():
                continue
            rel_parts = set(candidate.relative_to(repo_root).parts)
            if rel_parts & SKIP_PARTS:
                continue
            files.append(candidate)
    return sorted(files, key=lambda p: str(p.relative_to(repo_root)))


def _encode_file(path: Path) -> str:
    raw = path.read_bytes()
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    return base64.b64encode(compressed).decode("ascii")


def _mode_octal(path: Path) -> str:
    mode = stat.S_IMODE(path.stat().st_mode)
    return f"{mode:03o}"


def _render_installer(repo_root: Path, files: list[Path]) -> str:
    lines: list[str] = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        'TARGET_ROOT="${1:-$PWD}"',
        'mkdir -p "$TARGET_ROOT"',
        "",
        "decode_base64() {",
        "  if base64 --decode </dev/null >/dev/null 2>&1; then",
        "    base64 --decode",
        "  elif base64 -d </dev/null >/dev/null 2>&1; then",
        "    base64 -d",
        "  elif command -v python3 >/dev/null 2>&1; then",
        "    python3 -c 'import base64,sys;sys.stdout.buffer.write(base64.b64decode(sys.stdin.buffer.read()))'",
        "  else",
        "    echo 'No base64 decoder available.' >&2",
        "    return 1",
        "  fi",
        "}",
        "",
        "write_encoded_file() {",
        '  local rel_path="$1"',
        '  local mode="$2"',
        '  local dst="${TARGET_ROOT%/}/${rel_path}"',
        '  mkdir -p "$(dirname "$dst")"',
        '  decode_base64 | gzip -dc > "$dst"',
        '  chmod "$mode" "$dst"',
        '  printf "Wrote %s\\n" "$rel_path"',
        "}",
        "",
    ]

    for idx, path in enumerate(files):
        rel = path.relative_to(repo_root).as_posix()
        mode = _mode_octal(path)
        payload = _encode_file(path)
        marker = f"__B64_PAYLOAD_{idx}__"
        lines.append(f"write_encoded_file '{rel}' '{mode}' <<'{marker}'")
        lines.append(payload)
        lines.append(marker)
        lines.append("")

    lines.append('echo "Completed. Files restored under: $TARGET_ROOT"')
    lines.append("")
    return "\n".join(lines)


def _copy_to_clipboard(text: str) -> tuple[bool, str]:
    clipboard_cmds = [
        ["pbcopy"],
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["termux-clipboard-set"],
    ]
    if os.name == "nt" or sys.platform.startswith("win"):
        clipboard_cmds.extend(
            [
                ["clip.exe"],
                ["cmd.exe", "/c", "clip"],
            ]
        )
    for cmd in clipboard_cmds:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True)
            return True, " ".join(cmd)
        except (OSError, subprocess.CalledProcessError):
            continue
    return False, ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a shell installer that restores model_agent, run_model_chat_server scripts, and model_agent_config.json via gzip+base64 payloads."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Repository root containing model_agent, run_model_chat_server.*, and model_agent_config.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("model_agent_bundle.sh"),
        help="Path to write generated shell script.",
    )
    parser.add_argument(
        "--no-clipboard",
        action="store_true",
        help="Do not copy generated script to clipboard.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_path = args.output.resolve()

    files = _iter_source_files(repo_root)
    installer_text = _render_installer(repo_root, files)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(installer_text, encoding="utf-8")
    output_path.chmod(0o755)

    print(f"Generated: {output_path}")
    print(f"Packed files: {len(files)}")

    if args.no_clipboard:
        print("Clipboard: skipped (--no-clipboard)")
        return 0

    copied, command = _copy_to_clipboard(installer_text)
    if copied:
        print(f"Clipboard: copied via `{command}`")
        return 0

    print("Clipboard: failed (no supported clipboard command found).")
    print("Script file is still generated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
