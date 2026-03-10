#!/usr/bin/env python3
"""
z00_sync_git_final.py
Refactored Sync Helper with Responsive Layout, Directory Info, and Async GUI.
"""

import argparse
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Optional, Set, Tuple, Dict, Callable

# UI Imports
try:
    import tkinter as tk
    from tkinter import scrolledtext, ttk, messagebox
    _HAVE_TK = True
except ImportError:
    _HAVE_TK = False

# Curses for CLI TUI
try:
    import curses
    _HAVE_CURSES = True
except ImportError:
    _HAVE_CURSES = False

# Fallback for CLI interaction
try:
    import msvcrt
    _HAVE_MSVCRT = True
except ImportError:
    _HAVE_MSVCRT = False

try:
    import termios
    import tty
    _HAVE_TERMIOS = True
except ImportError:
    _HAVE_TERMIOS = False


# Configuration - Modern Theme (Slate Dark)
ACCENT_COLOR = "#4aa3ff"    # Slate-friendly accent blue
ACCENT_HOVER = "#3a8ad9"    # Darker accent for hover
SUCCESS_COLOR = "#47c270"   # Modern green
WARNING_COLOR = "#ffb84d"   # Modern amber
ERROR_COLOR = "#ff6b6b"     # Modern red
BG_COLOR = "#2b3038"        # Slate background
BG_SECONDARY = "#3a414d"    # Slate secondary
BORDER_COLOR = "#4b5563"    # Slate border
TEXT_COLOR = "#f1f5f9"      # Primary text
TEXT_SECONDARY = "#cbd5e1"  # Secondary text
TEXT_MUTED = "#94a3b8"      # Muted text

UI_FONT_FAMILY_DISPLAY = "Segoe UI"
UI_FONT_FAMILY_TEXT = "Segoe UI"
UI_FONT_FAMILY_MONO = "Consolas"

REPO_CHOICES = [
    "https://github.com/yjkim9670/CommonTG-Verification-Platform",
    "https://github.com/yjkim9670/GL-FW-DV-Constraint-Review",
    "https://github.com/yjkim9670/codex-agent",
]

# Timeout settings (based on avg times: Branch ~30s, Metadata ~45s, Sync ~35s)
GIT_BRANCH_TIMEOUT = 90   # Branch list fetch (avg 30s, 3x buffer)
GIT_FETCH_TIMEOUT = 120   # Metadata fetch (avg 45s, ~2.7x buffer)
GIT_CLONE_TIMEOUT = 240   # Clone/sync operation (avg 35s, generous buffer for network issues)

# Timezone Configuration
KST = timezone(timedelta(hours=9))  # Korea Standard Time (GMT+9)
SUBPROCESS_TEXT_ENCODING = "utf-8"
SUBPROCESS_TEXT_ERRORS = "replace"


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _strip_text(value: object) -> str:
    return _as_text(value).strip()


def _read_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _read_float_env(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _read_bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return _strip_text(raw).lower() in {"1", "true", "yes", "on"}


# Global I/O semaphore settings (cross-process)
GIT_SYNC_IO_SLOTS = _read_int_env("GIT_SYNC_IO_SLOTS", 1, minimum=1)
GIT_SYNC_IO_STALE_SECONDS = _read_int_env("GIT_SYNC_IO_STALE_SECONDS", 7200, minimum=300)
GIT_SYNC_IO_POLL_SECONDS = _read_float_env("GIT_SYNC_IO_POLL_SECONDS", 0.5, minimum=0.2)
AUTO_SYNC_MIRROR_DEFAULT = _read_bool_env("GIT_SYNC_AUTO_MIRROR", False)

LOG_PATH_ENV = "GIT_SYNC_LOG_PATH"
DEFAULT_RUNTIME_LOG_DIR = ".sync_runtime"
DEFAULT_LOG_FILENAME = "sync_run.log"


def _git_env() -> Dict[str, str]:
    """Ensure git never opens interactive prompts so GUI threads cannot hang."""
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GCM_INTERACTIVE", "never")
    return env


def _convert_to_kst_string(iso_date_str: Optional[str]) -> str:
    """
    Convert ISO8601 date string to KST format with text representation.

    Args:
        iso_date_str: Date string in ISO8601 format (e.g., "2025-12-08 15:30:00 +0900")

    Returns:
        Formatted string in KST (e.g., "2025-12-08 15:30:00 KST")
    """
    text = _as_text(iso_date_str)
    try:
        # Parse ISO8601 string (handles various formats including timezone offsets)
        # Try different formats
        for fmt in [
            "%Y-%m-%d %H:%M:%S %z",  # 2025-12-08 15:30:00 +0900
            "%Y-%m-%dT%H:%M:%S%z",   # 2025-12-08T15:30:00+0900
            "%Y-%m-%d %H:%M:%S%z",   # 2025-12-08 15:30:00+0900
        ]:
            try:
                dt = datetime.strptime(text.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            # If no format matched, return original string
            return text

        # Convert to KST
        dt_kst = dt.astimezone(KST)

        # Format as "YYYY-MM-DD HH:MM:SS KST"
        return dt_kst.strftime("%Y-%m-%d %H:%M:%S KST")

    except Exception:
        # If conversion fails, return original string
        return text


class GlobalIOSemaphore:
    """
    Cross-process I/O semaphore using lock files in the system temp directory.

    This limits concurrent heavy sync phases across different working folders.
    """

    def __init__(self, slots: int, stale_seconds: int, poll_seconds: float):
        self.slots = max(1, slots)
        self.stale_seconds = max(300, stale_seconds)
        self.poll_seconds = max(0.2, poll_seconds)
        self.lock_root = Path(tempfile.gettempdir()) / "git_sync_io_slots"
        self.lock_root.mkdir(parents=True, exist_ok=True)

    def _lock_file(self, slot: int) -> Path:
        return self.lock_root / f"slot_{slot}.lock"

    def _read_pid(self, lock_path: Path) -> Optional[int]:
        try:
            text = lock_path.read_text(encoding="utf-8")
        except OSError:
            return None
        match = re.search(r"pid=(\d+)", text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def _cleanup_stale(self, lock_path: Path, log_fn: Callable[[str], None]) -> None:
        try:
            stat = lock_path.stat()
        except FileNotFoundError:
            return
        except OSError:
            return

        age = time.time() - stat.st_mtime
        if age < self.stale_seconds:
            return

        pid = self._read_pid(lock_path)
        if pid is not None and self._is_pid_alive(pid):
            return

        try:
            lock_path.unlink()
            log_fn(f"[I/O semaphore] Removed stale lock: {lock_path.name}")
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def acquire(self, log_fn: Callable[[str], None], context: str) -> Path:
        started_at = time.time()
        last_wait_log = 0.0
        payload = (
            f"pid={os.getpid()} host={socket.gethostname()} "
            f"cwd={Path.cwd()} context={context} ts={datetime.now(KST).isoformat()}\n"
        )

        while True:
            for slot in range(self.slots):
                lock_path = self._lock_file(slot)
                self._cleanup_stale(lock_path, log_fn)

                try:
                    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError:
                    continue
                except OSError as e:
                    raise RuntimeError(f"I/O semaphore lock creation failed: {e}") from e

                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fp:
                        fp.write(payload)
                except Exception:
                    try:
                        lock_path.unlink()
                    except OSError:
                        pass
                    raise

                wait_sec = time.time() - started_at
                if wait_sec >= 1.0:
                    log_fn(
                        f"[I/O semaphore] Acquired slot {slot + 1}/{self.slots} "
                        f"after waiting {wait_sec:.1f}s ({context})"
                    )
                else:
                    log_fn(f"[I/O semaphore] Acquired slot {slot + 1}/{self.slots} ({context})")
                return lock_path

            wait_sec = time.time() - started_at
            now = time.time()
            if now - last_wait_log >= 10.0:
                log_fn(f"[I/O semaphore] Waiting for slot... {wait_sec:.1f}s elapsed ({context})")
                last_wait_log = now
            time.sleep(self.poll_seconds)

    def release(self, lock_path: Optional[Path], log_fn: Callable[[str], None]) -> None:
        if lock_path is None:
            return
        try:
            lock_path.unlink()
            log_fn(f"[I/O semaphore] Released {lock_path.name}")
        except FileNotFoundError:
            pass
        except OSError as e:
            log_fn(f"[I/O semaphore] Warning: failed to release lock {lock_path}: {e}")


# =============================================================================
# 1. Logging & Utilities
# =============================================================================

def resolve_log_path(cwd: Path) -> Path:
    raw = os.environ.get(LOG_PATH_ENV, "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        return candidate
    return cwd / DEFAULT_RUNTIME_LOG_DIR / DEFAULT_LOG_FILENAME


def build_log_protect_entries(cwd: Path, log_path: Path) -> Tuple[List[str], List[str]]:
    protect_dirs: List[str] = []
    protect_files: List[str] = []

    try:
        rel = log_path.resolve().relative_to(cwd.resolve())
    except ValueError:
        return protect_dirs, protect_files

    rel_str = rel.as_posix()
    if not rel_str or rel_str == ".":
        return protect_dirs, protect_files

    if len(rel.parts) == 1:
        protect_files.append(rel_str)
    else:
        protect_dirs.append(rel.parts[0].replace("\\", "/"))

    return protect_dirs, protect_files


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        try:
            log_path.unlink()
        except OSError:
            pass

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )
    logging.info("Logging initialized at %s", log_path)


def read_protect_list(path: Path) -> Tuple[List[str], List[str]]:
    dirs: List[str] = ["workspace", "sources"]
    files: List[str] = ["sync_protect.list", path.name if path.exists() else ""]

    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("dir:"):
                dirs.append(line[4:].strip().rstrip("\\/"))
            elif line.lower().startswith("file:"):
                files.append(line[5:].strip())
            elif line.endswith(("/", "\\")):
                dirs.append(line.rstrip("\\/"))
            elif "." in line:
                files.append(line)
            else:
                dirs.append(line)
    
    return sorted(list(set(d for d in dirs if d))), sorted(list(set(f for f in files if f)))


# =============================================================================
# 2. Business Logic (Model) - GitManager
# =============================================================================

class GitManager:
    """Handles all Git operations and file system manipulations."""

    def __init__(
        self,
        cwd: Path,
        protect_list_path: Path,
        extra_protect_dirs: Optional[List[str]] = None,
        extra_protect_files: Optional[List[str]] = None,
    ):
        self.cwd = cwd
        self.protect_list_path = protect_list_path
        self.extra_protect_dirs = extra_protect_dirs or []
        self.extra_protect_files = extra_protect_files or []
        self.protect_dirs: List[str] = []
        self.protect_files: List[str] = []
        self.io_semaphore = GlobalIOSemaphore(
            slots=GIT_SYNC_IO_SLOTS,
            stale_seconds=GIT_SYNC_IO_STALE_SECONDS,
            poll_seconds=GIT_SYNC_IO_POLL_SECONDS,
        )
        self._ensure_git()
        self.refresh_protect_list()

    def refresh_protect_list(self) -> None:
        protect_dirs, protect_files = read_protect_list(self.protect_list_path)
        protect_dirs.extend(self.extra_protect_dirs)
        protect_files.extend(self.extra_protect_files)
        self.protect_dirs = sorted(set(d for d in protect_dirs if d))
        self.protect_files = sorted(set(f for f in protect_files if f))

    def _ensure_git(self) -> None:
        if shutil.which("git") is None:
            raise EnvironmentError("Git executable not found in PATH.")

    def _parse_github_repo(self, repo_url: str) -> Tuple[str, str]:
        """
        GitHub URL에서 owner와 repo 이름 추출
        https://github.com/yjkim9670/GL-FW-DV-Constraint-Review
        → ("yjkim9670", "GL-FW-DV-Constraint-Review")
        """
        match = re.search(r'github\.com[:/]([^/]+)/([^/\.]+)', repo_url)
        if not match:
            raise ValueError(f"Invalid GitHub URL: {repo_url}")
        return match.group(1), match.group(2)

    def get_remote_branches_fast(self, repo: str) -> List[str]:
        """Fast retrieval of branch names using ls-remote."""
        cmd = ["git", "ls-remote", "--heads", repo]
        env = _git_env()
        try:
            raw = subprocess.check_output(
                cmd,
                text=True,
                encoding=SUBPROCESS_TEXT_ENCODING,
                errors=SUBPROCESS_TEXT_ERRORS,
                stderr=subprocess.STDOUT,
                timeout=GIT_BRANCH_TIMEOUT,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("Timed out while fetching remote branches.") from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to list branches: {e.output}") from e

        branches = []
        for line in raw.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1].startswith("refs/heads/"):
                branches.append(parts[1].replace("refs/heads/", "", 1))
        
        if not branches:
            raise RuntimeError("No remote branches found.")
        return sorted(branches)

    def fetch_branch_dates(self, repo: str) -> Dict[str, str]:
        """
        Slower retrieval of commit dates. 
        Creates a temporary repo to fetch metadata without a full clone.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="meta_", dir=Path(tempfile.gettempdir())))
        updates = {}
        env = _git_env()
        try:
            subprocess.run(
                ["git", "init", "-q"],
                cwd=tmp_dir,
                check=True,
                env=env,
                timeout=GIT_BRANCH_TIMEOUT,
            )
            subprocess.run(
                ["git", "remote", "add", "origin", repo],
                cwd=tmp_dir,
                check=True,
                env=env,
                timeout=GIT_BRANCH_TIMEOUT,
            )
            # Fetch only head information (lightweight as possible for dates)
            subprocess.run(
                ["git", "fetch", "--no-tags", "--depth", "1", "origin", "+refs/heads/*:refs/remotes/origin/*"],
                cwd=tmp_dir,
                check=True,
                capture_output=True,
                env=env,
                timeout=GIT_FETCH_TIMEOUT,
            )
            output = subprocess.check_output(
                ["git", "for-each-ref", "refs/remotes/origin", "--format", "%(refname:short)\t%(committerdate:iso8601)"],
                text=True,
                encoding=SUBPROCESS_TEXT_ENCODING,
                errors=SUBPROCESS_TEXT_ERRORS,
                cwd=tmp_dir,
                env=env,
                timeout=GIT_BRANCH_TIMEOUT,
            )
            for line in output.splitlines():
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    branch_name = parts[0].replace("origin/", "")
                    # Convert to KST format
                    updates[branch_name] = _convert_to_kst_string(parts[1])
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass  # Ignore errors here, returning empty dict is fine (dates are optional)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return updates

    def sync(self, repo: str, branch: str, mirror: bool, log_callback: Callable[[str], None], method: str = "git") -> None:
        """
        Performs the full sync process.

        Args:
            repo: Repository URL
            branch: Branch name to sync
            mirror: If True, delete local files not in repo
            log_callback: Logging function
            method: Download method - "git" (default) or "zip"
        """
        log_callback(f"Starting sync: {repo} @ {branch} (method: {method})")
        self.refresh_protect_list()

        if method == "git":
            self._sync_git_incremental(repo, branch, mirror, log_callback)
            return

        if method != "zip":
            raise ValueError(f"Unsupported sync method: {method}")

        # ZIP path keeps legacy full-download behavior.
        tmp_dir = None
        io_lock = self.io_semaphore.acquire(log_callback, f"{self.cwd.name}:{branch}:{method}")
        try:
            git_dir = self.cwd / ".git"
            if git_dir.exists():
                self._remove_git_dir(git_dir, "existing working copy", log_callback)

            tmp_dir = self._download_zip(repo, branch, log_callback)

            if mirror:
                self._backup_and_delete(tmp_dir, log_callback)
            else:
                log_callback("Mirror OFF: Skipping local cleanup.")

            self._copy_files(tmp_dir, log_callback)
            self._remove_git_dir(self.cwd / ".git", "post-copy", log_callback)
            log_callback("Sync completed successfully.")
        finally:
            if tmp_dir and tmp_dir.exists():
                self._remove_git_dir(tmp_dir / ".git", "temp cleanup", log_callback)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            self.io_semaphore.release(io_lock, log_callback)

    def _run_git_checked(
        self,
        command: List[str],
        timeout: int,
        cwd: Optional[Path] = None,
    ) -> str:
        env = _git_env()
        workdir = cwd or self.cwd
        try:
            completed = subprocess.run(
                command,
                cwd=workdir,
                check=True,
                capture_output=True,
                text=True,
                encoding=SUBPROCESS_TEXT_ENCODING,
                errors=SUBPROCESS_TEXT_ERRORS,
                timeout=timeout,
                env=env,
            )
            return _strip_text(completed.stdout)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Git command timed out: {' '.join(command)}") from e
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            stdout = (e.stdout or "").strip()
            detail = stderr or stdout or "No additional details."
            raise RuntimeError(f"Git command failed: {' '.join(command)}\n{detail}") from e

    def _ensure_incremental_repo(self, repo: str, log_fn: Callable[[str], None]) -> None:
        git_dir = self.cwd / ".git"
        if git_dir.exists():
            try:
                self._run_git_checked(["git", "rev-parse", "--is-inside-work-tree"], timeout=GIT_BRANCH_TIMEOUT)
            except RuntimeError:
                log_fn("Detected invalid .git metadata. Reinitializing repository metadata.")
                self._remove_git_dir(git_dir, "invalid working copy metadata", log_fn)

        if not git_dir.exists():
            log_fn("Initializing local git repository for incremental sync...")
            self._run_git_checked(["git", "init", "-q"], timeout=GIT_BRANCH_TIMEOUT)

        try:
            current_remote = self._run_git_checked(
                ["git", "remote", "get-url", "origin"],
                timeout=GIT_BRANCH_TIMEOUT,
            )
        except RuntimeError:
            self._run_git_checked(["git", "remote", "add", "origin", repo], timeout=GIT_BRANCH_TIMEOUT)
            log_fn("Configured remote 'origin'.")
        else:
            if current_remote != repo:
                self._run_git_checked(
                    ["git", "remote", "set-url", "origin", repo],
                    timeout=GIT_BRANCH_TIMEOUT,
                )
                log_fn("Updated remote 'origin' URL.")

    def _normalize_rel_path(self, rel_path: object) -> str:
        return _as_text(rel_path).replace("\\", "/").strip("/")

    def _compare_key(self, rel_path: str) -> str:
        normalized = self._normalize_rel_path(rel_path)
        if os.name == "nt":
            return normalized.lower()
        return normalized

    def _collect_tracked_path_keys(self) -> Set[str]:
        tracked_keys: Set[str] = set()
        raw = self._run_git_checked(["git", "ls-files", "-z"], timeout=GIT_BRANCH_TIMEOUT)
        if not raw:
            return tracked_keys

        for entry in raw.split("\x00"):
            normalized = self._normalize_rel_path(entry)
            if not normalized:
                continue
            tracked_keys.add(self._compare_key(normalized))
            parts = normalized.split("/")
            for depth in range(1, len(parts)):
                tracked_keys.add(self._compare_key("/".join(parts[:depth])))

        return tracked_keys

    def _run_mirror_cleanup_incremental(self, log_fn: Callable[[str], None]) -> None:
        tracked_keys = self._collect_tracked_path_keys()
        removed_files = 0
        removed_dirs = 0

        for current, dirs, files in os.walk(self.cwd, topdown=False):
            base = Path(current)

            for name in files:
                full_path = base / name
                try:
                    rel_path = self._normalize_rel_path(str(full_path.relative_to(self.cwd)))
                except ValueError:
                    continue
                if not rel_path or rel_path.startswith(".git/"):
                    continue
                if self._compare_key(rel_path) in tracked_keys:
                    continue
                if self._should_protect(rel_path, is_dir=False):
                    continue

                try:
                    full_path.unlink()
                    removed_files += 1
                except FileNotFoundError:
                    pass
                except OSError as e:
                    log_fn(f"Warning: Failed to delete file {rel_path}: {e}")

            for name in dirs:
                full_path = base / name
                try:
                    rel_path = self._normalize_rel_path(str(full_path.relative_to(self.cwd)))
                except ValueError:
                    continue
                if not rel_path or rel_path == ".git" or rel_path.startswith(".git/"):
                    continue
                if self._compare_key(rel_path) in tracked_keys:
                    continue
                if self._should_protect(rel_path, is_dir=True):
                    continue

                try:
                    if full_path.is_symlink():
                        full_path.unlink()
                        removed_files += 1
                    else:
                        shutil.rmtree(full_path)
                        removed_dirs += 1
                except FileNotFoundError:
                    pass
                except OSError as e:
                    log_fn(f"Warning: Failed to delete directory {rel_path}: {e}")

        log_fn(
            "Mirror clean completed with protect-list exclusions. "
            f"Removed {removed_files} files and {removed_dirs} directories."
        )

    def _sync_git_incremental(self, repo: str, branch: str, mirror: bool, log_fn: Callable[[str], None]) -> None:
        io_lock = self.io_semaphore.acquire(log_fn, f"{self.cwd.name}:{branch}:git")
        try:
            self._ensure_incremental_repo(repo, log_fn)

            log_fn("Running incremental sync: fetch -> checkout -> reset -> mirror-clean")
            refspec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
            self._run_git_checked(
                ["git", "fetch", "--depth", "1", "--prune", "origin", refspec],
                timeout=GIT_FETCH_TIMEOUT,
            )
            self._run_git_checked(
                ["git", "checkout", "-f", "-B", "__sync_work", f"origin/{branch}"],
                timeout=GIT_CLONE_TIMEOUT,
            )
            self._run_git_checked(
                ["git", "reset", "--hard", f"origin/{branch}"],
                timeout=GIT_CLONE_TIMEOUT,
            )

            if mirror:
                self._run_mirror_cleanup_incremental(log_fn)
            else:
                log_fn("Mirror OFF: Skipping local cleanup.")

            log_fn("Sync completed successfully.")
        finally:
            self.io_semaphore.release(io_lock, log_fn)

    def _clone_temp(self, repo: str, branch: str, log_fn: Callable) -> Path:
        base = self.cwd.parent / "temp"
        base.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="sync_", dir=base))
        log_fn(f"Cloning to temporary: {tmp_dir}")

        env = _git_env()
        try:
            subprocess.check_output(
                ["git", "clone", "--depth", "1", "-b", branch, repo, str(tmp_dir)],
                text=True,
                encoding=SUBPROCESS_TEXT_ENCODING,
                errors=SUBPROCESS_TEXT_ERRORS,
                stderr=subprocess.STDOUT,
                timeout=GIT_CLONE_TIMEOUT,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("Git clone timed out.") from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git clone failed: {e.output}") from e

        self._remove_git_dir(tmp_dir / ".git", "temp clone", log_fn)
        return tmp_dir

    def _download_zip(self, repo: str, branch: str, log_fn: Callable) -> Path:
        """
        GitHub에서 ZIP 파일을 다운로드하여 압축 해제

        개선사항:
        1. 브랜치명 슬래시(/) 처리 - GitHub는 슬래시를 하이픈으로 변환
        2. 타임아웃 추가 - GIT_CLONE_TIMEOUT 적용
        3. 임시 파일 정리 개선 - 실패 시에도 ZIP 파일 삭제
        4. 폴더명 감지 강화 - 최근 생성 폴더 기준 정렬
        5. 진행 상황 콜백 - 다운로드 진행률 표시
        6. 상세한 네트워크 에러 메시지 - 타임아웃/프록시 구분
        """
        base = self.cwd.parent / "temp"
        base.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="zip_", dir=base))

        zip_path = None
        try:
            # GitHub URL에서 owner/repo 추출
            owner, repo_name = self._parse_github_repo(repo)

            # [개선 1] 브랜치명의 슬래시를 하이픈으로 변환 (GitHub ZIP 규칙)
            # 참고: URL에는 원본 브랜치명을 사용하지만, GitHub가 생성하는 폴더명은 / → - 로 변환됨
            sanitized_branch = branch.replace('/', '-')
            zip_url = f"https://github.com/{owner}/{repo_name}/archive/refs/heads/{branch}.zip"

            log_fn(f"[ZIP Download] Target URL: {zip_url}")
            log_fn(f"[ZIP Download] Branch name in URL: {branch} (original, with slashes)")
            log_fn(f"[ZIP Download] Expected folder name: {repo_name}-{sanitized_branch} (GitHub converts / to -)")

            # ZIP 파일 경로 (안전한 파일명 사용)
            zip_filename = f"{repo_name}-{sanitized_branch}.zip"
            zip_path = tmp_dir / zip_filename
            log_fn(f"[ZIP Download] Local file: {zip_path}")

            # [개선 2] 타임아웃 설정 및 [개선 5] 진행 상황 콜백
            download_start_time = time.time()
            last_log_time = [download_start_time]
            downloaded_bytes = [0]

            # User-Agent 헤더 추가하여 프록시 환경에서도 작동하도록 개선
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/zip,*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive'
            }

            log_fn(f"[ZIP Download] Request headers: User-Agent={headers['User-Agent'][:50]}...")
            log_fn(f"[ZIP Download] Timeout: {GIT_CLONE_TIMEOUT} seconds")

            # urllib.request.Request로 헤더 추가
            request = urllib.request.Request(zip_url, headers=headers)

            try:
                log_fn(f"[ZIP Download] Opening connection to GitHub...")
                log_fn(f"[ZIP Download] Attempting to access: https://github.com/{owner}/{repo_name}")

                with urllib.request.urlopen(request, timeout=GIT_CLONE_TIMEOUT) as response:
                    total_size = int(response.headers.get('Content-Length', 0))
                    total_mb = total_size / (1024 * 1024) if total_size > 0 else 0

                    log_fn(f"[ZIP Download] ✓ Connected! HTTP {response.status}")
                    log_fn(f"[ZIP Download] Repository is accessible (Public or authenticated)")
                    log_fn(f"[ZIP Download] Total size: {total_mb:.1f} MB")
                    log_fn(f"[ZIP Download] Content-Type: {response.headers.get('Content-Type', 'unknown')}")
                    log_fn(f"[ZIP Download] Starting download with 8KB chunks...")

                    with open(zip_path, 'wb') as out_file:
                        chunk_size = 8192  # 8KB chunks
                        chunk_count = 0

                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break

                            out_file.write(chunk)
                            chunk_count += 1
                            downloaded_bytes[0] += len(chunk)

                            # 진행률 로깅 (10% 단위)
                            if total_size > 0:
                                percent = min(int(downloaded_bytes[0] * 100 / total_size), 100)
                                current_time = time.time()

                                if percent % 10 == 0 and (current_time - last_log_time[0]) > 2:
                                    downloaded_mb = downloaded_bytes[0] / (1024 * 1024)
                                    speed_mbps = downloaded_mb / (current_time - download_start_time)
                                    log_fn(f"Downloading: {percent}% ({downloaded_mb:.1f}MB / {total_mb:.1f}MB) @ {speed_mbps:.1f} MB/s")
                                    last_log_time[0] = current_time

                log_fn(f"[ZIP Download] Download successful: {chunk_count} chunks, {downloaded_bytes[0] / (1024*1024):.1f} MB")

            except socket.timeout:
                log_fn(f"[ZIP Download] ❌ FAILED: Socket timeout after {GIT_CLONE_TIMEOUT} seconds")
                raise
            except urllib.error.HTTPError as e:
                log_fn(f"[ZIP Download] ❌ FAILED: HTTP {e.code} - {e.reason}")
                log_fn(f"[ZIP Download] URL was: {zip_url}")
                if e.code == 401:
                    log_fn(f"[ZIP Download] Authentication required - Private repository detected")
                    log_fn(f"[ZIP Download] ZIP download does not support authentication")
                    log_fn(f"[ZIP Download] Solution: Use 'Git Sync (Incremental)' method with SSH key or PAT")
                elif e.code == 403:
                    log_fn(f"[ZIP Download] Access forbidden - Private repository detected")
                elif e.code == 404:
                    log_fn(f"[ZIP Download] Possible private repository - ZIP download requires public access")
                raise
            except urllib.error.URLError as e:
                log_fn(f"[ZIP Download] ❌ FAILED: URL Error - {e.reason}")
                raise
            except Exception as e:
                log_fn(f"[ZIP Download] ❌ FAILED: {type(e).__name__}: {e}")
                raise

            download_time = time.time() - download_start_time
            log_fn(f"Download complete in {download_time:.1f}s. Extracting...")

            # 압축 해제
            extract_dir = tmp_dir / "extracted"
            extract_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # [개선 1] GitHub ZIP 폴더명: {repo_name}-{sanitized_branch}
            extracted_folder = extract_dir / f"{repo_name}-{sanitized_branch}"

            # [개선 4] 폴더명 감지 강화 - 최근 생성 시간 기준 정렬
            if not extracted_folder.exists():
                log_fn(f"Expected folder not found: {extracted_folder.name}")
                log_fn("Searching for alternative extracted folder...")

                # 모든 하위 디렉토리를 생성 시간 기준으로 정렬 (최신 우선)
                subdirs = sorted(
                    [d for d in extract_dir.iterdir() if d.is_dir()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )

                if subdirs:
                    extracted_folder = subdirs[0]
                    log_fn(f"Auto-detected folder: {extracted_folder.name} (most recent)")
                else:
                    raise RuntimeError("No extracted folder found in ZIP")

            log_fn(f"ZIP extraction complete: {extracted_folder.name}")

            # [개선 3] 성공 시 ZIP 파일 삭제 (공간 절약)
            if zip_path and zip_path.exists():
                file_size_mb = zip_path.stat().st_size / (1024 * 1024)
                zip_path.unlink()
                log_fn(f"Cleaned up ZIP file ({file_size_mb:.1f}MB)")

            return extracted_folder

        # [개선 6] 상세한 네트워크 에러 메시지
        except socket.timeout as e:
            raise RuntimeError(
                f"다운로드 시간 초과 ({GIT_CLONE_TIMEOUT}초). "
                f"네트워크 연결이 불안정하거나 저장소가 너무 큽니다. "
                f"Git Sync 방식을 사용해보세요."
            ) from e

        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError(
                    f"❌ HTTP 401: 인증이 필요합니다.\n\n"
                    f"Private Repository에 접근하려면 인증이 필요합니다.\n"
                    f"ZIP 다운로드는 인증을 지원하지 않습니다.\n\n"
                    f"해결 방법:\n"
                    f"  - 'Git Sync (Incremental)' 방식으로 변경하세요\n"
                    f"  - Git 인증 설정 (다음 중 하나):\n"
                    f"    • SSH 키: ~/.ssh/id_rsa (권장)\n"
                    f"    • Personal Access Token (PAT):\n"
                    f"      git config --global credential.helper store\n"
                    f"      git clone <URL> (PAT 입력 요청됨)\n\n"
                    f"PAT 생성: GitHub → Settings → Developer settings → Personal access tokens"
                ) from e
            elif e.code == 403:
                raise RuntimeError(
                    f"❌ HTTP 403: 접근 권한이 없습니다.\n\n"
                    f"Private Repository는 ZIP 다운로드를 지원하지 않습니다.\n\n"
                    f"해결 방법:\n"
                    f"  - 'Git Sync (Incremental)' 방식으로 변경\n"
                    f"  - Git 인증 설정 확인:\n"
                    f"    • SSH 키: ~/.ssh/id_rsa\n"
                    f"    • Personal Access Token: git config credential.helper"
                ) from e
            elif e.code == 404:
                raise RuntimeError(
                    f"❌ HTTP 404: Repository 또는 Branch를 찾을 수 없습니다.\n\n"
                    f"가능한 원인:\n"
                    f"  1. Branch '{branch}'가 존재하지 않음\n"
                    f"  2. Private Repository (ZIP 다운로드는 Public만 지원)\n"
                    f"  3. Repository 이름 오타\n\n"
                    f"해결 방법:\n"
                    f"  - Refresh 버튼을 눌러 브랜치 목록 확인\n"
                    f"  - Private Repository는 'Git Sync (Incremental)' 방식 사용\n"
                    f"    (SSH 키 또는 Personal Access Token 필요)"
                ) from e
            elif e.code in (502, 503, 504):
                raise RuntimeError(
                    f"GitHub 서버 오류 ({e.code}). "
                    f"회사 프록시 서버에 일시적인 문제가 있을 수 있습니다. "
                    f"잠시 후 다시 시도해주세요."
                ) from e
            else:
                raise RuntimeError(f"HTTP error {e.code}: {e.reason}") from e

        except urllib.error.URLError as e:
            error_str = str(e).lower()
            if "timed out" in error_str or "timeout" in error_str:
                raise RuntimeError(
                    f"다운로드 시간 초과. 네트워크 연결을 확인하세요."
                ) from e
            elif "proxy" in error_str:
                raise RuntimeError(
                    f"프록시 인증 실패. 시스템 프록시 설정을 확인하세요.\n"
                    f"상세: {e.reason}"
                ) from e
            else:
                raise RuntimeError(f"네트워크 오류: {e.reason}") from e

        except zipfile.BadZipFile as e:
            raise RuntimeError(
                f"ZIP 파일이 손상되었습니다. 다운로드가 중단되었을 수 있습니다. "
                f"다시 시도해주세요."
            ) from e

        except Exception as e:
            raise RuntimeError(f"ZIP download failed: {e}") from e

        finally:
            # [개선 3] 실패 시에도 임시 ZIP 파일 정리
            if zip_path and zip_path.exists():
                try:
                    zip_path.unlink()
                    log_fn("Cleaned up incomplete ZIP file")
                except Exception:
                    pass  # 정리 실패는 무시 (이미 에러 상황)

    def _backup_and_delete(self, source_root: Path, log_fn: Callable) -> None:
        log_fn("Performing mirror cleanup (backup & delete)...")
        source_rels = self._build_rel_set(source_root)
        
        backup_base = self.cwd.parent / "sync_backups"
        backup_dir = backup_base / datetime.now().strftime("%Y%m%d_%H%M%S")
        
        deleted_count = 0
        backed_up_count = 0

        # Walk bottom-up
        for current, dirs, files in os.walk(self.cwd, topdown=False):
            base = Path(current)
            for name in dirs + files:
                full_path = base / name
                try:
                    rel_path = str(full_path.relative_to(self.cwd)).replace("\\", "/")
                except ValueError:
                    continue

                if rel_path in source_rels:
                    continue
                
                if self._should_protect(rel_path, full_path.is_dir()):
                    continue

                # Backup
                if backed_up_count == 0:
                    backup_dir.mkdir(parents=True, exist_ok=True)
                
                target_backup = backup_dir / rel_path
                target_backup.parent.mkdir(parents=True, exist_ok=True)
                
                try:
                    if full_path.is_dir():
                        shutil.copytree(full_path, target_backup, dirs_exist_ok=True)
                        shutil.rmtree(full_path)
                    else:
                        shutil.copy2(full_path, target_backup)
                        full_path.unlink()
                    
                    deleted_count += 1
                    backed_up_count += 1
                except Exception as e:
                    log_fn(f"Warning: Failed to process {rel_path}: {e}")

        if deleted_count > 0:
            log_fn(f"Mirrored: Removed {deleted_count} items. Backup at {backup_dir}")
        else:
            log_fn("Mirror clean: No extra files found.")

    def _copy_files(self, source: Path, log_fn: Callable) -> None:
        log_fn("Copying new files to workspace...")
        for entry in source.iterdir():
            dest = self.cwd / entry.name
            if entry.is_dir():
                shutil.copytree(entry, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, dest)

    def create_archive_backup(self, target_dir: Path, log_fn: Callable) -> Path:
        """
        Create a compressed archive of the current local repository.

        Args:
            target_dir: Directory where the archive will be saved
            log_fn: Logging callback function

        Returns:
            Path to the created archive file
        """
        # Create target directory if it doesn't exist
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Generate archive filename (fixed name, no timestamp)
        repo_name = self.cwd.name
        archive_name = f"{repo_name}_backup.zip"
        archive_path = target_dir / archive_name

        log_fn(f"Creating archive backup: {archive_name}")
        log_fn(f"Target directory: {target_dir}")

        # Remove old backup with same name if exists (overwrite mode)
        if archive_path.exists():
            archive_path.unlink()
            log_fn(f"Removed existing archive: {archive_name}")

        total_files = 0
        total_size = 0
        archive_rel = None
        try:
            archive_rel = archive_path.relative_to(self.cwd)
        except ValueError:
            archive_rel = None

        try:
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Walk through all files in the repository
                for root, dirs, files in os.walk(self.cwd):
                    for file in files:
                        file_path = Path(root) / file

                        try:
                            rel_path = file_path.relative_to(self.cwd)
                            if archive_rel and rel_path == archive_rel:
                                continue

                            # Add file to archive
                            zipf.write(file_path, arcname=rel_path)
                            total_files += 1
                            total_size += file_path.stat().st_size

                            # Log progress every 100 files
                            if total_files % 100 == 0:
                                log_fn(f"Archived {total_files} files...")

                        except Exception as e:
                            log_fn(f"Warning: Failed to archive {file_path}: {e}")

            # Get final archive size
            archive_size = archive_path.stat().st_size
            archive_size_mb = archive_size / (1024 * 1024)
            total_size_mb = total_size / (1024 * 1024)
            compression_ratio = (1 - archive_size / total_size) * 100 if total_size > 0 else 0

            log_fn(f"Archive created successfully!")
            log_fn(f"Total files: {total_files}")
            log_fn(f"Original size: {total_size_mb:.2f} MB")
            log_fn(f"Archive size: {archive_size_mb:.2f} MB")
            log_fn(f"Compression ratio: {compression_ratio:.1f}%")
            log_fn(f"Archive path: {archive_path}")

            return archive_path

        except Exception as e:
            log_fn(f"Error creating archive: {e}")
            if archive_path.exists():
                archive_path.unlink()
            raise

    def _remove_git_dir(self, path: Path, context: str, log_fn: Callable) -> None:
        if not path.exists():
            return
        
        def on_rm_error(func, p, exc_info):
            os.chmod(p, 0o777)
            try:
                func(p)
            except Exception:
                pass
        
        shutil.rmtree(path, onerror=on_rm_error)
        log_fn(f"Removed .git folder ({context})")

    def _build_rel_set(self, root: Path) -> Set[str]:
        rels = set()
        for current, dirs, files in os.walk(root):
            base = Path(current)
            for name in dirs + files:
                rel = str((base / name).relative_to(root)).replace("\\", "/")
                rels.add(rel)
        return rels

    def _should_protect(self, rel_path: str, is_dir: bool) -> bool:
        normalized = self._normalize_rel_path(rel_path)
        compare_key = self._compare_key(normalized)
        wildcard_chars = set("*?[]")
        path_obj = PurePosixPath(compare_key)

        # Check explicit directories and wildcard directory patterns.
        for pattern in self.protect_dirs:
            norm_pat = self._normalize_rel_path(_as_text(pattern).rstrip("\\/"))
            if not norm_pat:
                continue
            pat_key = self._compare_key(norm_pat)
            if any(ch in wildcard_chars for ch in pat_key):
                if path_obj.match(pat_key) or path_obj.match(f"{pat_key}/*"):
                    return True
            elif compare_key == pat_key or compare_key.startswith(f"{pat_key}/"):
                return True

        # Check file patterns.
        for pattern in self.protect_files:
            pat = self._normalize_rel_path(pattern)
            if not pat:
                continue
            if path_obj.match(self._compare_key(pat)):
                return True
        return False


# =============================================================================
# 3. Presentation Logic (View/Controller) - GuiApp
# =============================================================================

class TkTextHandler(logging.Handler):
    """Redirects log records to a Tkinter Text widget safely."""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", msg + "\n")
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        self.text_widget.after(0, append)


class GuiApp:
    def __init__(self, manager: GitManager, initial_repo: str, mode: str):
        self.manager = manager
        self.repo_url = initial_repo
        self.mode = mode
        self.root = tk.Tk()
        self.branch_map = []  # Stores plain branch names
        self.branch_dates = {} # Stores branch -> date string

        # Timestamp tracking
        self.last_branch_try_time = None
        self.last_metadata_try_time = None
        self.last_sync_try_time = None
        self.last_branch_time = None
        self.last_metadata_time = None
        self.last_sync_time = None
        self.timestamp_job = None

        # Performance tracking (average times)
        self.branch_fetch_times = []  # List of branch fetch durations
        self.metadata_fetch_times = []  # List of metadata fetch durations
        self.sync_times = []  # List of sync durations
        self.max_samples = 10  # Keep last N samples for rolling average

        # Task state tracking (for parallel operations)
        self.is_syncing = False
        self.is_refreshing = False
        self.cancel_refresh = False  # Flag to cancel ongoing refresh

        # Auto-refresh timer
        self.auto_refresh_job = None
        self.auto_refresh_enabled = False
        self.auto_refresh_interval = 150  # 2.5 minutes in seconds

        # Auto-sync state (triggered by auto-refresh update detection only)
        self.auto_sync_enabled = False
        self.last_synced_branch = None  # Track last synced branch for auto-sync
        self.auto_sync_mirror_default = AUTO_SYNC_MIRROR_DEFAULT
        self.auto_sync_tracking_branch = None
        self.auto_sync_last_synced_commit = ""
        self.auto_sync_pending_commit = None

        # Archive backup settings
        default_archive_dir = str(self.manager.cwd.parent / "archive_backups")
        self.archive_dir = default_archive_dir
        self.auto_backup_after_sync = False  # Auto backup after sync

        self._setup_ui()
        self._setup_logging()
        self._start_timestamp_updates()

        # [CHANGE] Initialize with 'main' branch by default
        self._initialize_main_branch()

    def _is_network_error(self, error_msg: str) -> bool:
        """네트워크 관련 에러인지 확인"""
        return is_network_error(error_msg)

    def _initialize_main_branch(self):
        """Initialize branch list with 'main' branch by default."""
        self.branch_map = ["main"]
        self.branch_tree.insert("", "end", values=("main", ""))
        logging.info("Initialized with 'main' branch")

    def _setup_ui(self):
        # [CHANGE] Updated Window Title to include Current Directory Name
        current_dir_name = self.manager.cwd.name
        self.root.title(f"[{current_dir_name}] Git Sync Pro - {self.mode}")

        # [CHANGE] Increased Window Size (1100x820) for better layout
        self.root.geometry("1100x820")
        self.root.configure(bg=BG_COLOR)

        # Apply modern theme
        self._apply_theme()

        # Header
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=20, pady=(15, 10))

        ttk.Label(header, text="Repository Sync", style="Title.TLabel").pack(anchor="w")
        # Show full path in subtitle
        ttk.Label(header, text=f"Target: {self.manager.cwd}", style="Subtitle.TLabel").pack(anchor="w")

        # Timestamp info frame (3 rows with column alignment)
        timestamp_frame = ttk.Frame(self.root)
        timestamp_frame.pack(fill="x", padx=20, pady=(0, 5))

        # Configure grid columns for alignment
        timestamp_frame.columnconfigure(0, weight=0, minsize=250)  # Refresh column
        timestamp_frame.columnconfigure(1, weight=0, minsize=250)  # Sync column
        timestamp_frame.columnconfigure(2, weight=1)               # Avg times column (flexible)

        # Row 0: Last try times (branch / metadata / sync)
        self.last_branch_try_var = tk.StringVar(value="Last Branch Try: -")
        self.last_metadata_try_var = tk.StringVar(value="Last Metadata Try: -")
        self.last_sync_try_var = tk.StringVar(value="Last Sync Try: -")

        ttk.Label(timestamp_frame, textvariable=self.last_branch_try_var, style="Timestamp.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.last_metadata_try_var, style="Timestamp.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.last_sync_try_var, style="Timestamp.TLabel").grid(row=0, column=2, sticky="w")

        # Row 1: Last done times (branch / metadata / sync)
        self.last_branch_var = tk.StringVar(value="Last Branch Done: -")
        self.last_metadata_var = tk.StringVar(value="Last Metadata Done: -")
        self.last_sync_var = tk.StringVar(value="Last Sync Done: -")

        ttk.Label(timestamp_frame, textvariable=self.last_branch_var, style="TimestampSuccess.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.last_metadata_var, style="TimestampSuccess.TLabel").grid(row=1, column=1, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.last_sync_var, style="TimestampSuccess.TLabel").grid(row=1, column=2, sticky="w")

        # Row 2: Average times (branch / metadata / sync)
        self.avg_branch_var = tk.StringVar(value="Avg Branch: -")
        self.avg_metadata_var = tk.StringVar(value="Avg Metadata: -")
        self.avg_sync_var = tk.StringVar(value="Avg Sync: -")

        ttk.Label(timestamp_frame, textvariable=self.avg_branch_var, style="TimestampPerf.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.avg_metadata_var, style="TimestampPerf.TLabel").grid(row=2, column=1, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.avg_sync_var, style="TimestampPerf.TLabel").grid(row=2, column=2, sticky="w")

        # Controls
        ctrl_frame = ttk.Frame(self.root)
        ctrl_frame.pack(fill="x", padx=20, pady=5)
        ctrl_frame.columnconfigure(1, weight=1)

        ttk.Label(ctrl_frame, text="Repo:", style="LabelBold.TLabel").grid(row=0, column=0, sticky="w")

        # [CHANGE] Use Combobox instead of OptionMenu for better layout and long text handling
        self.repo_var = tk.StringVar(value=self.repo_url)
        self.repo_combo = ttk.Combobox(ctrl_frame, textvariable=self.repo_var, values=REPO_CHOICES, state="readonly")
        self.repo_combo.grid(row=0, column=1, sticky="ew", padx=10)
        self.repo_combo.bind("<<ComboboxSelected>>", self._on_repo_changed)

        self.btn_open_browser = ttk.Button(ctrl_frame, text="🌐 Open", command=self.open_in_browser)
        self.btn_open_browser.grid(row=0, column=2, sticky="w", padx=(0, 10))

        self.mirror_var = tk.BooleanVar(value=True)
        mirror_check = ttk.Checkbutton(ctrl_frame, text="Manual Mirror (Clean Extras)", variable=self.mirror_var)
        mirror_check.grid(row=0, column=3, sticky="e", padx=10)

        self.btn_refresh = ttk.Button(ctrl_frame, text="↻ Refresh", command=self._toggle_refresh)
        self.btn_refresh.grid(row=0, column=4, sticky="e")

        # Download Method Selection
        method_frame = ttk.Frame(self.root)
        method_frame.pack(fill="x", padx=20, pady=5)

        ttk.Label(method_frame, text="Download Method:", style="LabelBold.TLabel").grid(row=0, column=0, sticky="w")

        self.download_method_var = tk.StringVar(value="git")
        ttk.Radiobutton(method_frame, text="Git Sync (Incremental)",
                       variable=self.download_method_var, value="git").grid(row=0, column=1, sticky="w", padx=10)
        ttk.Radiobutton(method_frame, text="ZIP Download (Public Repositories Only)",
                       variable=self.download_method_var, value="zip").grid(row=0, column=2, sticky="w", padx=10)

        # Archive Backup Settings
        archive_frame = ttk.Frame(self.root)
        archive_frame.pack(fill="x", padx=20, pady=5)
        archive_frame.columnconfigure(3, weight=1)

        ttk.Label(archive_frame, text="Archive Backup:", style="LabelBold.TLabel").grid(row=0, column=0, sticky="w")

        # Auto backup after sync checkbox
        self.auto_backup_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            archive_frame,
            text="Auto-backup after sync",
            variable=self.auto_backup_var
        ).grid(row=0, column=1, sticky="w", padx=(10, 5))

        # Archive directory path
        self.archive_dir_var = tk.StringVar(value=self.archive_dir)
        ttk.Label(archive_frame, text="Path:", style="LabelMuted.TLabel").grid(row=0, column=2, sticky="w", padx=(20, 5))

        archive_entry = ttk.Entry(archive_frame, textvariable=self.archive_dir_var, width=40)
        archive_entry.grid(row=0, column=3, sticky="ew", padx=5)

        # Browse button
        ttk.Button(archive_frame, text="Browse...", command=self._browse_archive_dir).grid(row=0, column=4, sticky="w", padx=5)

        # Auto-refresh controls
        auto_refresh_frame = ttk.Frame(self.root)
        auto_refresh_frame.pack(fill="x", padx=20, pady=5)

        ttk.Label(auto_refresh_frame, text="Auto-Refresh:", style="LabelBold.TLabel").grid(row=0, column=0, sticky="w")

        self.auto_refresh_var = tk.BooleanVar(value=False)
        self.auto_refresh_check = ttk.Checkbutton(
            auto_refresh_frame,
            text="Enable",
            variable=self.auto_refresh_var,
            command=self._toggle_auto_refresh
        )
        self.auto_refresh_check.grid(row=0, column=1, sticky="w", padx=(10, 5))

        ttk.Label(auto_refresh_frame, text="Interval:", style="LabelMuted.TLabel").grid(row=0, column=2, sticky="w", padx=(20, 5))

        self.auto_refresh_interval_var = tk.StringVar(value="150")  # 2.5 minutes
        interval_spinbox = ttk.Spinbox(
            auto_refresh_frame,
            from_=60,
            to=3600,
            increment=60,
            textvariable=self.auto_refresh_interval_var,
            width=8
        )
        interval_spinbox.grid(row=0, column=3, sticky="w", padx=5)
        ttk.Label(auto_refresh_frame, text="seconds", style="LabelMuted.TLabel").grid(row=0, column=4, sticky="w")

        # Branch List (Treeview with columns)
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill="both", expand=False, padx=20, pady=10)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(1, weight=1)
        ttk.Label(list_frame, text="Available Branches", style="LabelBold.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))

        # Create Treeview with two columns
        columns = ("branch", "last_commit")
        self.branch_tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse", height=6)

        # Configure columns
        self.branch_tree.heading("branch", text="Branch Name")
        self.branch_tree.heading("last_commit", text="Last Commit (KST)")
        self.branch_tree.column("branch", width=260, minwidth=180, stretch=True)
        self.branch_tree.column("last_commit", width=200, minwidth=150, stretch=False)

        # Style configuration for better readability
        style = ttk.Style()
        style.configure("Treeview", font=(UI_FONT_FAMILY_TEXT, 10), rowheight=26)
        style.configure("Treeview.Heading", font=(UI_FONT_FAMILY_TEXT, 10, "bold"))

        self.branch_tree.grid(row=1, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.branch_tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.branch_tree.config(yscrollcommand=scrollbar.set)

        # Progress Bar (Indeterminate)
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", padx=20, pady=(0, 5))

        # Action Area
        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill="x", padx=20, pady=10)
        action_frame.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Repository를 선택하고 Refresh 버튼을 눌러주세요")
        ttk.Label(action_frame, textvariable=self.status_var, style="LabelMuted.TLabel").grid(row=0, column=0, sticky="w")

        # Archive Backup Button
        self.btn_archive = ttk.Button(action_frame, text="📦 Archive Backup", command=self.create_archive_backup)
        self.btn_archive.grid(row=0, column=1, sticky="e", padx=(0, 10))

        # Sync Button always visible on right
        self.btn_sync = ttk.Button(action_frame, text="Start Sync", command=self.start_sync, style="Accent.TButton")
        self.btn_sync.grid(row=0, column=2, sticky="e")

        # Auto-sync controls (below Start Sync button)
        auto_sync_frame = ttk.Frame(self.root)
        auto_sync_frame.pack(fill="x", padx=20, pady=5)

        ttk.Label(auto_sync_frame, text="Auto-Sync:", style="LabelBold.TLabel").grid(row=0, column=0, sticky="w")

        self.auto_sync_var = tk.BooleanVar(value=False)
        self.auto_sync_check = ttk.Checkbutton(
            auto_sync_frame,
            text="Enable",
            variable=self.auto_sync_var,
            command=self._toggle_auto_sync
        )
        self.auto_sync_check.grid(row=0, column=1, sticky="w", padx=(10, 5))
        self.auto_sync_check.config(state="disabled")
        ttk.Label(
            auto_sync_frame,
            text="(Auto-Refresh ON + selected branch update detected only)",
            style="LabelMuted.TLabel",
        ).grid(row=0, column=2, columnspan=4, sticky="w", padx=(20, 0))

        self.auto_sync_mirror_var = tk.BooleanVar(value=self.auto_sync_mirror_default)
        ttk.Checkbutton(
            auto_sync_frame,
            text="Auto-Sync Mirror (Clean Extras)",
            variable=self.auto_sync_mirror_var,
        ).grid(row=1, column=1, sticky="w", padx=(10, 5), pady=(4, 0))

        # Log Area
        log_frame = ttk.LabelFrame(self.root, text="Activity Log", padding=5)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.log_widget = scrolledtext.ScrolledText(
            log_frame,
            height=15,
            state="disabled",
            font=(UI_FONT_FAMILY_MONO, 9),
            bg=BG_SECONDARY,
            fg=TEXT_COLOR,
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=10
        )
        self.log_widget.pack(fill="both", expand=True)

    def _apply_theme(self):
        """Apply modern, clean theme with improved contrast and spacing."""
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except:
            pass

        # Base styles
        style.configure(".",
                       background=BG_COLOR,
                       foreground=TEXT_COLOR,
                       borderwidth=0,
                       relief="flat")

        # Frame styles
        style.configure("TFrame", background=BG_COLOR, borderwidth=0)
        style.configure("TLabelframe",
                       background=BG_COLOR,
                       bordercolor=BORDER_COLOR,
                       borderwidth=1,
                       relief="solid")
        style.configure("TLabelframe.Label",
                       background=BG_COLOR,
                       foreground=TEXT_COLOR,
                       font=(UI_FONT_FAMILY_TEXT, 10, "bold"))

        # Label styles
        style.configure("Title.TLabel",
                       font=(UI_FONT_FAMILY_DISPLAY, 18, "bold"),
                       background=BG_COLOR,
                       foreground=TEXT_COLOR,
                       padding=(0, 10, 0, 5))

        style.configure("Subtitle.TLabel",
                       font=(UI_FONT_FAMILY_TEXT, 10),
                       foreground=TEXT_SECONDARY,
                       background=BG_COLOR,
                       padding=(0, 0, 0, 10))

        style.configure("LabelBold.TLabel",
                       font=(UI_FONT_FAMILY_TEXT, 10, "bold"),
                       background=BG_COLOR,
                       foreground=TEXT_COLOR)

        style.configure("LabelMuted.TLabel",
                       font=(UI_FONT_FAMILY_TEXT, 9),
                       foreground=TEXT_MUTED,
                       background=BG_COLOR)

        style.configure("Timestamp.TLabel",
                       font=(UI_FONT_FAMILY_TEXT, 9, "italic"),
                       foreground=ACCENT_COLOR,
                       background=BG_COLOR)

        style.configure("TimestampSuccess.TLabel",
                       font=(UI_FONT_FAMILY_TEXT, 9, "italic"),
                       foreground=SUCCESS_COLOR,
                       background=BG_COLOR)

        style.configure("TimestampPerf.TLabel",
                       font=(UI_FONT_FAMILY_TEXT, 9, "italic"),
                       foreground=WARNING_COLOR,
                       background=BG_COLOR)

        # Button styles - Modern with rounded appearance
        style.configure("Accent.TButton",
                       background=ACCENT_COLOR,
                       foreground="#ffffff",
                       font=(UI_FONT_FAMILY_TEXT, 10, "bold"),
                       borderwidth=0,
                       focuscolor="none",
                       padding=(20, 10))

        style.map("Accent.TButton",
                 background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)],
                 foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])

        style.configure("TButton",
                       background=BG_SECONDARY,
                       foreground=TEXT_COLOR,
                       font=(UI_FONT_FAMILY_TEXT, 9),
                       borderwidth=1,
                       bordercolor=BORDER_COLOR,
                       focuscolor="none",
                       padding=(12, 8))

        style.map("TButton",
                 background=[("active", BORDER_COLOR), ("pressed", BORDER_COLOR)])

        # Entry and Combobox styles
        style.configure("TEntry",
                       fieldbackground=BG_SECONDARY,
                       foreground=TEXT_COLOR,
                       bordercolor=BORDER_COLOR,
                       borderwidth=1,
                       insertcolor=TEXT_COLOR,
                       padding=8)

        style.map("TEntry",
                 bordercolor=[("focus", ACCENT_COLOR)])

        style.configure("TCombobox",
                       fieldbackground=BG_SECONDARY,
                       background=BG_SECONDARY,
                       foreground=TEXT_COLOR,
                       bordercolor=BORDER_COLOR,
                       arrowcolor=TEXT_COLOR,
                       padding=8)

        style.map("TCombobox",
                 fieldbackground=[("readonly", BG_SECONDARY)],
                 bordercolor=[("focus", ACCENT_COLOR)])

        # Checkbutton styles
        style.configure("TCheckbutton",
                       background=BG_COLOR,
                       foreground=TEXT_COLOR,
                       font=(UI_FONT_FAMILY_TEXT, 9))

        # Radiobutton styles
        style.configure("TRadiobutton",
                       background=BG_COLOR,
                       foreground=TEXT_COLOR,
                       font=(UI_FONT_FAMILY_TEXT, 9))

        # Treeview styles (for branch list)
        style.configure("Treeview",
                       background=BG_SECONDARY,
                       foreground=TEXT_COLOR,
                       fieldbackground=BG_SECONDARY,
                       borderwidth=1,
                       bordercolor=BORDER_COLOR,
                       font=(UI_FONT_FAMILY_TEXT, 9))

        style.configure("Treeview.Heading",
                       background=BG_COLOR,
                       foreground=TEXT_COLOR,
                       borderwidth=1,
                       bordercolor=BORDER_COLOR,
                       font=(UI_FONT_FAMILY_TEXT, 10, "bold"),
                       padding=10)

        style.map("Treeview",
                 background=[("selected", ACCENT_COLOR)],
                 foreground=[("selected", "#ffffff")])

        style.map("Treeview.Heading",
                 background=[("active", BG_SECONDARY)])

        # Spinbox styles
        style.configure("TSpinbox",
                       fieldbackground=BG_SECONDARY,
                       foreground=TEXT_COLOR,
                       bordercolor=BORDER_COLOR,
                       arrowcolor=TEXT_COLOR,
                       padding=8)

    def _setup_logging(self):
        handler = TkTextHandler(self.log_widget)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s", datefmt="%H:%M:%S"))
        logging.getLogger().addHandler(handler)

    def _format_elapsed(self, delta_seconds: int) -> str:
        if delta_seconds < 0:
            delta_seconds = 0
        if delta_seconds < 60:
            return f"{delta_seconds}s"
        if delta_seconds < 3600:
            minutes = delta_seconds // 60
            seconds = delta_seconds % 60
            return f"{minutes}m {seconds}s"
        if delta_seconds < 86400:
            hours = delta_seconds // 3600
            minutes = (delta_seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        days = delta_seconds // 86400
        hours = (delta_seconds % 86400) // 3600
        return f"{days}d {hours}h"

    def _format_time_with_age(self, label: str, dt: Optional[datetime]) -> str:
        if not dt:
            return f"{label}: -"
        now = datetime.now(KST)
        elapsed = int((now - dt).total_seconds())
        elapsed_str = self._format_elapsed(elapsed)
        timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S KST")
        return f"{label}: {timestamp_str} ({elapsed_str} ago)"

    def _update_timestamp_labels(self):
        self.last_branch_try_var.set(self._format_time_with_age("Last Branch Try", self.last_branch_try_time))
        self.last_metadata_try_var.set(self._format_time_with_age("Last Metadata Try", self.last_metadata_try_time))
        self.last_sync_try_var.set(self._format_time_with_age("Last Sync Try", self.last_sync_try_time))
        self.last_branch_var.set(self._format_time_with_age("Last Branch Done", self.last_branch_time))
        self.last_metadata_var.set(self._format_time_with_age("Last Metadata Done", self.last_metadata_time))
        self.last_sync_var.set(self._format_time_with_age("Last Sync Done", self.last_sync_time))
        self.timestamp_job = self.root.after(1000, self._update_timestamp_labels)

    def _start_timestamp_updates(self):
        if self.timestamp_job:
            self.root.after_cancel(self.timestamp_job)
        self._update_timestamp_labels()

    def _browse_archive_dir(self):
        """Browse and select archive backup directory."""
        from tkinter import filedialog

        initial_dir = self.archive_dir_var.get()
        target_dir = filedialog.askdirectory(
            title="Select Archive Backup Directory",
            initialdir=initial_dir
        )

        if target_dir:
            self.archive_dir_var.set(target_dir)
            self.archive_dir = target_dir
            logging.info(f"Archive backup directory set to: {target_dir}")

    def open_in_browser(self):
        """Open selected repository in web browser."""
        repo_url = self.repo_var.get()
        if repo_url:
            try:
                webbrowser.open(repo_url)
                logging.info(f"Opened repository in browser: {repo_url}")
            except Exception as e:
                logging.error(f"Failed to open browser: {e}")
                messagebox.showerror("Browser Error", f"Failed to open browser:\n{e}")

    def _on_repo_changed(self, _event):
        """Repository 변경 시 브랜치 리스트 초기화 (자동 로드 안 함)"""
        # Clear branch list
        for item in self.branch_tree.get_children():
            self.branch_tree.delete(item)
        self.branch_map = []
        self.branch_dates = {}

        # [CHANGE] Re-initialize with main branch
        self._initialize_main_branch()

        # Update status message
        self.status_var.set("Repository가 변경되었습니다. Refresh 버튼을 눌러 브랜치를 로드하세요")

    def _update_controls(self):
        """
        Update control states based on current task status.
        Allows parallel operations: Refresh and Sync can run simultaneously.
        """
        # Repository selection: disabled if either task is running
        if self.is_syncing or self.is_refreshing:
            self.repo_combo.config(state="disabled")
        else:
            self.repo_combo.config(state="readonly")

        # Refresh button: change text and always enabled
        if self.is_refreshing:
            self.btn_refresh.config(text="⏹ Stop Refresh", state="normal")
        else:
            self.btn_refresh.config(text="↻ Refresh", state="normal")

        # Sync button: disabled if syncing OR no branches loaded
        sync_enabled = not self.is_syncing and len(self.branch_map) > 0
        self.btn_sync.config(state="normal" if sync_enabled else "disabled")

        # Auto-sync toggle is available only when auto-refresh is enabled
        self.auto_sync_check.config(state="normal" if self.auto_refresh_enabled else "disabled")

        # Branch tree: always enabled (can select even during operations)
        # Treeview doesn't have a state property like Listbox, so no action needed

        # Progress bar: show if any task is running
        if self.is_syncing or self.is_refreshing:
            self.progress.start(10)
        else:
            self.progress.stop()

    # --- Async Tasks ---

    def _toggle_refresh(self):
        """Toggle between starting and stopping refresh."""
        if self.is_refreshing:
            # Stop refresh
            self.cancel_refresh = True
            self.status_var.set("Cancelling refresh...")
            logging.info("[Refresh] Cancellation requested by user")
        else:
            # Start refresh
            self.refresh_branches(auto_refresh=False)

    def refresh_branches(self, auto_refresh=False):
        """
        Fetch branch list from remote repository.

        Args:
            auto_refresh: If True, this is an automatic refresh (no user interaction)
        """
        # Prevent concurrent refresh operations
        if self.is_refreshing:
            if not auto_refresh:
                logging.warning("[Refresh] Already in progress, skipping")
            return

        self.last_branch_try_time = datetime.now(KST)

        # Update state
        self.is_refreshing = True
        self.cancel_refresh = False  # Reset cancel flag
        self._update_controls()

        # [CHANGE] Do NOT clear branch list - preserve existing branches
        if auto_refresh:
            self.status_var.set("Auto-refreshing branch list...")
        else:
            self.status_var.set("Fetching branch list...")

        repo = self.repo_var.get()
        if auto_refresh:
            logging.info(f"[Auto-Refresh] Starting branch fetch from: {repo}")
        else:
            logging.info(f"[Refresh] Starting branch fetch from: {repo}")

        def task():
            try:
                # Check cancel flag before Step 1
                if self.cancel_refresh:
                    self.root.after(0, lambda: self._on_refresh_cancelled(auto_refresh))
                    return

                # Step 1: Fast fetch names (measure time)
                branch_start = time.time()
                branches = self.manager.get_remote_branches_fast(repo)
                branch_duration = time.time() - branch_start

                # Check cancel flag after Step 1
                if self.cancel_refresh:
                    self.root.after(0, lambda: self._on_refresh_cancelled(auto_refresh))
                    return

                self.root.after(0, lambda: self._on_branches_loaded(branches, auto_refresh, branch_duration))

                # Check cancel flag before Step 2
                if self.cancel_refresh:
                    self.root.after(0, lambda: self._on_refresh_cancelled(auto_refresh))
                    return

                # Step 2: Slow fetch dates (measure time)
                self.last_metadata_try_time = datetime.now(KST)
                metadata_start = time.time()
                dates = self.manager.fetch_branch_dates(repo)
                metadata_duration = time.time() - metadata_start

                # Check cancel flag after Step 2
                if self.cancel_refresh:
                    self.root.after(0, lambda: self._on_refresh_cancelled(auto_refresh))
                    return

                self.root.after(0, lambda: self._on_dates_loaded(dates, auto_refresh, metadata_duration))

            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._on_refresh_error("Fetch Error", error_msg, auto_refresh))

        threading.Thread(target=task, daemon=True).start()

    def _on_branches_loaded(self, branches: List[str], auto_refresh=False, duration=None):
        """Handle successful branch list fetch."""
        # Record branch fetch time
        if duration is not None:
            self.branch_fetch_times.append(duration)
            if len(self.branch_fetch_times) > self.max_samples:
                self.branch_fetch_times.pop(0)
            self._update_avg_times()
        self.last_branch_time = datetime.now(KST)

        # Preserve current selection
        current_selection = self.branch_tree.selection()
        selected_branch = None
        if current_selection and self.branch_map:
            # Get the branch name from the selected item
            selected_item = current_selection[0]
            selected_branch = self.branch_tree.item(selected_item)["values"][0]

        # Update branch map
        self.branch_map = branches

        # Clear tree (but keep dates in self.branch_dates for reuse)
        for item in self.branch_tree.get_children():
            self.branch_tree.delete(item)

        # Insert branches with existing dates if available
        for b in branches:
            # Use existing date if available, otherwise show "Loading..."
            commit_date = self.branch_dates.get(b, "Loading..." if not auto_refresh else "")
            self.branch_tree.insert("", "end", values=(b, commit_date))

        # Restore selection if possible
        if selected_branch and selected_branch in branches:
            index = branches.index(selected_branch)
            items = self.branch_tree.get_children()
            if index < len(items):
                self.branch_tree.selection_set(items[index])
                self.branch_tree.see(items[index])

        if auto_refresh:
            self.status_var.set("Auto-refresh: Branch list updated. Fetching metadata...")
        else:
            self.status_var.set("Branch list loaded. Fetching metadata...")

        # Update controls (Sync button becomes available if branches loaded)
        self._update_controls()

    def _on_dates_loaded(self, dates: Dict[str, str], auto_refresh=False, duration=None):
        """Handle successful commit date fetch."""
        # Record metadata fetch time
        if duration is not None:
            self.metadata_fetch_times.append(duration)
            if len(self.metadata_fetch_times) > self.max_samples:
                self.metadata_fetch_times.pop(0)
            self._update_avg_times()

        # Update branch_dates with new information (preserves old dates for branches not in new fetch)
        self.branch_dates.update(dates)

        # Preserve current selection
        current_selection = self.branch_tree.selection()
        selected_index = None
        if current_selection:
            items = self.branch_tree.get_children()
            selected_index = items.index(current_selection[0])

        # Update tree items with dates
        for item in self.branch_tree.get_children():
            branch_name = self.branch_tree.item(item)["values"][0]
            commit_date = self.branch_dates.get(branch_name, "")
            self.branch_tree.item(item, values=(branch_name, commit_date))

        # Restore selection
        if selected_index is not None:
            items = self.branch_tree.get_children()
            if selected_index < len(items):
                self.branch_tree.selection_set(items[selected_index])
                self.branch_tree.see(items[selected_index])

        # Update state
        self.is_refreshing = False
        self._update_controls()

        self.last_metadata_time = datetime.now(KST)

        if auto_refresh:
            self.status_var.set("Auto-refresh completed.")
            logging.info("[Auto-Refresh] Completed successfully")
            self._detect_and_trigger_auto_sync()
        else:
            self.status_var.set("Ready.")

    def _on_refresh_error(self, title: str, message: str, auto_refresh=False):
        """Handle refresh error."""
        self.is_refreshing = False
        self._update_controls()

        if auto_refresh:
            # Silent logging for auto-refresh errors (don't show popup)
            logging.error(f"[Auto-Refresh] {title}: {message}")
            self.status_var.set("Auto-refresh failed (see log)")
        else:
            # Show error popup for manual refresh
            self._on_error(title, message)

    def _on_refresh_cancelled(self, auto_refresh=False):
        """Handle refresh cancellation."""
        self.is_refreshing = False
        self.cancel_refresh = False
        self._update_controls()

        if auto_refresh:
            logging.info("[Auto-Refresh] Cancelled")
            self.status_var.set("Auto-refresh cancelled")
        else:
            logging.info("[Refresh] Cancelled by user")
            self.status_var.set("Refresh cancelled")

    def _update_avg_times(self):
        """Update average times display."""
        # Calculate averages
        avg_branch = sum(self.branch_fetch_times) / len(self.branch_fetch_times) if self.branch_fetch_times else 0
        avg_metadata = sum(self.metadata_fetch_times) / len(self.metadata_fetch_times) if self.metadata_fetch_times else 0
        avg_sync = sum(self.sync_times) / len(self.sync_times) if self.sync_times else 0

        # Format display (separate variables for column alignment)
        branch_str = f"{avg_branch:.1f}s" if avg_branch > 0 else "-"
        metadata_str = f"{avg_metadata:.1f}s" if avg_metadata > 0 else "-"
        sync_str = f"{avg_sync:.1f}s" if avg_sync > 0 else "-"

        self.avg_branch_var.set(f"Avg Branch: {branch_str}")
        self.avg_metadata_var.set(f"Avg Metadata: {metadata_str}")
        self.avg_sync_var.set(f"Avg Sync: {sync_str}")

    def _get_selected_branch(self) -> Optional[str]:
        """Return currently selected branch from treeview."""
        selected = self.branch_tree.selection()
        if not selected:
            return None

        values = self.branch_tree.item(selected[0]).get("values", [])
        if not values:
            return None

        return str(values[0])

    def _disable_auto_sync(self, reason: Optional[str] = None):
        """Disable auto-sync and reset tracking state."""
        self.auto_sync_enabled = False
        self.auto_sync_var.set(False)
        self.auto_sync_tracking_branch = None
        self.auto_sync_last_synced_commit = ""
        self.auto_sync_pending_commit = None
        if reason:
            logging.info(reason)
        self._update_controls()

    def _detect_and_trigger_auto_sync(self):
        """Trigger auto-sync only when selected branch commit changes."""
        if not self.auto_sync_enabled or not self.auto_refresh_enabled:
            return

        selected_branch = self._get_selected_branch()
        if not selected_branch:
            return

        latest_commit = self.branch_dates.get(selected_branch, "")
        if not latest_commit:
            return

        if selected_branch != self.auto_sync_tracking_branch:
            self.auto_sync_tracking_branch = selected_branch
            self.auto_sync_last_synced_commit = latest_commit
            self.auto_sync_pending_commit = None
            logging.info(
                f"[Auto-Sync] Tracking selected branch '{selected_branch}' "
                f"(baseline commit: {latest_commit})"
            )
            return

        if not self.auto_sync_last_synced_commit:
            self.auto_sync_last_synced_commit = latest_commit
            return

        if latest_commit == self.auto_sync_last_synced_commit:
            return

        if self.auto_sync_pending_commit == latest_commit:
            return

        if self.is_syncing:
            logging.warning(
                f"[Auto-Sync] Update detected on '{selected_branch}' "
                f"({self.auto_sync_last_synced_commit} -> {latest_commit}), "
                "but sync is already in progress. Will retry on next auto-refresh."
            )
            return

        logging.info(
            f"[Auto-Sync] Update detected on '{selected_branch}' "
            f"({self.auto_sync_last_synced_commit} -> {latest_commit}). Starting sync."
        )
        self._execute_auto_sync(selected_branch, latest_commit)

    def start_sync(self):
        # Check if branches are loaded
        if not self.branch_map:
            messagebox.showwarning(
                "브랜치 미로드",
                "브랜치 목록이 로드되지 않았습니다.\n\n"
                "Repository를 선택하고 Refresh 버튼을 먼저 눌러주세요."
            )
            return

        # Get selected branch from Treeview
        selected = self.branch_tree.selection()
        if not selected:
            messagebox.showwarning("브랜치 미선택", "동기화할 브랜치를 먼저 선택해주세요.")
            return

        # Extract branch name from selected item
        branch = self.branch_tree.item(selected[0])["values"][0]
        repo = self.repo_var.get()
        mirror = self.mirror_var.get()
        method = self.download_method_var.get()

        # [CHANGE] Record last synced branch for auto-sync
        self.last_synced_branch = branch

        # ZIP mode still replaces local git metadata and files, so keep explicit confirmation.
        if method == "zip" and (self.manager.cwd / ".git").exists():
            confirm = messagebox.askyesno(
                "Confirm Overwrite",
                "A .git folder exists in the current directory.\n\n"
                "Continuing will DELETE the current Git configuration and replace files.\n"
                "Are you sure you want to proceed?"
            )
            if not confirm:
                return

        self.last_sync_try_time = datetime.now(KST)

        # Record sync start time for duration measurement
        self.sync_start_time = time.time()

        # Update state
        self.is_syncing = True
        self._update_controls()

        method_text = "ZIP 다운로드" if method == "zip" else "Git Incremental"
        self.status_var.set(f"Syncing {branch}... ({method_text})")

        logging.info(f"[Sync] Starting sync - Repo: {repo}, Branch: {branch}, Method: {method}, Mirror: {mirror}")

        def task():
            error_message = None
            try:
                self.manager.sync(repo, branch, mirror, logging.info, method=method)
            except Exception as e:
                error_message = str(e)  # 이미 즉시 변환하고 있어서 안전함
            finally:
                # Calculate duration
                sync_duration = time.time() - self.sync_start_time
                # error_message는 except 블록 밖 변수이므로 안전
                self.root.after(0, lambda msg=error_message, dur=sync_duration: self._on_sync_complete(msg, dur))

        threading.Thread(target=task, daemon=True).start()

    def _on_sync_complete(self, error_message: Optional[str], duration: float = None):
        # Update state
        self.is_syncing = False
        self._update_controls()

        if error_message:
            self._on_error("Sync Failed", error_message)
        else:
            # Record sync time on success
            if duration is not None:
                self.sync_times.append(duration)
                if len(self.sync_times) > self.max_samples:
                    self.sync_times.pop(0)
                self._update_avg_times()
            self._on_sync_success()

    def _on_sync_success(self):
        self.last_sync_time = datetime.now(KST)

        self.status_var.set("Sync completed successfully.")

        # Auto-backup after sync if enabled
        if self.auto_backup_var.get():
            logging.info("[Auto-Backup] Starting automatic backup after sync...")
            self._perform_auto_backup()
        else:
            messagebox.showinfo("Success", "Repository sync finished!")
            if self.mode == "Normal":
                self.root.destroy()

    def _on_error(self, title, message):
        # Note: State is managed by caller (_on_sync_complete or _on_refresh_error)

        # Credential 에러인지 확인
        if is_credential_error(message):
            self.status_var.set("인증 실패: Credential 필요")
            logging.warning(f"Credential Error Detected: {message}")

            user_message = (
                "🔒 Git 인증이 필요합니다.\n\n"
                "Private Repository에 접근하려면 인증이 필요합니다.\n\n"
                "해결 방법:\n\n"
                "1. SSH URL 사용 (권장):\n"
                "   • SSH 키 생성: ssh-keygen -t ed25519 -C \"your_email@example.com\"\n"
                "   • GitHub에 공개키 등록: Settings → SSH and GPG keys\n"
                "   • Repository URL을 git@github.com:user/repo.git 형식으로 변경\n\n"
                "2. Personal Access Token (PAT) 사용:\n"
                "   • GitHub → Settings → Developer settings → Personal access tokens\n"
                "   • Token 생성 후 아래 명령어 실행:\n"
                "     git config --global credential.helper store\n"
                "   • Git 명령어 실행 시 Username에 토큰 입력\n\n"
                "3. ZIP Download 사용 (Public Repository만 가능):\n"
                "   • Download Method를 'ZIP Download'로 변경\n\n"
                f"상세 정보:\n{message}"
            )
            messagebox.showerror("Git 인증 필요", user_message)

        # 네트워크 에러인지 확인
        elif self._is_network_error(message):
            self.status_var.set("대기 중: 네트워크 문제 감지됨")
            logging.warning(f"Network Error Detected: {message}")

            user_message = (
                "⚠️ 회사 프록시 서버 또는 네트워크에 문제가 있습니다.\n\n"
                "502/503 에러 또는 연결 시간 초과가 발생했습니다.\n"
                "잠시 후 다시 시도해주세요.\n\n"
                f"상세 정보:\n{message}"
            )
            messagebox.showwarning("네트워크 연결 문제", user_message)
        else:
            # 일반 에러 처리
            self.status_var.set(f"오류: {title}")
            logging.error(f"{title}: {message}")
            messagebox.showerror(title, message)

    def create_archive_backup(self):
        """Create a compressed archive backup of the current local repository."""
        from tkinter import filedialog

        # Ask user to select target directory
        initial_dir = str(self.manager.cwd.parent / "archive_backups")
        target_dir = filedialog.askdirectory(
            title="Select Archive Backup Directory",
            initialdir=initial_dir
        )

        if not target_dir:
            logging.info("Archive backup cancelled by user")
            return

        # Confirm before proceeding
        confirm = messagebox.askyesno(
            "Confirm Archive Backup",
            f"Create archive backup of current repository?\n\n"
            f"Target directory: {target_dir}\n\n"
            f"This will create a compressed ZIP file containing all repository files."
        )

        if not confirm:
            return

        self.status_var.set("Creating archive backup...")
        logging.info(f"[Archive] Starting archive backup to: {target_dir}")

        # Disable buttons during archive creation
        self.btn_archive.configure(state="disabled")
        self.btn_sync.configure(state="disabled")

        def task():
            error_message = None
            archive_path = None
            try:
                archive_path = self.manager.create_archive_backup(
                    Path(target_dir),
                    logging.info
                )
            except Exception as e:
                error_message = str(e)
            finally:
                self.root.after(0, lambda msg=error_message, path=archive_path:
                    self._on_archive_complete(msg, path))

        threading.Thread(target=task, daemon=True).start()

    def _on_archive_complete(self, error_message: Optional[str], archive_path: Optional[Path]):
        """Handle archive backup completion."""
        # Re-enable buttons
        self.btn_archive.configure(state="normal")
        self.btn_sync.configure(state="normal")

        if error_message:
            self.status_var.set("Archive backup failed")
            logging.error(f"Archive backup failed: {error_message}")
            messagebox.showerror("Archive Backup Failed", f"Failed to create archive:\n\n{error_message}")
        else:
            self.status_var.set("Archive backup completed successfully")
            success_message = f"Archive backup created successfully!\n\nLocation: {archive_path}"
            logging.info(f"[Archive] Backup completed: {archive_path}")

            # Ask if user wants to open the directory
            open_dir = messagebox.askyesno(
                "Archive Backup Complete",
                f"{success_message}\n\nOpen backup directory?"
            )

            if open_dir and archive_path:
                try:
                    if sys.platform == "win32":
                        os.startfile(archive_path.parent)
                    elif sys.platform == "darwin":
                        subprocess.run(["open", str(archive_path.parent)])
                    else:
                        subprocess.run(["xdg-open", str(archive_path.parent)])
                except Exception as e:
                    logging.warning(f"Failed to open directory: {e}")

    def _perform_auto_backup(self):
        """Perform automatic backup after sync (no user interaction)."""
        target_dir = self.archive_dir_var.get()

        if not target_dir:
            logging.warning("[Auto-Backup] No archive directory set, skipping auto-backup")
            messagebox.showinfo("Success", "Repository sync finished!")
            if self.mode == "Normal":
                self.root.destroy()
            return

        self.status_var.set("Creating automatic backup...")
        logging.info(f"[Auto-Backup] Creating backup to: {target_dir}")

        def task():
            error_message = None
            archive_path = None
            try:
                archive_path = self.manager.create_archive_backup(
                    Path(target_dir),
                    logging.info
                )
            except Exception as e:
                error_message = str(e)
            finally:
                self.root.after(0, lambda msg=error_message, path=archive_path:
                    self._on_auto_backup_complete(msg, path))

        threading.Thread(target=task, daemon=True).start()

    def _on_auto_backup_complete(self, error_message: Optional[str], archive_path: Optional[Path]):
        """Handle automatic backup completion."""
        if error_message:
            self.status_var.set("Auto-backup failed")
            logging.error(f"[Auto-Backup] Failed: {error_message}")
            messagebox.showerror(
                "Auto-Backup Failed",
                f"Sync completed but auto-backup failed:\n\n{error_message}\n\nPlease check the archive directory settings."
            )
        else:
            self.status_var.set("Sync and auto-backup completed successfully")
            logging.info(f"[Auto-Backup] Completed: {archive_path}")
            messagebox.showinfo(
                "Success",
                f"Repository sync finished!\n\nAuto-backup created:\n{archive_path}"
            )

        if self.mode == "Normal":
            self.root.destroy()

    def _perform_auto_backup_silent(self):
        """Perform automatic backup after auto-sync (silent, no popup)."""
        target_dir = self.archive_dir_var.get()

        if not target_dir:
            logging.warning("[Auto-Sync Backup] No archive directory set, skipping auto-backup")
            # Still refresh metadata
            logging.info("[Auto-Sync] Refreshing metadata after successful sync...")
            self.refresh_branches(auto_refresh=True)
            return

        self.status_var.set("Creating automatic backup after auto-sync...")
        logging.info(f"[Auto-Sync Backup] Creating backup to: {target_dir}")

        def task():
            error_message = None
            archive_path = None
            try:
                archive_path = self.manager.create_archive_backup(
                    Path(target_dir),
                    logging.info
                )
            except Exception as e:
                error_message = str(e)
            finally:
                self.root.after(0, lambda msg=error_message, path=archive_path:
                    self._on_auto_backup_silent_complete(msg, path))

        threading.Thread(target=task, daemon=True).start()

    def _on_auto_backup_silent_complete(self, error_message: Optional[str], archive_path: Optional[Path]):
        """Handle automatic backup completion for auto-sync (silent)."""
        if error_message:
            self.status_var.set("Auto-sync backup failed")
            logging.error(f"[Auto-Sync Backup] Failed: {error_message}")
        else:
            self.status_var.set("Auto-sync and backup completed successfully")
            logging.info(f"[Auto-Sync Backup] Completed: {archive_path}")

        # Always refresh metadata after backup (success or fail)
        logging.info("[Auto-Sync] Refreshing metadata after backup...")
        self.refresh_branches(auto_refresh=True)

    # --- Auto-Refresh ---

    def _toggle_auto_refresh(self):
        """Toggle auto-refresh on/off."""
        self.auto_refresh_enabled = self.auto_refresh_var.get()

        if self.auto_refresh_enabled:
            # Start auto-refresh
            try:
                interval = int(self.auto_refresh_interval_var.get())
                self.auto_refresh_interval = interval
                logging.info(f"[Auto-Refresh] Enabled with interval: {interval} seconds")
                self._schedule_auto_refresh()
            except ValueError:
                messagebox.showerror("Invalid Interval", "Please enter a valid number for interval.")
                self.auto_refresh_var.set(False)
                self.auto_refresh_enabled = False
        else:
            # Stop auto-refresh
            if self.auto_refresh_job:
                self.root.after_cancel(self.auto_refresh_job)
                self.auto_refresh_job = None
            logging.info("[Auto-Refresh] Disabled")
            if self.auto_sync_enabled:
                self._disable_auto_sync("[Auto-Sync] Disabled because Auto-Refresh was turned off")
                self.status_var.set("Auto-Sync disabled (requires Auto-Refresh).")

        self._update_controls()

    # --- Auto-Sync ---

    def _toggle_auto_sync(self):
        """Toggle auto-sync on/off."""
        self.auto_sync_enabled = self.auto_sync_var.get()

        if self.auto_sync_enabled:
            if not self.auto_refresh_enabled:
                messagebox.showwarning(
                    "Auto-Refresh Required",
                    "Auto-Sync works only when Auto-Refresh is enabled.\n\n"
                    "Please enable Auto-Refresh first."
                )
                self._disable_auto_sync()
                return

            selected_branch = self._get_selected_branch()
            if not selected_branch:
                messagebox.showwarning(
                    "No Branch Selected",
                    "Select a branch first. Auto-Sync monitors updates on the selected branch."
                )
                self._disable_auto_sync()
                return

            baseline_commit = self.branch_dates.get(selected_branch, "")
            self.auto_sync_tracking_branch = selected_branch
            self.auto_sync_last_synced_commit = baseline_commit
            self.auto_sync_pending_commit = None
            logging.info(
                f"[Auto-Sync] Enabled. Tracking branch: {selected_branch}, "
                f"baseline commit: {baseline_commit or '(unknown)'}, "
                f"mirror: {self.auto_sync_mirror_var.get()}"
            )
            self.status_var.set(f"Auto-Sync enabled for '{selected_branch}' (waiting for updates).")
        else:
            self._disable_auto_sync("[Auto-Sync] Disabled")
            self.status_var.set("Auto-Sync disabled.")

    def _schedule_auto_refresh(self):
        """Schedule the next auto-refresh."""
        if not self.auto_refresh_enabled:
            return

        # Cancel previous job if exists
        if self.auto_refresh_job:
            self.root.after_cancel(self.auto_refresh_job)

        # Schedule next refresh
        interval_ms = self.auto_refresh_interval * 1000
        self.auto_refresh_job = self.root.after(interval_ms, self._execute_auto_refresh)

    def _execute_auto_refresh(self):
        """Execute auto-refresh and reschedule."""
        if not self.auto_refresh_enabled:
            return

        # Only refresh if branches are already loaded
        if self.branch_map:
            logging.info(f"[Auto-Refresh] Executing automatic refresh (interval: {self.auto_refresh_interval}s)")
            self.refresh_branches(auto_refresh=True)

        # Reschedule next refresh
        self._schedule_auto_refresh()

    def _execute_auto_sync(self, branch: str, target_commit: str):
        """Execute auto-sync immediately for a detected commit update."""
        if not self.auto_sync_enabled or not self.auto_refresh_enabled:
            return

        if self.is_syncing:
            logging.warning("[Auto-Sync] Sync already in progress, skipping update trigger")
            return

        self.auto_sync_pending_commit = target_commit
        self.last_sync_try_time = datetime.now(KST)

        repo = self.repo_var.get()
        mirror = self.auto_sync_mirror_var.get()
        method = self.download_method_var.get()

        auto_sync_start_time = time.time()

        # Update state
        self.is_syncing = True
        self._update_controls()

        method_text = "ZIP 다운로드" if method == "zip" else "Git Incremental"
        self.status_var.set(f"Auto-syncing {branch}... ({method_text})")

        if mirror != self.mirror_var.get():
            logging.info(
                f"[Auto-Sync] Mirror policy split active "
                f"(manual_mirror={self.mirror_var.get()}, auto_sync_mirror={mirror})"
            )
        logging.info(
            f"[Auto-Sync] Starting sync - Repo: {repo}, Branch: {branch}, Method: {method}, "
            f"Mirror: {mirror}, target_commit: {target_commit}"
        )

        def task():
            error_message = None
            try:
                self.manager.sync(repo, branch, mirror, logging.info, method=method)
            except Exception as e:
                error_message = str(e)
            finally:
                sync_duration = time.time() - auto_sync_start_time
                self.root.after(
                    0,
                    lambda msg=error_message, dur=sync_duration, b=branch, c=target_commit:
                        self._on_auto_sync_complete(msg, dur, b, c),
                )

        threading.Thread(target=task, daemon=True).start()

    def _on_auto_sync_complete(
        self,
        error_message: Optional[str],
        duration: float = None,
        branch: Optional[str] = None,
        target_commit: Optional[str] = None,
    ):
        """Handle auto-sync completion."""
        # Update state
        self.is_syncing = False
        self._update_controls()

        if error_message:
            # Log error but don't show popup for auto-sync
            logging.error(f"[Auto-Sync] Failed: {error_message}")
            self.status_var.set("Auto-sync failed (see log)")
            self.auto_sync_pending_commit = None
        else:
            # Record sync time on success
            if duration is not None:
                self.sync_times.append(duration)
                if len(self.sync_times) > self.max_samples:
                    self.sync_times.pop(0)
                self._update_avg_times()

            self.last_sync_time = datetime.now(KST)
            if branch:
                self.last_synced_branch = branch
            if (
                branch
                and target_commit
                and branch == self.auto_sync_tracking_branch
            ):
                self.auto_sync_last_synced_commit = target_commit
            self.auto_sync_pending_commit = None

            self.status_var.set("Auto-sync completed successfully.")
            logging.info("[Auto-Sync] Completed successfully")

            # Auto-backup after auto-sync if enabled
            if self.auto_backup_var.get():
                logging.info("[Auto-Sync] Auto-backup enabled, starting backup...")
                self._perform_auto_backup_silent()
            else:
                # Auto-refresh metadata after successful auto-sync (only if no backup)
                logging.info("[Auto-Sync] Refreshing metadata after successful sync...")
                self.refresh_branches(auto_refresh=True)

    def run(self):
        self.root.mainloop()


# =============================================================================
# 3.5. CLI Mode (Curses TUI) - CliApp
# =============================================================================

class CliApp:
    """Interactive TUI for CLI mode using curses."""

    def __init__(self, manager: GitManager, initial_repo: str):
        self.manager = manager
        self.repo_url = initial_repo
        self.branches = ["main"]  # Start with main branch
        self.branch_dates = {}

        # State
        self.selected_repo_idx = REPO_CHOICES.index(initial_repo) if initial_repo in REPO_CHOICES else 0
        self.selected_branch_idx = 0
        self.download_method = "git"  # "git" or "zip"

        # Timestamps
        self.last_branch_try_time = None
        self.last_metadata_try_time = None
        self.last_sync_try_time = None
        self.last_branch_time = None
        self.last_metadata_time = None
        self.last_sync_time = None

        # Status message
        self.status_msg = "Press 'r' to refresh branches"

        # Screens: "repo" or "branch"
        self.current_screen = "repo"

        # Layout constraints to keep curses drawing safe on narrow terminals
        self.min_height = 15
        self.min_width = 50

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        """Safely draw text within the current window bounds."""
        height, width = self.stdscr.getmaxyx()
        if y < 0 or y >= height:
            return

        # Clamp x and truncate text if needed
        if x < 0:
            text = text[-x:]
            x = 0
        if x >= width:
            return

        max_len = max(width - x, 0)
        if max_len == 0:
            return

        try:
            self.stdscr.addstr(y, x, text[:max_len], attr)
        except curses.error:
            # Ignore drawing errors on extremely small terminals
            pass

    def _format_elapsed(self, since: datetime) -> str:
        delta_seconds = int((datetime.now(KST) - since).total_seconds())
        if delta_seconds < 0:
            delta_seconds = 0
        if delta_seconds < 60:
            return f"{delta_seconds}s"
        if delta_seconds < 3600:
            minutes = delta_seconds // 60
            seconds = delta_seconds % 60
            return f"{minutes}m {seconds}s"
        if delta_seconds < 86400:
            hours = delta_seconds // 3600
            minutes = (delta_seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        days = delta_seconds // 86400
        hours = (delta_seconds % 86400) // 3600
        return f"{days}d {hours}h"

    def _format_time_pair(self, label: str, try_dt: Optional[datetime], done_dt: Optional[datetime]) -> str:
        if try_dt:
            try_str = f"{try_dt.strftime('%H:%M:%S')} ({self._format_elapsed(try_dt)} ago)"
        else:
            try_str = "-"
        if done_dt:
            done_str = f"{done_dt.strftime('%H:%M:%S')} ({self._format_elapsed(done_dt)} ago)"
        else:
            done_str = "-"
        return f"{label} Try: {try_str} | Done: {done_str}"

    def _draw_small_terminal_warning(self, height: int, width: int) -> None:
        """Render a compact warning when the terminal is too small."""
        warning_lines = [
            "Terminal is too small for the TUI.",
            f"Current size: {width}x{height} (min {self.min_width}x{self.min_height})",
            "Rotate to landscape or widen the window to continue.",
            "Press 'q' to exit.",
        ]

        start_row = max((height - len(warning_lines)) // 2, 0)
        for idx, line in enumerate(warning_lines):
            self._safe_addstr(start_row + idx, 2, line, curses.color_pair(4))

    def run(self, stdscr):
        """Main curses loop."""
        # Initialize colors
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)    # Success
        curses.init_pair(2, curses.COLOR_RED, -1)      # Error
        curses.init_pair(3, curses.COLOR_BLUE, -1)     # Info
        curses.init_pair(4, curses.COLOR_YELLOW, -1)   # Warning
        curses.init_pair(5, curses.COLOR_CYAN, -1)     # Highlight
        curses.init_pair(6, curses.COLOR_WHITE, -1)    # Normal

        # Settings
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(False)  # Blocking input
        stdscr.keypad(True)  # Enable arrow keys

        self.stdscr = stdscr

        # Main loop
        while True:
            try:
                self._draw_screen()
                key = stdscr.getch()

                if key == ord('q') or key == ord('Q'):
                    break

                if self.current_screen == "repo":
                    if not self._handle_repo_screen(key):
                        break
                elif self.current_screen == "branch":
                    if not self._handle_branch_screen(key):
                        break

            except KeyboardInterrupt:
                break
            except Exception as e:
                self.status_msg = f"Error: {str(e)}"
                stdscr.refresh()

    def _draw_screen(self):
        """Draw the current screen."""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()

        if height < self.min_height or width < self.min_width:
            self._draw_small_terminal_warning(height, width)
            self.stdscr.refresh()
            return

        # Header
        self._draw_header()

        # Content
        if self.current_screen == "repo":
            self._draw_repo_screen()
        elif self.current_screen == "branch":
            self._draw_branch_screen()

        # Footer
        self._draw_footer(height, width)

        self.stdscr.refresh()

    def _draw_header(self):
        """Draw header with title and timestamps."""
        _, width = self.stdscr.getmaxyx()

        # Title
        title = f"Git Sync Tool - {self.manager.cwd.name}"
        title_display = title if len(title) < width - 2 else title[: width - 5] + "..."
        title_start = max((width - len(title_display)) // 2, 0)
        self._safe_addstr(0, title_start, title_display, curses.A_BOLD | curses.color_pair(5))

        # Timestamps
        row = 2
        ts_str = self._format_time_pair("Branch", self.last_branch_try_time, self.last_branch_time)
        self._safe_addstr(row, 2, ts_str, curses.color_pair(3))
        row += 1

        ts_str = self._format_time_pair("Metadata", self.last_metadata_try_time, self.last_metadata_time)
        self._safe_addstr(row, 2, ts_str, curses.color_pair(3))
        row += 1

        ts_str = self._format_time_pair("Sync", self.last_sync_try_time, self.last_sync_time)
        self._safe_addstr(row, 2, ts_str, curses.color_pair(3))

    def _draw_footer(self, height, width):
        """Draw footer with help text."""
        footer_row = height - 2

        if footer_row < 1:
            return

        if self.current_screen == "repo":
            help_text = "↑/↓: Navigate | Enter: Select | q: Quit"
        else:
            help_text = "↑/↓: Navigate | r: Refresh | s: Sync | m: Method | b: Back | q: Quit"

        divider = "─" * max(width - 4, 0)
        self._safe_addstr(footer_row, 2, divider)
        self._safe_addstr(footer_row + 1, max((width - len(help_text)) // 2, 0), help_text, curses.color_pair(6))

        # Status message
        if self.status_msg:
            status_row = footer_row - 1
            # Truncate if too long
            max_len = width - 4
            display_msg = self.status_msg[:max_len] if len(self.status_msg) > max_len else self.status_msg
            self._safe_addstr(status_row, 2, display_msg, curses.color_pair(4))

    def _draw_repo_screen(self):
        """Draw repository selection screen."""
        start_row = 5

        self._safe_addstr(start_row, 2, "Select Repository:", curses.A_BOLD)
        start_row += 2

        for i, repo in enumerate(REPO_CHOICES):
            attr = curses.A_REVERSE if i == self.selected_repo_idx else curses.A_NORMAL
            # Truncate long URLs
            display_repo = repo if len(repo) < 70 else repo[:67] + "..."
            self._safe_addstr(start_row + i, 4, f"[{i+1}] {display_repo}", attr)

    def _draw_branch_screen(self):
        """Draw branch selection screen."""
        start_row = 5

        # Current repository
        self._safe_addstr(start_row, 2, "Repository:", curses.A_BOLD)
        repo_display = self.repo_url if len(self.repo_url) < 60 else self.repo_url[:57] + "..."
        self._safe_addstr(start_row, 15, repo_display, curses.color_pair(5))

        # Download method
        start_row += 1
        method_text = "Git Incremental" if self.download_method == "git" else "ZIP Download"
        self._safe_addstr(start_row, 2, "Method:", curses.A_BOLD)
        self._safe_addstr(start_row, 15, method_text, curses.color_pair(3))

        # Branches
        start_row += 2
        self._safe_addstr(start_row, 2, "Available Branches:", curses.A_BOLD)
        start_row += 2

        height, _ = self.stdscr.getmaxyx()
        max_branches = max(height - start_row - 5, 1)  # Leave space for footer

        # Calculate scroll window
        if self.selected_branch_idx >= max_branches:
            scroll_offset = self.selected_branch_idx - max_branches + 1
        else:
            scroll_offset = 0

        visible_branches = self.branches[scroll_offset:scroll_offset + max_branches]

        for i, branch in enumerate(visible_branches):
            actual_idx = scroll_offset + i
            attr = curses.A_REVERSE if actual_idx == self.selected_branch_idx else curses.A_NORMAL

            # Branch name
            branch_display = f"[{actual_idx+1}] {branch}"

            # Add date if available
            if branch in self.branch_dates:
                date_str = self.branch_dates[branch]
                branch_display += f"  ({date_str})"

            self._safe_addstr(start_row + i, 4, branch_display, attr)

    def _handle_repo_screen(self, key) -> bool:
        """Handle input on repository screen. Returns False to exit."""
        if key == curses.KEY_UP:
            self.selected_repo_idx = max(0, self.selected_repo_idx - 1)
        elif key == curses.KEY_DOWN:
            self.selected_repo_idx = min(len(REPO_CHOICES) - 1, self.selected_repo_idx + 1)
        elif key == ord('\n') or key == curses.KEY_ENTER or key == 10:
            # Select repository
            self.repo_url = REPO_CHOICES[self.selected_repo_idx]
            self.current_screen = "branch"
            self.status_msg = "Press 'r' to refresh branches"

        return True

    def _handle_branch_screen(self, key) -> bool:
        """Handle input on branch screen. Returns False to exit."""
        if key == curses.KEY_UP:
            self.selected_branch_idx = max(0, self.selected_branch_idx - 1)
        elif key == curses.KEY_DOWN:
            self.selected_branch_idx = min(len(self.branches) - 1, self.selected_branch_idx + 1)
        elif key == ord('b') or key == ord('B'):
            # Back to repo selection
            self.current_screen = "repo"
            self.status_msg = "Select repository"
        elif key == ord('m') or key == ord('M'):
            # Toggle download method
            self.download_method = "zip" if self.download_method == "git" else "git"
            method_text = "Git Incremental" if self.download_method == "git" else "ZIP Download"
            self.status_msg = f"Download method changed to: {method_text}"
        elif key == ord('r') or key == ord('R'):
            # Refresh branches
            self._refresh_branches()
        elif key == ord('s') or key == ord('S'):
            # Sync selected branch
            self._sync_branch()

        return True

    def _refresh_branches(self):
        """Refresh branch list from remote."""
        self.last_branch_try_time = datetime.now(KST)
        self.status_msg = "Refreshing branches..."
        self.stdscr.clear()
        self._draw_screen()
        self.stdscr.refresh()

        try:
            # Fetch branches
            branches = self.manager.get_remote_branches_fast(self.repo_url)
            self.branches = branches
            self.last_branch_time = datetime.now(KST)

            # Fetch dates (this may take time)
            self.status_msg = "Fetching branch metadata..."
            self.stdscr.clear()
            self._draw_screen()
            self.stdscr.refresh()

            self.last_metadata_try_time = datetime.now(KST)
            dates = self.manager.fetch_branch_dates(self.repo_url)
            self.branch_dates.update(dates)

            # Success
            self.last_metadata_time = datetime.now(KST)
            self.status_msg = f"Refreshed successfully: {len(branches)} branches found"

        except Exception as e:
            error_msg = str(e)
            if is_credential_error(error_msg):
                self.status_msg = "Auth failed. Use SSH URL or setup credentials (see log)"
            elif is_network_error(error_msg):
                self.status_msg = "Network error. Check connection (see log)"
            else:
                self.status_msg = f"Refresh failed: {error_msg[:60]}"

    def _sync_branch(self):
        """Sync selected branch."""
        if not self.branches:
            self.status_msg = "No branches available. Press 'r' to refresh."
            return

        branch = self.branches[self.selected_branch_idx]
        self.last_sync_try_time = datetime.now(KST)

        # Show progress message
        self.status_msg = f"Syncing {branch}..."
        self.stdscr.clear()
        self._draw_screen()
        self.stdscr.refresh()

        # Disable curses temporarily for sync output
        curses.endwin()

        try:
            print(f"\n{'='*60}")
            print(f"Syncing: {branch}")
            print(f"Repository: {self.repo_url}")
            print(f"Method: {self.download_method}")
            print(f"{'='*60}\n")

            self.manager.sync(self.repo_url, branch, True, print, method=self.download_method)

            # Success
            self.last_sync_time = datetime.now(KST)
            print(f"\n{'='*60}")
            print("✓ Sync completed successfully!")
            print(f"{'='*60}\n")
            print("Press any key to continue...")

        except Exception as e:
            print(f"\n{'='*60}")
            print(f"✗ Sync failed: {str(e)}")
            print(f"{'='*60}\n")
            print("Press any key to continue...")

        # Wait for user input
        import sys
        if _HAVE_TERMIOS:
            import tty
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        elif _HAVE_MSVCRT:
            msvcrt.getch()
        else:
            input()

        # Restore curses
        self.stdscr = curses.initscr()
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_BLUE, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_CYAN, -1)
        curses.init_pair(6, curses.COLOR_WHITE, -1)
        curses.curs_set(0)
        self.stdscr.keypad(True)

        self.status_msg = f"Sync completed for {branch}"


# =============================================================================
# 4. Entry Point & CLI Fallbacks
# =============================================================================

def is_network_error(error_msg: str) -> bool:
    """네트워크 관련 에러인지 확인 (CLI/GUI 공통)"""
    network_indicators = [
        "502", "503", "504",  # HTTP proxy errors
        "timed out", "timeout",
        "connection", "connect",
        "network", "proxy",
        "git clone failed", "git fetch",
        "could not resolve host",
        "unable to access",
    ]
    error_lower = error_msg.lower()
    return any(indicator in error_lower for indicator in network_indicators)


def is_credential_error(error_msg: str) -> bool:
    """Credential 관련 에러인지 확인"""
    credential_indicators = [
        "username",
        "password",
        "credential",
        "authentication failed",
        "could not read username",
        "could not read password",
        "terminal prompts disabled",
        "no credentials",
        "missing credential",
        "authentication required",
        "invalid credentials",
        "401", "403",  # HTTP auth errors
    ]
    error_lower = error_msg.lower()
    return any(indicator in error_lower for indicator in credential_indicators)


def cli_select_repo() -> Tuple[Optional[str], Optional[str]]:
    """CLI Mode selection for Repo and Loop/Normal"""
    print("\n--- Git Sync CLI Mode ---")
    
    print("Select Mode:")
    print("[1] Normal Mode (Run once)")
    print("[2] Loop Mode (Repeat)")
    m = _strip_text(input("Choice (1/2): "))
    mode = "Loop Mode" if m == "2" else "Normal Mode"

    print("\nSelect Repository:")
    for i, r in enumerate(REPO_CHOICES, 1):
        print(f"[{i}] {r}")
    
    try:
        r_idx = int(_strip_text(input(f"Choice (1-{len(REPO_CHOICES)}): "))) - 1
        repo = REPO_CHOICES[r_idx]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return None, None
        
    return repo, mode

def main():
    parser = argparse.ArgumentParser(description="Professional Git Sync Tool")
    parser.add_argument("--no-gui", action="store_true", help="Force CLI mode")
    parser.add_argument("--repo", help="Pre-select repository")
    parser.add_argument("--loop", action="store_true", help="Loop mode")
    parser.add_argument("--archive", metavar="DIR", help="Create archive backup to specified directory and exit")
    args = parser.parse_args()

    cwd = Path.cwd()
    log_path = resolve_log_path(cwd)
    setup_logging(log_path)
    
    # Load protection list
    protect_list_path = cwd / "sync_protect.list"
    extra_protect_dirs, extra_protect_files = build_log_protect_entries(cwd, log_path)

    try:
        manager = GitManager(
            cwd,
            protect_list_path,
            extra_protect_dirs=extra_protect_dirs,
            extra_protect_files=extra_protect_files,
        )
    except Exception as e:
        print(f"Initialization Error: {e}")
        return

    # Handle archive mode (CLI only, exit after completion)
    if args.archive:
        target_dir = Path(args.archive)
        print(f"\n{'='*60}")
        print("Archive Backup Mode")
        print(f"{'='*60}")
        print(f"Target directory: {target_dir}")
        print(f"Source: {cwd}")
        print(f"{'='*60}\n")

        try:
            archive_path = manager.create_archive_backup(target_dir, print)
            print(f"\n{'='*60}")
            print("✓ Archive backup completed successfully!")
            print(f"Archive: {archive_path}")
            print(f"{'='*60}\n")
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"✗ Archive backup failed: {e}")
            print(f"{'='*60}\n")
            logging.error(f"Archive backup failed: {e}")
            return

        return  # Exit after archive operation

    # Determine Mode
    use_gui = _HAVE_TK and not args.no_gui

    if use_gui:
        repo = args.repo or REPO_CHOICES[0]
        mode = "Loop Mode" if args.loop else "Normal Mode"
        app = GuiApp(manager, repo, mode)
        app.run()
    else:
        # CLI Mode - Use curses TUI if available
        repo = args.repo or REPO_CHOICES[0]

        if _HAVE_CURSES:
            # Interactive TUI mode
            logging.info("Starting interactive CLI mode (curses TUI)")
            app = CliApp(manager, repo)
            try:
                curses.wrapper(app.run)
            except KeyboardInterrupt:
                print("\nExited.")
            except Exception as e:
                print(f"\nTUI Error: {e}")
                logging.error(f"TUI Error: {e}")
        else:
            # Fallback to simple CLI
            logging.info("Curses not available, using simple CLI mode")
            print("\n⚠️  Interactive TUI not available (curses library not found)")
            print("Falling back to simple CLI mode\n")

            mode_str = "Loop Mode" if args.loop else "Normal Mode"

            if not repo:
                repo, mode_str = cli_select_repo()
                if not repo: return

            logging.info("CLI mode started for %s (%s)", repo, mode_str)
            try:
                branches = manager.get_remote_branches_fast(repo)
                for i, b in enumerate(branches, 1):
                    print(f"[{i}] {b}")

                sel = _strip_text(input("Select branch number: "))
                branch = branches[int(sel)-1]

                manager.sync(repo, branch, True, logging.info)

            except Exception as e:
                error_msg = str(e)
                if is_credential_error(error_msg):
                    logging.warning(f"Credential Error: {error_msg}")
                    print("\n" + "="*60)
                    print("🔒 Git 인증 필요")
                    print("="*60)
                    print("Private Repository에 접근하려면 인증이 필요합니다.")
                    print("\n해결 방법:")
                    print("\n1. SSH URL 사용 (권장):")
                    print("   ssh-keygen -t ed25519 -C \"your_email@example.com\"")
                    print("   → GitHub에 공개키 등록 (Settings → SSH keys)")
                    print("   → Repository URL을 git@github.com:user/repo.git 형식으로 변경")
                    print("\n2. Personal Access Token (PAT):")
                    print("   git config --global credential.helper store")
                    print("   → GitHub에서 Token 생성 (Settings → Developer settings)")
                    print("   → Git 명령어 실행 시 Username에 토큰 입력")
                    print("\n3. ZIP Download (Public Repository만):")
                    print("   → GUI 실행 후 Download Method를 'ZIP Download'로 변경")
                    print(f"\n상세 정보: {error_msg}")
                    print("="*60 + "\n")
                elif is_network_error(error_msg):
                    logging.warning(f"Network Error: {error_msg}")
                    print("\n" + "="*60)
                    print("⚠️  네트워크 연결 문제")
                    print("="*60)
                    print("회사 프록시 서버 또는 네트워크에 문제가 있습니다.")
                    print("502/503 에러 또는 연결 시간 초과가 발생했습니다.")
                    print("잠시 후 다시 시도해주세요.")
                    print(f"\n상세 정보: {error_msg}")
                    print("="*60 + "\n")
                else:
                    logging.error(f"CLI Error: {error_msg}")
                    print(f"\nError: {error_msg}")

if __name__ == "__main__":
    main()
