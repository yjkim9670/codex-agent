#!/usr/bin/env python3
"""
z00_sync_git_final.py
Refactored Sync Helper with Responsive Layout, Directory Info, and Async GUI.
"""

import argparse
import ctypes
import hashlib
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Iterable, Iterator, List, NamedTuple, Optional, Set, Tuple

try:
    from ctypes import wintypes
    _HAVE_CTYPES_WINTYPES = True
except ImportError:
    wintypes = None
    _HAVE_CTYPES_WINTYPES = False

# UI Imports
try:
    import tkinter as tk
    from tkinter import scrolledtext, ttk, messagebox
    _HAVE_TK = True
except ImportError:
    _HAVE_TK = False

try:
    import ttkbootstrap as tb
    _HAVE_TTKBOOTSTRAP = True
except ImportError:
    tb = None
    _HAVE_TTKBOOTSTRAP = False

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


# Configuration - Carbon Dark Theme
ACCENT_COLOR = "#8ab4f8"    # Cool blue accent
ACCENT_HOVER = "#a8c7fa"    # Lighter accent for hover
SUCCESS_COLOR = "#7ccf8a"   # Muted green
WARNING_COLOR = "#f2c14e"   # Muted amber
ERROR_COLOR = "#ff7b72"     # Muted red
BG_COLOR = "#161819"        # Carbon background
BG_SECONDARY = "#222629"    # Carbon panel
BORDER_COLOR = "#3a4045"    # Carbon border
TEXT_COLOR = "#eceff1"      # Primary text
TEXT_SECONDARY = "#bcc5cc"  # Secondary text
TEXT_MUTED = "#8f989f"      # Muted text

UI_FONT_FAMILY_DISPLAY = "Segoe UI"
UI_FONT_FAMILY_TEXT = "Segoe UI"
DEFAULT_ARCHIVE_DIR = str(Path.cwd().parent / "archive_backups")
UI_FONT_FAMILY_MONO = "Consolas"

ARCHIVE_TEXT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cc",
    ".cfg",
    ".cmd",
    ".conf",
    ".cpp",
    ".css",
    ".csv",
    ".do",
    ".env",
    ".f",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".log",
    ".lst",
    ".m",
    ".md",
    ".mk",
    ".py",
    ".rst",
    ".sdc",
    ".sh",
    ".sql",
    ".sv",
    ".svh",
    ".tcl",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".v",
    ".vh",
    ".xml",
    ".yaml",
    ".yml",
}
ARCHIVE_TEXT_FILENAMES = {
    ".dockerignore",
    ".editorconfig",
    ".env",
    ".gitattributes",
    ".gitignore",
    ".gitmodules",
    "dockerfile",
    "makefile",
}
ARCHIVE_BINARY_EXTENSIONS = {
    ".7z",
    ".bin",
    ".bmp",
    ".db",
    ".dll",
    ".doc",
    ".docx",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".npy",
    ".pdf",
    ".pkl",
    ".png",
    ".ppt",
    ".pptm",
    ".pptx",
    ".pyc",
    ".so",
    ".sqlite",
    ".tar",
    ".tgz",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".zip",
}
ARCHIVE_OFFICE_DRM_EXTENSIONS = {
    ".xls",
    ".xlsx",
    ".xlsm",
    ".ppt",
    ".pptx",
    ".pptm",
}
ARCHIVE_EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    ".vscode",
}
ARCHIVE_WORKSPACE_DIR_NAME = "workspace"
ARCHIVE_WORKSPACE_AUTOMATION_DB_REL = PurePosixPath(
    f"{ARCHIVE_WORKSPACE_DIR_NAME}/automation_history.db"
)
ARCHIVE_OFFICE_DRM_CACHE_ENV = "GIT_SYNC_OFFICE_DRM_CACHE_DIR"
ARCHIVE_OFFICE_DRM_CACHE_VERSION = "z01_office_drm_resave_v1"
ARCHIVE_OFFICE_DRM_HASH_CHUNK_SIZE = 1024 * 1024
TTKBOOTSTRAP_THEME_ENV = "GIT_SYNC_TTKBOOTSTRAP_THEME"
TTKBOOTSTRAP_DEFAULT_THEME = "darkly"

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
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Global I/O semaphore settings (cross-process)
GIT_SYNC_IO_SLOTS = _read_int_env("GIT_SYNC_IO_SLOTS", 1, minimum=1)
GIT_SYNC_IO_STALE_SECONDS = _read_int_env("GIT_SYNC_IO_STALE_SECONDS", 60, minimum=60)
GIT_SYNC_IO_POLL_SECONDS = _read_float_env("GIT_SYNC_IO_POLL_SECONDS", 0.5, minimum=0.2)
GIT_SYNC_IO_RELEASE_RETRY_SECONDS = _read_int_env("GIT_SYNC_IO_RELEASE_RETRY_SECONDS", 60, minimum=1)
AUTO_REFRESH_INTERVAL_DEFAULT_SECONDS = 60
AUTO_SYNC_MIRROR_DEFAULT = _read_bool_env("GIT_SYNC_AUTO_MIRROR", True)
CLI_AUTO_UPDATE_INTERVAL_DEFAULT_SECONDS = _read_float_env(
    "GIT_SYNC_CLI_WATCH_INTERVAL",
    60.0,
    minimum=1.0,
)

LOG_PATH_ENV = "GIT_SYNC_LOG_PATH"
DEFAULT_RUNTIME_LOG_DIR = ".sync_runtime"
DEFAULT_LOG_FILENAME = "sync_run.log"
DEFAULT_EXTERNAL_LOG_ROOT = "git-sync"
LOCAL_PRESERVE_DIRS: Tuple[str, ...] = ("summary",)


class RemoteBranchSnapshot(NamedTuple):
    commit_sha: str
    committed_at: str


class ArchiveOfficeDrmCacheRef(NamedTuple):
    key: str
    path: Path
    source_size: int
    source_sha256: str


class ArchiveOfficeDrmMiss(NamedTuple):
    rel_path: Path
    staged_path: Path
    cache_ref: ArchiveOfficeDrmCacheRef


def _git_env() -> Dict[str, str]:
    """Ensure git never opens interactive prompts so GUI threads cannot hang."""
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GCM_INTERACTIVE", "never")
    return env


def _convert_to_kst_string(iso_date_str: str) -> str:
    """
    Convert ISO8601 date string to KST format with text representation.

    Args:
        iso_date_str: Date string in ISO8601 format (e.g., "2025-12-08 15:30:00 +0900")

    Returns:
        Formatted string in KST (e.g., "2025-12-08 15:30:00 KST")
    """
    try:
        # Parse ISO8601 string (handles various formats including timezone offsets)
        # Try different formats
        for fmt in [
            "%Y-%m-%d %H:%M:%S %z",  # 2025-12-08 15:30:00 +0900
            "%Y-%m-%dT%H:%M:%S%z",   # 2025-12-08T15:30:00+0900
            "%Y-%m-%d %H:%M:%S%z",   # 2025-12-08 15:30:00+0900
        ]:
            try:
                dt = datetime.strptime(iso_date_str.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            # If no format matched, return original string
            return iso_date_str

        # Convert to KST
        dt_kst = dt.astimezone(KST)

        # Format as "YYYY-MM-DD HH:MM:SS KST"
        return dt_kst.strftime("%Y-%m-%d %H:%M:%S KST")

    except Exception:
        # If conversion fails, return original string
        return iso_date_str


def _resolve_script_build_info(script_path: Path) -> Tuple[str, str]:
    """
    Resolve lightweight build info for display in GUI.

    Returns:
        (current_version, last_updated_kst)
    """
    current_version = "local"
    last_updated = "-"
    env = _git_env()

    try:
        raw = subprocess.check_output(
            [
                "git",
                "log",
                "-1",
                "--format=%h|%cd",
                "--date=format:%Y-%m-%d %H:%M:%S %z",
                "--",
                script_path.name,
            ],
            cwd=script_path.parent,
            text=True,
            encoding=SUBPROCESS_TEXT_ENCODING,
            errors=SUBPROCESS_TEXT_ERRORS,
            stderr=subprocess.DEVNULL,
            timeout=5,
            env=env,
        ).strip()
        if raw:
            parts = raw.split("|", 1)
            if parts and parts[0].strip():
                current_version = parts[0].strip()
            if len(parts) == 2 and parts[1].strip():
                last_updated = _convert_to_kst_string(parts[1].strip())
                return current_version, last_updated
    except Exception:
        pass

    try:
        mtime = datetime.fromtimestamp(script_path.stat().st_mtime, tz=timezone.utc)
        last_updated = mtime.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    except OSError:
        last_updated = "-"

    return current_version, last_updated


class GlobalIOSemaphore:
    """
    Cross-process I/O semaphore using lock files in the system temp directory.

    This limits concurrent heavy sync phases across different working folders.
    """

    def __init__(self, slots: int, stale_seconds: int, poll_seconds: float):
        self.slots = max(1, slots)
        self.stale_seconds = max(60, stale_seconds)
        self.poll_seconds = max(0.2, poll_seconds)
        self.lock_root = Path(tempfile.gettempdir()) / "git_sync_io_slots"
        self._ensure_lock_root()

    def _lock_file(self, slot: int) -> Path:
        return self.lock_root / f"slot_{slot}.lock"

    def _ensure_lock_root(self) -> None:
        try:
            self.lock_root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(
                f"I/O semaphore lock directory unavailable: {self.lock_root} ({e})"
            ) from e

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
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        if pid <= 0:
            return False
        if os.name == "nt":
            return self._is_pid_alive_windows(pid)
        return self._is_pid_alive_posix(pid)

    def _is_pid_alive_posix(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return False
        return True

    def _is_pid_alive_windows(self, pid: int) -> bool:
        if pid > 0xFFFFFFFF:
            return False
        if not _HAVE_CTYPES_WINTYPES:
            return self._is_pid_alive_posix(pid)

        process_query_limited_information = 0x1000
        still_active = 259
        error_invalid_parameter = 87
        error_access_denied = 5

        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            open_process = kernel32.OpenProcess
            open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            open_process.restype = wintypes.HANDLE

            get_exit_code_process = kernel32.GetExitCodeProcess
            get_exit_code_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            get_exit_code_process.restype = wintypes.BOOL

            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL

            handle = open_process(process_query_limited_information, False, pid)
            if not handle:
                error_code = ctypes.get_last_error()
                if error_code == error_access_denied:
                    return True
                if error_code == error_invalid_parameter:
                    return False
                return False

            try:
                exit_code = wintypes.DWORD()
                if not get_exit_code_process(handle, ctypes.byref(exit_code)):
                    error_code = ctypes.get_last_error()
                    if error_code == error_access_denied:
                        return True
                    return False
                return exit_code.value == still_active
            finally:
                close_handle(handle)
        except Exception:
            return False

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
        if pid is not None:
            try:
                if self._is_pid_alive(pid):
                    return
            except Exception as e:
                log_fn(
                    f"[I/O semaphore] Warning: PID liveness check failed for "
                    f"{lock_path.name} (pid={pid}): {e}"
                )

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
            self._ensure_lock_root()
            for slot in range(self.slots):
                lock_path = self._lock_file(slot)
                self._cleanup_stale(lock_path, log_fn)

                try:
                    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError:
                    continue
                except FileNotFoundError:
                    # The temp lock directory can disappear during long-running sessions.
                    self._ensure_lock_root()
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
        retry_deadline = time.time() + GIT_SYNC_IO_RELEASE_RETRY_SECONDS
        last_error: Optional[OSError] = None

        while True:
            try:
                lock_path.unlink()
                log_fn(f"[I/O semaphore] Released {lock_path.name}")
                return
            except FileNotFoundError:
                return
            except OSError as e:
                last_error = e
                if time.time() >= retry_deadline:
                    break
                time.sleep(1.0)

        try:
            os.chmod(lock_path, 0o666)
            lock_path.unlink()
            log_fn(
                f"[I/O semaphore] Force-released {lock_path.name} "
                f"after {GIT_SYNC_IO_RELEASE_RETRY_SECONDS}s wait"
            )
        except FileNotFoundError:
            return
        except OSError as e:
            detail = e
            if last_error is not None:
                detail = OSError(f"{last_error}; final attempt: {e}")
            log_fn(f"[I/O semaphore] Warning: failed to release lock {lock_path}: {detail}")


# =============================================================================
# 1. Logging & Utilities
# =============================================================================

def _is_path_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _sanitize_repo_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return safe or "repo"


def _default_external_log_path(cwd: Path) -> Path:
    return (
        Path(tempfile.gettempdir())
        / DEFAULT_EXTERNAL_LOG_ROOT
        / _sanitize_repo_name(cwd.name)
        / DEFAULT_LOG_FILENAME
    )


def resolve_log_path(cwd: Path) -> Tuple[Path, Optional[Path]]:
    fallback = _default_external_log_path(cwd)
    raw = os.environ.get(LOG_PATH_ENV, "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        if _is_path_within(candidate, cwd):
            return fallback, candidate
        return candidate, None
    return fallback, None


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
        force=True,
    )
    logging.info("Logging initialized at %s", log_path)


@contextmanager
def suspend_repo_file_handlers(cwd: Path) -> Iterator[int]:
    root_logger = logging.getLogger()
    suspended_handlers: List[logging.FileHandler] = []

    for handler in list(root_logger.handlers):
        if not isinstance(handler, logging.FileHandler):
            continue
        base_filename = getattr(handler, "baseFilename", "")
        if not base_filename:
            continue
        if not _is_path_within(Path(base_filename), cwd):
            continue

        try:
            handler.flush()
        except Exception:
            pass
        handler.close()
        root_logger.removeHandler(handler)
        suspended_handlers.append(handler)

    try:
        yield len(suspended_handlers)
    finally:
        for handler in suspended_handlers:
            root_logger.addHandler(handler)


def read_protect_list(path: Path) -> Tuple[List[str], List[str]]:
    dirs: List[str] = ["workspace", "sources"]
    files: List[str] = []
    if path.exists() and path.name != "sync_protect.list":
        files.append(path.name)

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

    def _path_lexists(self, path: Path) -> bool:
        try:
            return os.path.lexists(path)
        except (OSError, SystemError, ValueError):
            return False

    def _path_is_symlink(self, path: Path) -> bool:
        try:
            return path.is_symlink()
        except (OSError, SystemError, ValueError):
            return False

    def _path_is_file(self, path: Path) -> bool:
        try:
            return path.is_file()
        except (OSError, SystemError, ValueError):
            return False

    def _path_is_dir(self, path: Path) -> bool:
        try:
            return path.is_dir()
        except (OSError, SystemError, ValueError):
            return False

    def _make_path_writable(self, path: Path) -> None:
        try:
            os.chmod(path, 0o777)
        except (OSError, SystemError, ValueError):
            pass

    def _make_tree_writable(self, path: Path) -> None:
        if not self._path_lexists(path):
            return

        self._make_path_writable(path)
        if not self._path_is_dir(path) or self._path_is_symlink(path):
            return

        try:
            for current, dirs, files in os.walk(path, topdown=False):
                current_path = Path(current)
                self._make_path_writable(current_path)
                for name in files:
                    self._make_path_writable(current_path / name)
                for name in dirs:
                    self._make_path_writable(current_path / name)
        except (OSError, SystemError, ValueError):
            pass

    def _remove_path_once(self, path: Path) -> None:
        if not self._path_lexists(path):
            return

        if self._path_is_symlink(path) or self._path_is_file(path):
            self._make_path_writable(path)
            path.unlink()
            return

        self._make_tree_writable(path)
        shutil.rmtree(path)

    def _parse_github_repo(self, repo_url: str) -> Tuple[str, str]:
        """
        Extract the owner and repository name from a GitHub URL.
        https://github.com/yjkim9670/GL-FW-DV-Constraint-Review
        -> ("yjkim9670", "GL-FW-DV-Constraint-Review")
        """
        match = re.search(r'github\.com[:/]([^/]+)/([^/\.]+)', repo_url)
        if not match:
            raise ValueError(f"Invalid GitHub URL: {repo_url}")
        return match.group(1), match.group(2)

    def get_remote_branches_fast(self, repo: str) -> List[str]:
        """Fast retrieval of branch names using ls-remote."""
        return sorted(self.get_remote_branch_heads_fast(repo))

    def get_remote_branch_heads_fast(self, repo: str) -> Dict[str, str]:
        """Return branch names and remote HEAD SHAs using one ls-remote call."""
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

        branches = {}
        for line in raw.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1].startswith("refs/heads/"):
                branches[parts[1].replace("refs/heads/", "", 1)] = parts[0]
        
        if not branches:
            raise RuntimeError("No remote branches found.")
        return branches

    def get_remote_branch_head(self, repo: str, branch: str) -> str:
        """Return the current remote commit SHA for one branch."""
        ref_name = f"refs/heads/{branch}"
        cmd = ["git", "ls-remote", "--heads", repo, ref_name]
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
            raise RuntimeError(f"Timed out while checking branch head: {branch}") from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to check branch head: {e.output}") from e

        for line in raw.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == ref_name:
                return parts[0]

        raise RuntimeError(f"Branch not found on remote: {branch}")

    def get_remote_branch_snapshot(self, repo: str, branch: str) -> RemoteBranchSnapshot:
        """Return the remote branch commit SHA and committer time in KST."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="meta_branch_", dir=Path(tempfile.gettempdir())))
        env = _git_env()
        ref_name = f"refs/heads/{branch}"
        remote_ref = f"refs/remotes/origin/{branch}"

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
            subprocess.run(
                [
                    "git",
                    "fetch",
                    "--no-tags",
                    "--depth",
                    "1",
                    "origin",
                    f"+{ref_name}:{remote_ref}",
                ],
                cwd=tmp_dir,
                check=True,
                capture_output=True,
                text=True,
                encoding=SUBPROCESS_TEXT_ENCODING,
                errors=SUBPROCESS_TEXT_ERRORS,
                env=env,
                timeout=GIT_FETCH_TIMEOUT,
            )
            raw = subprocess.check_output(
                [
                    "git",
                    "show",
                    "-s",
                    "--format=%H%x09%cd",
                    "--date=format:%Y-%m-%d %H:%M:%S %z",
                    remote_ref,
                ],
                text=True,
                encoding=SUBPROCESS_TEXT_ENCODING,
                errors=SUBPROCESS_TEXT_ERRORS,
                cwd=tmp_dir,
                env=env,
                timeout=GIT_BRANCH_TIMEOUT,
            ).strip()
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Timed out while fetching branch commit metadata: {branch}") from e
        except subprocess.CalledProcessError as e:
            detail = e.stderr or e.stdout or ""
            raise RuntimeError(f"Failed to fetch branch commit metadata: {detail}") from e
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        commit_sha, _, committed_at_raw = raw.partition("\t")
        if not commit_sha:
            raise RuntimeError(f"Branch metadata unavailable: {branch}")

        committed_at = _convert_to_kst_string(committed_at_raw) if committed_at_raw else "-"
        return RemoteBranchSnapshot(commit_sha=commit_sha, committed_at=committed_at)

    def get_local_ref_snapshot(self, ref: str) -> RemoteBranchSnapshot:
        """Return commit SHA and commit time for a local git ref."""
        raw = self._run_git_checked(
            [
                "git",
                "show",
                "-s",
                "--format=%H%x09%cd",
                "--date=format:%Y-%m-%d %H:%M:%S %z",
                ref,
            ],
            timeout=GIT_BRANCH_TIMEOUT,
        ).strip()
        commit_sha, _, committed_at_raw = raw.partition("\t")
        if not commit_sha:
            raise RuntimeError(f"Local git ref metadata unavailable: {ref}")
        committed_at = _convert_to_kst_string(committed_at_raw) if committed_at_raw else "-"
        return RemoteBranchSnapshot(commit_sha=commit_sha, committed_at=committed_at)

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

    def sync(
        self,
        repo: str,
        branch: str,
        mirror: bool,
        log_callback: Callable[[str], None],
        method: str = "git",
    ) -> RemoteBranchSnapshot:
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
        log_callback(
            f"Loaded sync protect list: {len(self.protect_dirs)} dirs, {len(self.protect_files)} files"
        )
        preserved_dirs: List[Tuple[str, Path]] = []
        for rel_dir in LOCAL_PRESERVE_DIRS:
            snapshot_root = self._snapshot_local_dir(rel_dir, log_callback)
            if snapshot_root is not None:
                preserved_dirs.append((rel_dir, snapshot_root))

        try:
            if method == "git":
                return self._sync_git_incremental(repo, branch, mirror, log_callback)

            if method != "zip":
                raise ValueError(f"Unsupported sync method: {method}")

            # ZIP path keeps legacy full-download behavior.
            tmp_dir = None
            io_lock = self.io_semaphore.acquire(log_callback, f"{self.cwd.name}:{branch}:{method}")
            try:
                git_dir = self.cwd / ".git"
                if self._path_lexists(git_dir):
                    self._remove_git_dir(git_dir, "existing working copy", log_callback)

                tmp_dir = self._download_zip(repo, branch, log_callback)
                protected_snapshot = self._capture_protected_file_state(
                    self._collect_rel_files(tmp_dir),
                    log_callback,
                )

                try:
                    if mirror:
                        self._backup_and_delete(tmp_dir, log_callback)
                    else:
                        log_callback("Mirror OFF: Skipping local cleanup.")

                    self._copy_files(tmp_dir, log_callback)
                    self._remove_git_dir(self.cwd / ".git", "post-copy", log_callback)
                finally:
                    self._restore_protected_file_state(*protected_snapshot, log_callback)

                log_callback("Sync completed successfully.")
                return RemoteBranchSnapshot(commit_sha="", committed_at="-")
            finally:
                if tmp_dir and self._path_lexists(tmp_dir):
                    self._remove_git_dir(tmp_dir / ".git", "temp cleanup", log_callback)
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                self.io_semaphore.release(io_lock, log_callback)
        finally:
            git_dir = self.cwd / ".git"
            try:
                if self._path_lexists(git_dir):
                    self._remove_git_dir(git_dir, "post-sync cleanup", log_callback)
            except Exception as e:
                log_callback(f"Warning: Failed to remove .git folder after sync: {e}")
            for rel_dir, snapshot_root in reversed(preserved_dirs):
                self._restore_local_dir(rel_dir, snapshot_root, log_callback)

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
            stdout_raw = completed.stdout
            if isinstance(stdout_raw, bytes):
                stdout_raw = stdout_raw.decode(errors="replace")
            return (stdout_raw or "").strip()
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Git command timed out: {' '.join(command)}") from e
        except subprocess.CalledProcessError as e:
            stderr_raw = e.stderr
            stdout_raw = e.stdout
            if isinstance(stderr_raw, bytes):
                stderr_raw = stderr_raw.decode(errors="replace")
            if isinstance(stdout_raw, bytes):
                stdout_raw = stdout_raw.decode(errors="replace")
            stderr = (stderr_raw or "").strip()
            stdout = (stdout_raw or "").strip()
            detail = stderr or stdout or "No additional details."
            raise RuntimeError(f"Git command failed: {' '.join(command)}\n{detail}") from e

    def _snapshot_local_dir(self, rel_dir: str, log_fn: Callable[[str], None]) -> Optional[Path]:
        target = self.cwd / rel_dir
        if not self._path_is_dir(target):
            return None

        snapshot_root = Path(
            tempfile.mkdtemp(prefix="sync_preserve_", dir=Path(tempfile.gettempdir()))
        )
        snapshot_path = snapshot_root / "snapshot"
        try:
            shutil.copytree(target, snapshot_path, dirs_exist_ok=True)
        except Exception:
            shutil.rmtree(snapshot_root, ignore_errors=True)
            raise

        log_fn(f"Preserved local directory before sync: {rel_dir}")
        return snapshot_root

    def _restore_local_dir(
        self,
        rel_dir: str,
        snapshot_root: Optional[Path],
        log_fn: Callable[[str], None],
    ) -> None:
        if snapshot_root is None:
            return

        snapshot_path = snapshot_root / "snapshot"
        try:
            if not self._path_lexists(snapshot_path):
                log_fn(f"Warning: Missing preserved snapshot for {rel_dir}; restore skipped.")
                return

            target = self.cwd / rel_dir
            if self._path_lexists(target):
                try:
                    if self._path_is_symlink(target) or self._path_is_file(target):
                        target.unlink()
                    else:
                        shutil.rmtree(target)
                except OSError as e:
                    log_fn(f"Warning: Failed to clear {rel_dir} before restore: {e}")
                    return

            shutil.copytree(snapshot_path, target, dirs_exist_ok=True)
            log_fn(f"Restored preserved local directory: {rel_dir}")
        except Exception as e:
            log_fn(f"Warning: Failed to restore preserved directory {rel_dir}: {e}")
        finally:
            shutil.rmtree(snapshot_root, ignore_errors=True)

    def _ensure_incremental_repo(self, repo: str, log_fn: Callable[[str], None]) -> None:
        git_dir = self.cwd / ".git"
        if self._path_lexists(git_dir):
            try:
                self._run_git_checked(["git", "rev-parse", "--is-inside-work-tree"], timeout=GIT_BRANCH_TIMEOUT)
            except RuntimeError:
                log_fn("Detected invalid .git metadata. Reinitializing repository metadata.")
                self._remove_git_dir(git_dir, "invalid working copy metadata", log_fn)

        if not self._path_lexists(git_dir):
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

    def _normalize_rel_path(self, rel_path: str) -> str:
        return rel_path.replace("\\", "/").strip("/")

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

    def _list_tracked_files_for_ref(self, ref: str) -> List[str]:
        raw = self._run_git_checked(
            ["git", "ls-tree", "-r", "--name-only", ref],
            timeout=GIT_BRANCH_TIMEOUT,
        )
        if not raw:
            return []

        files: List[str] = []
        for line in raw.splitlines():
            normalized = self._normalize_rel_path(line)
            if not normalized or normalized.startswith(".git/"):
                continue
            files.append(normalized)
        return files

    def _collect_rel_files(self, root: Path) -> List[str]:
        rel_files: List[str] = []
        for current, _, files in os.walk(root):
            base = Path(current)
            for name in files:
                try:
                    rel_path = self._normalize_rel_path(str((base / name).relative_to(root)))
                except ValueError:
                    continue
                if rel_path and not rel_path.startswith(".git/"):
                    rel_files.append(rel_path)
        return rel_files

    def _capture_protected_file_state(
        self,
        candidate_files: Iterable[str],
        log_fn: Callable[[str], None],
    ) -> Tuple[Optional[Path], Set[str], Set[str]]:
        protected_paths: Set[str] = set()
        for rel_path in candidate_files:
            normalized = self._normalize_rel_path(rel_path)
            if not normalized or normalized.startswith(".git/"):
                continue
            if self._should_protect(normalized, is_dir=False):
                protected_paths.add(normalized)

        if not protected_paths:
            return None, set(), set()

        snapshot_root = Path(tempfile.mkdtemp(prefix="sync_protect_", dir=Path(tempfile.gettempdir())))
        preserved_paths: Set[str] = set()
        missing_paths: Set[str] = set()
        try:
            for rel_path in sorted(protected_paths):
                full_path = self.cwd / rel_path
                target = snapshot_root / rel_path

                if self._path_is_dir(full_path) and not self._path_is_symlink(full_path):
                    shutil.copytree(full_path, target, dirs_exist_ok=True)
                    preserved_paths.add(rel_path)
                    continue

                if self._path_lexists(full_path):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(full_path, target, follow_symlinks=False)
                    preserved_paths.add(rel_path)
                else:
                    missing_paths.add(rel_path)
        except Exception:
            shutil.rmtree(snapshot_root, ignore_errors=True)
            raise

        log_fn(
            "Prepared protected snapshot for tracked sync targets: "
            f"{len(preserved_paths)} preserved, {len(missing_paths)} absent."
        )
        return snapshot_root, preserved_paths, missing_paths

    def _remove_local_path(self, rel_path: str, log_fn: Callable[[str], None]) -> None:
        target = self.cwd / rel_path
        if not self._path_lexists(target):
            return

        try:
            if self._path_is_dir(target) and not self._path_is_symlink(target):
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as e:
            log_fn(f"Warning: Failed to clear protected path {rel_path}: {e}")

    def _restore_protected_file_state(
        self,
        snapshot_root: Optional[Path],
        preserved_paths: Set[str],
        missing_paths: Set[str],
        log_fn: Callable[[str], None],
    ) -> None:
        if snapshot_root is None:
            return

        try:
            restore_targets = sorted(preserved_paths | missing_paths)
            for rel_path in restore_targets:
                self._remove_local_path(rel_path, log_fn)

            restored_count = 0
            for rel_path in sorted(preserved_paths):
                source = snapshot_root / rel_path
                target = self.cwd / rel_path
                if self._path_is_dir(source) and not self._path_is_symlink(source):
                    shutil.copytree(source, target, dirs_exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target, follow_symlinks=False)
                restored_count += 1

            log_fn(
                "Reapplied protect-list exclusions after sync update: "
                f"restored {restored_count}, kept {len(missing_paths)} absent."
            )
        finally:
            shutil.rmtree(snapshot_root, ignore_errors=True)

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
                    if self._path_is_symlink(full_path):
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

    def _sync_git_incremental(
        self,
        repo: str,
        branch: str,
        mirror: bool,
        log_fn: Callable[[str], None],
    ) -> RemoteBranchSnapshot:
        io_lock = self.io_semaphore.acquire(log_fn, f"{self.cwd.name}:{branch}:git")
        try:
            self._ensure_incremental_repo(repo, log_fn)

            log_fn("Running optimized sync: selected-branch fetch -> checkout -> reset -> mirror-clean")
            refspec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
            self._run_git_checked(
                ["git", "fetch", "--depth", "1", "--prune", "origin", refspec],
                timeout=GIT_FETCH_TIMEOUT,
            )
            target_ref = f"origin/{branch}"
            snapshot = self.get_local_ref_snapshot(target_ref)
            log_fn(
                "Fetched selected branch "
                f"{branch} at {snapshot.commit_sha[:12]} "
                f"({snapshot.committed_at})."
            )
            protected_snapshot = self._capture_protected_file_state(
                self._list_tracked_files_for_ref(target_ref),
                log_fn,
            )
            try:
                with suspend_repo_file_handlers(self.cwd) as suspended_count:
                    if suspended_count:
                        log_fn(
                            "Temporarily suspended repository-local file logging "
                            "during checkout/reset."
                        )

                    self._run_git_checked(
                        ["git", "checkout", "-f", "-B", "__sync_work", target_ref],
                        timeout=GIT_CLONE_TIMEOUT,
                    )
                    self._run_git_checked(
                        ["git", "reset", "--hard", target_ref],
                        timeout=GIT_CLONE_TIMEOUT,
                    )

                if mirror:
                    self._run_mirror_cleanup_incremental(log_fn)
                else:
                    log_fn("Mirror OFF: Skipping local cleanup.")
            finally:
                self._restore_protected_file_state(*protected_snapshot, log_fn)

            log_fn("Sync completed successfully.")
            return snapshot
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
        Download a ZIP archive from GitHub and extract it.

        Notes:
        1. Branch slashes are handled because GitHub converts them to hyphens.
        2. GIT_CLONE_TIMEOUT is applied to ZIP downloads.
        3. Temporary ZIP files are removed even when a failure occurs.
        4. Extracted folders are detected by most recent creation time.
        5. Download progress is reported through the callback.
        6. Network errors distinguish timeouts from proxy failures.
        """
        base = self.cwd.parent / "temp"
        base.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="zip_", dir=base))

        zip_path = None
        try:
            # Extract owner/repo from the GitHub URL.
            owner, repo_name = self._parse_github_repo(repo)

            # [Note 1] Convert branch slashes to hyphens for GitHub ZIP folder names.
            # The URL keeps the original branch name, while GitHub converts / to - in the folder.
            sanitized_branch = branch.replace('/', '-')
            zip_url = f"https://github.com/{owner}/{repo_name}/archive/refs/heads/{branch}.zip"

            log_fn(f"[ZIP Download] Target URL: {zip_url}")
            log_fn(f"[ZIP Download] Branch name in URL: {branch} (original, with slashes)")
            log_fn(f"[ZIP Download] Expected folder name: {repo_name}-{sanitized_branch} (GitHub converts / to -)")

            # ZIP file path with a safe file name.
            zip_filename = f"{repo_name}-{sanitized_branch}.zip"
            zip_path = tmp_dir / zip_filename
            log_fn(f"[ZIP Download] Local file: {zip_path}")

            # [Notes 2 and 5] Timeout handling and progress callback state.
            download_start_time = time.time()
            last_log_time = [download_start_time]
            downloaded_bytes = [0]

            # Add a User-Agent header for better proxy compatibility.
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/zip,*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive'
            }

            log_fn(f"[ZIP Download] Request headers: User-Agent={headers['User-Agent'][:50]}...")
            log_fn(f"[ZIP Download] Timeout: {GIT_CLONE_TIMEOUT} seconds")

            # Attach headers through urllib.request.Request.
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

                            # Log progress in 10% increments.
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

            # Extract the archive.
            extract_dir = tmp_dir / "extracted"
            extract_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # [Note 1] GitHub ZIP folder name: {repo_name}-{sanitized_branch}
            extracted_folder = extract_dir / f"{repo_name}-{sanitized_branch}"

            # [Note 4] Detect the extracted folder by most recent modification time.
            if not extracted_folder.exists():
                log_fn(f"Expected folder not found: {extracted_folder.name}")
                log_fn("Searching for alternative extracted folder...")

                # Sort child directories by modification time, newest first.
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

            # [Note 3] Remove the ZIP file after a successful extraction.
            if zip_path and zip_path.exists():
                file_size_mb = zip_path.stat().st_size / (1024 * 1024)
                zip_path.unlink()
                log_fn(f"Cleaned up ZIP file ({file_size_mb:.1f}MB)")

            return extracted_folder

        # [Note 6] Detailed network error messages.
        except socket.timeout as e:
            raise RuntimeError(
                f"Download timed out after {GIT_CLONE_TIMEOUT} seconds. "
                f"The network may be unstable or the repository may be too large. "
                f"Try the Git Sync method."
            ) from e

        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError(
                    f"HTTP 401: Authentication is required.\n\n"
                    f"Private repositories require authentication.\n"
                    f"ZIP download does not support authentication.\n\n"
                    f"Resolution:\n"
                    f"  - Switch to the 'Git Sync (Incremental)' method.\n"
                    f"  - Configure Git authentication with one of these options:\n"
                    f"    - SSH key: ~/.ssh/id_rsa (recommended)\n"
                    f"    - Personal Access Token (PAT):\n"
                    f"      git config --global credential.helper store\n"
                    f"      git clone <URL> (enter the PAT when prompted)\n\n"
                    f"Create a PAT in GitHub -> Settings -> Developer settings -> Personal access tokens"
                ) from e
            elif e.code == 403:
                raise RuntimeError(
                    f"HTTP 403: Access is forbidden.\n\n"
                    f"Private repositories do not support ZIP download.\n\n"
                    f"Resolution:\n"
                    f"  - Switch to the 'Git Sync (Incremental)' method.\n"
                    f"  - Check Git authentication settings:\n"
                    f"    - SSH key: ~/.ssh/id_rsa\n"
                    f"    - Personal Access Token: git config credential.helper"
                ) from e
            elif e.code == 404:
                raise RuntimeError(
                    f"HTTP 404: Repository or branch not found.\n\n"
                    f"Possible causes:\n"
                    f"  1. Branch '{branch}' does not exist.\n"
                    f"  2. The repository is private. ZIP download supports public repositories only.\n"
                    f"  3. The repository name is misspelled.\n\n"
                    f"Resolution:\n"
                    f"  - Use Refresh to check the branch list.\n"
                    f"  - Use 'Git Sync (Incremental)' for private repositories.\n"
                    f"    SSH key or Personal Access Token authentication is required."
                ) from e
            elif e.code in (502, 503, 504):
                raise RuntimeError(
                    f"GitHub server error ({e.code}). "
                    f"The corporate proxy server may have a temporary issue. "
                    f"Try again later."
                ) from e
            else:
                raise RuntimeError(f"HTTP error {e.code}: {e.reason}") from e

        except urllib.error.URLError as e:
            error_str = str(e).lower()
            if "timed out" in error_str or "timeout" in error_str:
                raise RuntimeError(
                    f"Download timed out. Check the network connection."
                ) from e
            elif "proxy" in error_str:
                raise RuntimeError(
                    f"Proxy authentication failed. Check the system proxy settings.\n"
                    f"Details: {e.reason}"
                ) from e
            else:
                raise RuntimeError(f"Network error: {e.reason}") from e

        except zipfile.BadZipFile as e:
            raise RuntimeError(
                f"The ZIP file is corrupted. The download may have been interrupted. "
                f"Try again."
            ) from e

        except Exception as e:
            raise RuntimeError(f"ZIP download failed: {e}") from e

        finally:
            # [Note 3] Remove temporary ZIP files even after failures.
            if zip_path and zip_path.exists():
                try:
                    zip_path.unlink()
                    log_fn("Cleaned up incomplete ZIP file")
                except Exception:
                    pass  # Ignore cleanup failures while handling the original error.

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

    def _archive_path_is_relative_to(self, path: Path, base: Path) -> bool:
        try:
            path.relative_to(base)
            return True
        except ValueError:
            return False

    def _archive_backup_path(self, target_dir: Path) -> Path:
        return Path(target_dir) / f"{self.cwd.name}_backup.tar.gz"

    def _build_archive_filters(
        self,
        target_dir: Path,
    ) -> Tuple[Path, Callable[[Path], bool], Callable[[Path, bool], bool]]:
        target_dir = Path(target_dir)
        archive_path = self._archive_backup_path(target_dir)
        cwd_resolved = self.cwd.resolve()
        target_dir_resolved = target_dir.resolve()
        archive_path_resolved = archive_path.resolve()
        excluded_backup_dir = (
            target_dir_resolved
            if self._archive_path_is_relative_to(target_dir_resolved, cwd_resolved)
            else None
        )

        def should_skip_path(path: Path) -> bool:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path.absolute()

            try:
                rel_path = path.relative_to(self.cwd)
            except ValueError:
                try:
                    rel_path = resolved.relative_to(cwd_resolved)
                except ValueError:
                    rel_path = None

            if rel_path and any(
                part in ARCHIVE_EXCLUDED_DIR_NAMES for part in rel_path.parts
            ):
                return True
            if resolved == archive_path_resolved:
                return True
            if excluded_backup_dir and (
                resolved == excluded_backup_dir
                or self._archive_path_is_relative_to(resolved, excluded_backup_dir)
            ):
                return True
            return False

        def should_archive_rel_path(rel_path: Path, is_dir: bool) -> bool:
            return self._archive_rel_is_workspace_allowed(rel_path, is_dir)

        return archive_path, should_skip_path, should_archive_rel_path

    def _archive_rel_is_in_publish_tree(self, rel_path: Path, is_dir: bool) -> bool:
        parts = rel_path.parts
        if len(parts) < 2 or parts[0] != ARCHIVE_WORKSPACE_DIR_NAME:
            return False

        publish_search_parts = parts[1:] if is_dir else parts[1:-1]
        return "publish" in publish_search_parts

    def _archive_rel_is_workspace_allowed(self, rel_path: Path, is_dir: bool) -> bool:
        parts = rel_path.parts
        if not parts or parts[0] != ARCHIVE_WORKSPACE_DIR_NAME:
            return True

        if not is_dir and PurePosixPath(rel_path.as_posix()) == ARCHIVE_WORKSPACE_AUTOMATION_DB_REL:
            return True

        return self._archive_rel_is_in_publish_tree(rel_path, is_dir)

    def _should_normalize_archive_text(self, file_path: Path) -> bool:
        suffix = file_path.suffix.lower()
        name = file_path.name.lower()

        if suffix in ARCHIVE_BINARY_EXTENSIONS:
            return False
        if suffix in ARCHIVE_TEXT_EXTENSIONS or name in ARCHIVE_TEXT_FILENAMES:
            return True

        try:
            with file_path.open("rb") as handle:
                sample = handle.read(8192)
        except OSError:
            return False

        if not sample:
            return True
        if b"\0" in sample:
            return False

        try:
            sample.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    def _normalize_archive_text_newlines(self, data: bytes) -> bytes:
        return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

    def _apply_archive_file_mode(self, tar_info: tarfile.TarInfo, rel_path: Path) -> None:
        if rel_path.suffix.lower() == ".sh":
            tar_info.mode = (tar_info.mode or 0o644) | 0o755

    def _is_archive_office_drm_target(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in ARCHIVE_OFFICE_DRM_EXTENSIONS

    def _collect_archive_office_drm_files(
        self,
        should_skip_path: Callable[[Path], bool],
        should_archive_rel_path: Callable[[Path, bool], bool],
    ) -> List[Tuple[Path, Path]]:
        targets: List[Tuple[Path, Path]] = []

        for root, dirs, files in os.walk(self.cwd):
            root_path = Path(root)
            if should_skip_path(root_path):
                dirs[:] = []
                continue

            kept_dirs = []
            for dir_name in dirs:
                dir_path = root_path / dir_name
                if should_skip_path(dir_path):
                    continue
                if not dir_path.is_symlink():
                    kept_dirs.append(dir_name)
            dirs[:] = kept_dirs

            for file_name in files:
                file_path = root_path / file_name
                if should_skip_path(file_path):
                    continue
                if file_path.is_symlink() or not file_path.is_file():
                    continue
                if not self._is_archive_office_drm_target(file_path):
                    continue

                try:
                    rel_path = file_path.relative_to(self.cwd)
                except ValueError:
                    continue
                if not should_archive_rel_path(rel_path, False):
                    continue
                targets.append((file_path, rel_path))

        targets.sort(key=lambda item: item[1].as_posix().lower())
        return targets

    def get_archive_office_drm_targets(self, target_dir: Path) -> List[Path]:
        _archive_path, should_skip_path, should_archive_rel_path = self._build_archive_filters(
            target_dir
        )
        return [
            rel_path
            for _source_path, rel_path in self._collect_archive_office_drm_files(
                should_skip_path,
                should_archive_rel_path,
            )
        ]

    def _find_archive_office_drm_helper(self) -> Path:
        helper_name = "z01_excel_drm_unprotect.py"
        candidates = [
            Path(__file__).resolve().with_name(helper_name),
            self.cwd / helper_name,
        ]

        seen: Set[Path] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = candidate.absolute()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.is_file():
                return resolved

        searched = ", ".join(str(path) for path in candidates)
        raise FileNotFoundError(f"Office DRM helper script not found: {searched}")

    def _archive_office_drm_cache_namespace(self) -> str:
        try:
            cwd_key = str(self.cwd.resolve())
        except OSError:
            cwd_key = str(self.cwd.absolute())

        digest = hashlib.sha256(cwd_key.encode("utf-8", errors="replace")).hexdigest()
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.cwd.name).strip("._-")
        if not safe_name:
            safe_name = "repository"
        return f"{safe_name}_{digest[:16]}"

    def _archive_office_drm_cache_root(self) -> Path:
        env_value = os.environ.get(ARCHIVE_OFFICE_DRM_CACHE_ENV)
        if env_value:
            base_dir = Path(env_value).expanduser()
        elif os.name == "nt":
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                base_dir = Path(local_app_data)
            else:
                base_dir = Path.home() / "AppData" / "Local"
            base_dir = base_dir / DEFAULT_EXTERNAL_LOG_ROOT / "office_drm_cache"
        elif sys.platform == "darwin":
            base_dir = Path.home() / "Library" / "Caches" / DEFAULT_EXTERNAL_LOG_ROOT / "office_drm_cache"
        else:
            xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
            base_dir = Path(xdg_cache_home).expanduser() if xdg_cache_home else Path.home() / ".cache"
            base_dir = base_dir / DEFAULT_EXTERNAL_LOG_ROOT / "office_drm_cache"

        return (
            base_dir
            / self._archive_office_drm_cache_namespace()
            / ARCHIVE_OFFICE_DRM_CACHE_VERSION
        )

    def _sha256_file(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(ARCHIVE_OFFICE_DRM_HASH_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _archive_office_drm_cache_ref(self, source_path: Path) -> ArchiveOfficeDrmCacheRef:
        source_stat = source_path.stat()
        source_sha256 = self._sha256_file(source_path)
        suffix = source_path.suffix.lower()
        key_material = "|".join(
            [
                ARCHIVE_OFFICE_DRM_CACHE_VERSION,
                suffix,
                str(source_stat.st_size),
                source_sha256,
            ]
        )
        key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
        cache_path = (
            self._archive_office_drm_cache_root()
            / key[:2]
            / f"{key}{suffix}"
        )
        return ArchiveOfficeDrmCacheRef(
            key=key,
            path=cache_path,
            source_size=source_stat.st_size,
            source_sha256=source_sha256,
        )

    def _archive_office_drm_cache_is_valid(self, cache_path: Path) -> bool:
        try:
            return cache_path.is_file() and cache_path.stat().st_size > 0
        except OSError:
            return False

    def _store_archive_office_drm_cache(
        self,
        staged_path: Path,
        cache_ref: ArchiveOfficeDrmCacheRef,
    ) -> None:
        cache_ref.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = cache_ref.path.with_name(f"{cache_ref.path.name}.tmp-{os.getpid()}")
        try:
            shutil.copy2(staged_path, temp_path)
            os.replace(str(temp_path), str(cache_ref.path))
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

    def _run_archive_office_drm_resave(self, stage_dir: Path, log_fn: Callable) -> None:
        if os.name != "nt":
            raise RuntimeError(
                "Archive contains Office files that must be re-saved before backup, "
                "but Office COM is only available on Windows. Run archive backup on "
                "Windows with pywin32 and Microsoft Office installed."
            )

        helper_path = self._find_archive_office_drm_helper()
        command = [sys.executable, "-u", str(helper_path), "--stage-dir", str(stage_dir)]

        log_fn(f"Running Office DRM re-save helper: {helper_path}")
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(
            command,
            cwd=str(self.cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=SUBPROCESS_TEXT_ENCODING,
            errors=SUBPROCESS_TEXT_ERRORS,
            bufsize=1,
            env=env,
        )

        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.rstrip("\r\n")
                if line:
                    log_fn(line)

        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(
                f"Office DRM re-save failed before archive creation "
                f"(exit code={return_code})."
            )

    def _prepare_archive_office_drm_stage(
        self,
        stage_dir: Path,
        office_drm_files: List[Tuple[Path, Path]],
        log_fn: Callable,
    ) -> Dict[str, Path]:
        staged_sources: Dict[str, Path] = {}
        cache_hits = 0
        duplicate_misses = 0
        unique_misses: Dict[str, ArchiveOfficeDrmMiss] = {}
        cache_root = self._archive_office_drm_cache_root()

        log_fn(f"Office DRM cache: {cache_root}")

        for source_path, rel_path in office_drm_files:
            cache_ref = self._archive_office_drm_cache_ref(source_path)
            rel_path_key = rel_path.as_posix()

            if self._archive_office_drm_cache_is_valid(cache_ref.path):
                staged_sources[rel_path_key] = cache_ref.path
                cache_hits += 1
                continue

            existing_miss = unique_misses.get(cache_ref.key)
            if existing_miss is not None:
                staged_sources[rel_path_key] = existing_miss.staged_path
                duplicate_misses += 1
                continue

            staged_path = stage_dir / rel_path
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, staged_path)
            staged_sources[rel_path_key] = staged_path
            unique_misses[cache_ref.key] = ArchiveOfficeDrmMiss(
                rel_path=rel_path,
                staged_path=staged_path,
                cache_ref=cache_ref,
            )

        log_fn(
            "Office DRM cache summary: "
            f"{cache_hits} hit(s), {len(unique_misses)} miss(es)"
            + (f", {duplicate_misses} duplicate miss target(s)" if duplicate_misses else "")
        )

        if unique_misses:
            self._run_archive_office_drm_resave(stage_dir, log_fn)
            stored_count = 0
            for miss in unique_misses.values():
                try:
                    self._store_archive_office_drm_cache(
                        miss.staged_path,
                        miss.cache_ref,
                    )
                    stored_count += 1
                except Exception as e:
                    log_fn(
                        "Warning: Failed to update Office DRM cache for "
                        f"{miss.rel_path.as_posix()}: {e}"
                    )
            log_fn(f"Office DRM cache updated: {stored_count} file(s)")
        else:
            log_fn("Office DRM re-save helper skipped; all target files were cache hits.")

        return staged_sources

    def _add_archive_entry(self, tarf: tarfile.TarFile, path: Path, rel_path: Path) -> int:
        arcname = rel_path.as_posix()
        tar_info = tarf.gettarinfo(str(path), arcname=arcname)

        if tar_info.isfile():
            self._apply_archive_file_mode(tar_info, rel_path)
            data = path.read_bytes()
            original_size = len(data)
            if self._should_normalize_archive_text(path):
                data = self._normalize_archive_text_newlines(data)
                tar_info.size = len(data)
            tarf.addfile(tar_info, BytesIO(data))
            return original_size

        tarf.addfile(tar_info)
        return path.lstat().st_size

    def create_archive_backup(
        self,
        target_dir: Path,
        log_fn: Callable,
        skip_office_drm: bool = False,
    ) -> Path:
        """
        Create a compressed archive of the current local repository.

        Args:
            target_dir: Directory where the archive will be saved
            log_fn: Logging callback function
            skip_office_drm: If True, exclude Office DRM target files instead of COM re-save.

        Returns:
            Path to the created archive file
        """
        # Create target directory if it doesn't exist
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Generate archive filename (fixed name, no timestamp)
        archive_path = self._archive_backup_path(target_dir)
        archive_name = archive_path.name

        log_fn(f"Creating archive backup: {archive_name}")
        log_fn(f"Target directory: {target_dir}")

        # Remove old backup with same name if exists (overwrite mode)
        if archive_path.exists():
            archive_path.unlink()
            log_fn(f"Removed existing archive: {archive_name}")

        total_files = 0
        total_size = 0
        _archive_path, should_skip_path, should_archive_rel_path = self._build_archive_filters(
            target_dir
        )

        office_drm_stage = None
        try:
            archive_source_overrides: Dict[str, Path] = {}
            office_drm_excluded_paths: Set[str] = set()
            log_fn(
                "Workspace archive scope: "
                f"{ARCHIVE_WORKSPACE_DIR_NAME}/**/publish/**, "
                f"{ARCHIVE_WORKSPACE_AUTOMATION_DB_REL.as_posix()}"
            )
            office_drm_files = self._collect_archive_office_drm_files(
                should_skip_path,
                should_archive_rel_path,
            )
            if office_drm_files:
                log_fn(f"Office DRM re-save target count: {len(office_drm_files)}")
                sample_targets = ", ".join(
                    rel_path.as_posix()
                    for _, rel_path in office_drm_files[:5]
                )
                if len(office_drm_files) > 5:
                    sample_targets += ", ..."
                log_fn(f"Office DRM targets: {sample_targets}")

                if skip_office_drm:
                    office_drm_excluded_paths = {
                        rel_path.as_posix()
                        for _, rel_path in office_drm_files
                    }
                    log_fn(
                        "Office DRM re-save skipped; "
                        f"excluded {len(office_drm_excluded_paths)} target file(s) from archive."
                    )
                else:
                    office_drm_stage = tempfile.TemporaryDirectory(
                        prefix="ctg_archive_office_drm_"
                    )
                    archive_source_overrides = self._prepare_archive_office_drm_stage(
                        Path(office_drm_stage.name),
                        office_drm_files,
                        log_fn,
                    )

            with tarfile.open(archive_path, 'w:gz', format=tarfile.PAX_FORMAT) as tarf:
                # Walk through all files in the repository
                for root, dirs, files in os.walk(self.cwd):
                    root_path = Path(root)
                    if should_skip_path(root_path):
                        dirs[:] = []
                        continue

                    kept_dirs = []
                    for dir_name in dirs:
                        dir_path = root_path / dir_name
                        if should_skip_path(dir_path):
                            continue

                        try:
                            rel_dir = dir_path.relative_to(self.cwd)
                            if should_archive_rel_path(rel_dir, True):
                                self._add_archive_entry(tarf, dir_path, rel_dir)
                        except Exception as e:
                            log_fn(f"Warning: Failed to archive {dir_path}: {e}")
                            continue

                        if not dir_path.is_symlink():
                            kept_dirs.append(dir_name)
                    dirs[:] = kept_dirs

                    for file in files:
                        file_path = root_path / file

                        try:
                            if should_skip_path(file_path):
                                continue
                            rel_path = file_path.relative_to(self.cwd)
                            if not should_archive_rel_path(rel_path, False):
                                continue
                            rel_path_key = rel_path.as_posix()
                            if rel_path_key in office_drm_excluded_paths:
                                continue
                            archive_source = archive_source_overrides.get(
                                rel_path_key,
                                file_path,
                            )

                            # Add file to archive using POSIX paths and LF-normalized text content.
                            total_size += self._add_archive_entry(
                                tarf,
                                archive_source,
                                rel_path,
                            )
                            total_files += 1

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
        finally:
            if office_drm_stage is not None:
                office_drm_stage.cleanup()

    def _remove_git_dir(self, path: Path, context: str, log_fn: Callable) -> None:
        if not self._path_lexists(path):
            return

        deadline = time.time() + max(1, GIT_SYNC_IO_RELEASE_RETRY_SECONDS)
        last_error: Optional[Exception] = None

        while True:
            try:
                self._remove_path_once(path)
                if not self._path_lexists(path):
                    log_fn(f"Removed .git folder ({context})")
                    return
                last_error = OSError(f"Path still exists after delete attempt: {path}")
            except FileNotFoundError:
                log_fn(f"Removed .git folder ({context})")
                return
            except Exception as e:
                last_error = e

            if time.time() >= deadline:
                break
            if last_error is not None:
                log_fn(
                    f"[.git cleanup] Retrying removal after failure ({context}): "
                    f"{type(last_error).__name__}: {last_error}"
                )
            time.sleep(1)

        detail = last_error or "unknown error"
        raise OSError(f"Failed to remove .git folder ({context}): {path} ({detail})")

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
            norm_pat = self._normalize_rel_path(pattern.rstrip("\\/"))
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
        self.using_ttkbootstrap = False
        self.bootstrap_theme = os.environ.get(
            TTKBOOTSTRAP_THEME_ENV,
            TTKBOOTSTRAP_DEFAULT_THEME,
        ).strip() or TTKBOOTSTRAP_DEFAULT_THEME
        if _HAVE_TTKBOOTSTRAP and tb is not None:
            try:
                self.root = tb.Window(themename=self.bootstrap_theme)
                self.using_ttkbootstrap = True
            except Exception:
                self.root = tk.Tk()
        else:
            self.root = tk.Tk()
        self.branch_map = []  # Stores plain branch names
        self.branch_dates = {} # Stores branch -> date string
        self.branch_heads = {} # Stores branch -> remote commit SHA
        self.ui_bg = BG_COLOR
        self.ui_bg_secondary = BG_SECONDARY
        self.ui_border = BORDER_COLOR
        self.ui_text = TEXT_COLOR
        self.ui_text_secondary = TEXT_SECONDARY
        self.ui_text_muted = TEXT_MUTED
        self.ui_accent = ACCENT_COLOR
        self.ui_accent_hover = ACCENT_HOVER
        self.ui_success = SUCCESS_COLOR
        self.ui_warning = WARNING_COLOR

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
        self.auto_refresh_interval = AUTO_REFRESH_INTERVAL_DEFAULT_SECONDS

        # Auto-sync state (triggered by auto-refresh update detection only)
        self.auto_sync_enabled = False
        self.last_synced_branch = None  # Track last synced branch for auto-sync
        self.auto_sync_mirror_default = AUTO_SYNC_MIRROR_DEFAULT
        self.auto_sync_tracking_branch = None
        self.auto_sync_last_synced_commit = ""
        self.auto_sync_pending_commit = None

        # Archive backup settings
        self.archive_dir = DEFAULT_ARCHIVE_DIR
        self.auto_backup_after_sync = False  # Auto backup after sync
        self.skip_office_drm_var = tk.BooleanVar(value=False)
        self.office_drm_mode_var = tk.StringVar(value="cache")
        self.current_version, self.last_updated_at = _resolve_script_build_info(Path(__file__).resolve())

        self._setup_ui()
        self._setup_logging()
        self._start_timestamp_updates()

        # [CHANGE] Initialize with 'main' branch by default
        self._initialize_main_branch()

    def _is_network_error(self, error_msg: str) -> bool:
        """Check whether the error is network-related."""
        return is_network_error(error_msg)

    def _initialize_main_branch(self):
        """Initialize branch list with 'main' branch by default."""
        self.branch_map = ["main"]
        item = self.branch_tree.insert("", "end", values=("main", ""))
        self.branch_tree.selection_set(item)
        logging.info("Initialized with 'main' branch")

    def _setup_ui(self):
        # [CHANGE] Updated Window Title to include Current Directory Name
        current_dir_name = self.manager.cwd.name
        self.root.title(f"[{current_dir_name}] Git Sync Pro - {self.mode}")

        # [CHANGE] Increased Window Size (1100x920) for better layout
        self.root.geometry("1100x920")
        self.root.minsize(1020, 820)
        self.root.configure(bg=self.ui_bg)

        # Apply modern theme
        self._apply_theme()
        self._apply_app_icon()

        # Header
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=20, pady=(15, 10))

        ttk.Label(header, text="Repository Sync", style="Title.TLabel").pack(anchor="w")
        # Show full path in subtitle
        ttk.Label(header, text=f"Target: {self.manager.cwd}", style="Subtitle.TLabel").pack(anchor="w")
        self.build_info_var = tk.StringVar(
            value=f"Version: {self.current_version} | Last Updated: {self.last_updated_at}"
        )
        ttk.Label(header, textvariable=self.build_info_var, style="LabelMuted.TLabel").pack(anchor="w")

        # Timestamp info frame (3 rows with column alignment)
        timestamp_frame = ttk.Frame(self.root)
        timestamp_frame.pack(fill="x", padx=20, pady=(0, 5))

        # Configure grid columns for alignment
        timestamp_frame.columnconfigure(0, weight=0, minsize=250)  # Refresh column
        timestamp_frame.columnconfigure(1, weight=0, minsize=250)  # Sync column
        timestamp_frame.columnconfigure(2, weight=1)               # Avg times column (flexible)

        # Row 0: Last try times (branch / remote check / sync)
        self.last_branch_try_var = tk.StringVar(value="Last Branch Try: -")
        self.last_metadata_try_var = tk.StringVar(value="Last Remote Check Try: -")
        self.last_sync_try_var = tk.StringVar(value="Last Sync Try: -")

        ttk.Label(timestamp_frame, textvariable=self.last_branch_try_var, style="Timestamp.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.last_metadata_try_var, style="Timestamp.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.last_sync_try_var, style="Timestamp.TLabel").grid(row=0, column=2, sticky="w")

        # Row 1: Last done times (branch / remote check / sync)
        self.last_branch_var = tk.StringVar(value="Last Branch Done: -")
        self.last_metadata_var = tk.StringVar(value="Last Remote Check Done: -")
        self.last_sync_var = tk.StringVar(value="Last Sync Done: -")

        ttk.Label(timestamp_frame, textvariable=self.last_branch_var, style="TimestampSuccess.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.last_metadata_var, style="TimestampSuccess.TLabel").grid(row=1, column=1, sticky="w", padx=(0, 10))
        ttk.Label(timestamp_frame, textvariable=self.last_sync_var, style="TimestampSuccess.TLabel").grid(row=1, column=2, sticky="w")

        # Row 2: Average times (branch / remote check / sync)
        self.avg_branch_var = tk.StringVar(value="Avg Branch: -")
        self.avg_metadata_var = tk.StringVar(value="Avg Remote Check: -")
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

        ttk.Label(archive_frame, text="DRM:", style="LabelMuted.TLabel").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(4, 0),
        )
        ttk.Radiobutton(
            archive_frame,
            text="Use cache + re-save misses",
            variable=self.office_drm_mode_var,
            value="cache",
            command=self._on_office_drm_mode_changed,
        ).grid(row=1, column=1, sticky="w", padx=(10, 5), pady=(4, 0))

        ttk.Radiobutton(
            archive_frame,
            text="Exclude targets",
            variable=self.office_drm_mode_var,
            value="exclude",
            command=self._on_office_drm_mode_changed,
        ).grid(row=1, column=2, sticky="w", padx=(10, 5), pady=(4, 0))

        ttk.Button(
            archive_frame,
            text="Show DRM Targets",
            command=self.open_archive_drm_targets_overlay,
        ).grid(row=1, column=3, sticky="w", padx=5, pady=(4, 0))

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

        self.auto_refresh_interval_var = tk.StringVar(value=str(AUTO_REFRESH_INTERVAL_DEFAULT_SECONDS))
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
        self.branch_tree.heading("last_commit", text="Remote Info")
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

        self.status_var = tk.StringVar(value="Select a branch and click Start Sync. Refresh is optional.")
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
            bg=self.ui_bg_secondary,
            fg=self.ui_text,
            insertbackground=self.ui_text,
            selectbackground=self.ui_accent,
            selectforeground="#101214",
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=10
        )
        self.log_widget.pack(fill="both", expand=True)

    def _on_office_drm_mode_changed(self) -> None:
        self.skip_office_drm_var.set(self.office_drm_mode_var.get() == "exclude")

    def _skip_office_drm_for_archive(self) -> bool:
        self._on_office_drm_mode_changed()
        return self.skip_office_drm_var.get()

    def _apply_app_icon(self) -> None:
        """Apply a simple carbon diamond icon without requiring external files."""
        try:
            icons = [self._build_app_icon(32), self._build_app_icon(16)]
            self.root.iconphoto(True, *icons)
            self._app_icon_images = icons
        except Exception:
            self._app_icon_images = []

    def _build_app_icon(self, size: int):
        icon = tk.PhotoImage(width=size, height=size)
        icon.put(BG_COLOR, to=(0, 0, size, size))

        center = (size - 1) / 2
        radius = max(5, int(size * 0.36))
        fill_color = "#2a2f33"
        edge_color = "#c7cdd1"

        for y in range(size):
            dy = abs(y - center)
            if dy > radius:
                continue
            span = int(radius - dy)
            x0 = max(0, int(center - span))
            x1 = min(size - 1, int(center + span))
            icon.put(fill_color, to=(x0, y, x1 + 1, y + 1))
            icon.put(edge_color, to=(x0, y, min(size, x0 + 1), y + 1))
            icon.put(edge_color, to=(x1, y, min(size, x1 + 1), y + 1))

        line_width = max(1, size // 13)
        accent_color = ACCENT_COLOR

        def put_block(x: int, y: int) -> None:
            icon.put(
                accent_color,
                to=(
                    max(0, x),
                    max(0, y),
                    min(size, x + line_width),
                    min(size, y + line_width),
                ),
            )

        for idx in range(max(3, size // 6)):
            put_block(int(size * 0.30) + idx, int(size * 0.53) + idx)
        for idx in range(max(5, size // 4)):
            put_block(int(size * 0.45) + idx, int(size * 0.68) - idx)

        return icon

    def _style_color(self, style, name: str, fallback: str) -> str:
        colors = getattr(style, "colors", None)
        if colors is None:
            return fallback
        try:
            value = getattr(colors, name)
            if value:
                return str(value)
        except Exception:
            pass
        try:
            value = colors.get(name)
            if value:
                return str(value)
        except Exception:
            pass
        return fallback

    def _apply_theme(self):
        """Apply modern, clean theme with improved contrast and spacing."""
        style = tb.Style() if self.using_ttkbootstrap and tb is not None else ttk.Style(self.root)
        if self.using_ttkbootstrap:
            try:
                style.theme_use(self.bootstrap_theme)
            except Exception:
                pass

            self.ui_bg = BG_COLOR
            self.ui_bg_secondary = BG_SECONDARY
            self.ui_border = BORDER_COLOR
            self.ui_text = TEXT_COLOR
            self.ui_text_secondary = TEXT_SECONDARY
            self.ui_text_muted = TEXT_MUTED
            self.ui_accent = ACCENT_COLOR
            self.ui_accent_hover = ACCENT_HOVER
            self.ui_success = SUCCESS_COLOR
            self.ui_warning = WARNING_COLOR
            self.root.configure(bg=self.ui_bg)

            style.configure(
                ".",
                background=self.ui_bg,
                foreground=self.ui_text,
                bordercolor=self.ui_border,
                focuscolor=self.ui_accent,
            )
            style.configure("TFrame", background=self.ui_bg, borderwidth=0)
            style.configure(
                "TLabelframe",
                background=self.ui_bg,
                bordercolor=self.ui_border,
                borderwidth=1,
            )
            style.configure(
                "TLabelframe.Label",
                background=self.ui_bg,
                foreground=self.ui_text,
                font=(UI_FONT_FAMILY_TEXT, 10, "bold"),
            )
            style.configure(
                "Title.TLabel",
                font=(UI_FONT_FAMILY_DISPLAY, 18, "bold"),
                background=self.ui_bg,
                foreground=self.ui_text,
                padding=(0, 10, 0, 5),
            )
            style.configure(
                "Subtitle.TLabel",
                font=(UI_FONT_FAMILY_TEXT, 10),
                foreground=self.ui_text_secondary,
                background=self.ui_bg,
                padding=(0, 0, 0, 10),
            )
            style.configure(
                "LabelBold.TLabel",
                font=(UI_FONT_FAMILY_TEXT, 10, "bold"),
                background=self.ui_bg,
                foreground=self.ui_text,
            )
            style.configure(
                "LabelMuted.TLabel",
                font=(UI_FONT_FAMILY_TEXT, 9),
                foreground=self.ui_text_muted,
                background=self.ui_bg,
            )
            style.configure(
                "Timestamp.TLabel",
                font=(UI_FONT_FAMILY_TEXT, 9, "italic"),
                foreground=self.ui_accent,
                background=self.ui_bg,
            )
            style.configure(
                "TimestampSuccess.TLabel",
                font=(UI_FONT_FAMILY_TEXT, 9, "italic"),
                foreground=self.ui_success,
                background=self.ui_bg,
            )
            style.configure(
                "TimestampPerf.TLabel",
                font=(UI_FONT_FAMILY_TEXT, 9, "italic"),
                foreground=self.ui_warning,
                background=self.ui_bg,
            )
            style.configure(
                "Accent.TButton",
                background=self.ui_accent,
                foreground="#101214",
                font=(UI_FONT_FAMILY_TEXT, 10, "bold"),
                borderwidth=0,
                focuscolor=self.ui_accent,
                padding=(20, 10),
            )
            style.map(
                "Accent.TButton",
                background=[("active", self.ui_accent_hover), ("pressed", self.ui_accent_hover)],
                foreground=[("active", "#101214"), ("pressed", "#101214")],
            )
            style.configure(
                "TButton",
                background=self.ui_bg_secondary,
                foreground=self.ui_text,
                borderwidth=1,
                bordercolor=self.ui_border,
                focuscolor=self.ui_accent,
                padding=(12, 8),
            )
            style.map(
                "TButton",
                background=[("active", self.ui_border), ("pressed", self.ui_border)],
                foreground=[("active", self.ui_text), ("pressed", self.ui_text)],
            )
            style.configure(
                "TEntry",
                fieldbackground=self.ui_bg_secondary,
                foreground=self.ui_text,
                bordercolor=self.ui_border,
                insertcolor=self.ui_text,
                padding=8,
            )
            style.map("TEntry", bordercolor=[("focus", self.ui_accent)])
            style.configure(
                "TCombobox",
                fieldbackground=self.ui_bg_secondary,
                background=self.ui_bg_secondary,
                foreground=self.ui_text,
                bordercolor=self.ui_border,
                arrowcolor=self.ui_text,
                padding=8,
            )
            style.map(
                "TCombobox",
                fieldbackground=[("readonly", self.ui_bg_secondary)],
                bordercolor=[("focus", self.ui_accent)],
            )
            style.configure(
                "TCheckbutton",
                background=self.ui_bg,
                foreground=self.ui_text,
                font=(UI_FONT_FAMILY_TEXT, 9),
                focuscolor=self.ui_accent,
            )
            style.configure(
                "TRadiobutton",
                background=self.ui_bg,
                foreground=self.ui_text,
                font=(UI_FONT_FAMILY_TEXT, 9),
                focuscolor=self.ui_accent,
            )
            style.configure(
                "Treeview",
                background=self.ui_bg_secondary,
                foreground=self.ui_text,
                fieldbackground=self.ui_bg_secondary,
                borderwidth=1,
                bordercolor=self.ui_border,
                font=(UI_FONT_FAMILY_TEXT, 9),
                rowheight=26,
            )
            style.configure(
                "Treeview.Heading",
                background=self.ui_bg,
                foreground=self.ui_text,
                borderwidth=1,
                bordercolor=self.ui_border,
                font=(UI_FONT_FAMILY_TEXT, 10, "bold"),
                padding=10,
            )
            style.map(
                "Treeview",
                background=[("selected", self.ui_accent)],
                foreground=[("selected", "#101214")],
            )
            style.map("Treeview.Heading", background=[("active", self.ui_border)])
            style.configure(
                "TSpinbox",
                fieldbackground=self.ui_bg_secondary,
                foreground=self.ui_text,
                bordercolor=self.ui_border,
                arrowcolor=self.ui_text,
                padding=8,
            )
            style.configure(
                "TProgressbar",
                background=self.ui_accent,
                troughcolor=self.ui_bg_secondary,
                bordercolor=self.ui_border,
                lightcolor=self.ui_accent,
                darkcolor=self.ui_accent,
            )
            return

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
                       foreground="#101214",
                       font=(UI_FONT_FAMILY_TEXT, 10, "bold"),
                       borderwidth=0,
                       focuscolor="none",
                       padding=(20, 10))

        style.map("Accent.TButton",
                 background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)],
                 foreground=[("active", "#101214"), ("pressed", "#101214")])

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
                 foreground=[("selected", "#101214")])

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
        self.last_metadata_try_var.set(self._format_time_with_age("Last Remote Check Try", self.last_metadata_try_time))
        self.last_sync_try_var.set(self._format_time_with_age("Last Sync Try", self.last_sync_try_time))
        self.last_branch_var.set(self._format_time_with_age("Last Branch Done", self.last_branch_time))
        self.last_metadata_var.set(self._format_time_with_age("Last Remote Check Done", self.last_metadata_time))
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

    def _archive_target_dir_from_ui(self) -> Path:
        raw_dir = self.archive_dir_var.get().strip()
        return Path(raw_dir) if raw_dir else Path(DEFAULT_ARCHIVE_DIR)

    def open_archive_drm_targets_overlay(self):
        """Open an overlay listing Office files that need DRM handling for archive."""
        target_dir = self._archive_target_dir_from_ui()

        overlay = tk.Toplevel(self.root)
        overlay.title("Office DRM Targets")
        overlay.geometry("820x520")
        overlay.configure(bg=self.ui_bg)
        overlay.transient(self.root)

        container = ttk.Frame(overlay, padding=12)
        container.pack(fill="both", expand=True)
        container.rowconfigure(2, weight=1)
        container.columnconfigure(0, weight=1)

        ttk.Label(
            container,
            text="Office DRM Targets",
            style="LabelBold.TLabel",
        ).grid(row=0, column=0, sticky="w")

        summary_var = tk.StringVar(value="Scanning archive scope...")
        ttk.Label(
            container,
            textvariable=summary_var,
            style="LabelMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 8))

        text_widget = scrolledtext.ScrolledText(
            container,
            height=20,
            state="disabled",
            font=(UI_FONT_FAMILY_MONO, 9),
            bg=self.ui_bg_secondary,
            fg=self.ui_text,
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=10,
        )
        text_widget.grid(row=2, column=0, sticky="nsew")

        button_frame = ttk.Frame(container)
        button_frame.grid(row=3, column=0, sticky="e", pady=(10, 0))
        ttk.Button(button_frame, text="Close", command=overlay.destroy).pack(side="right")

        def populate(paths: Optional[List[Path]], error_message: Optional[str]) -> None:
            if not overlay.winfo_exists():
                return
            text_widget.configure(state="normal")
            text_widget.delete("1.0", "end")
            if error_message:
                summary_var.set("Scan failed.")
                text_widget.insert("end", error_message)
            elif paths:
                summary_var.set(
                    f"{len(paths)} target file(s) in archive scope. Target directory: {target_dir}"
                )
                text_widget.insert(
                    "end",
                    "\n".join(path.as_posix() for path in paths),
                )
            else:
                summary_var.set(f"No Office DRM target files found. Target directory: {target_dir}")
                text_widget.insert("end", "No target files.")
            text_widget.configure(state="disabled")

        def task() -> None:
            try:
                paths = self.manager.get_archive_office_drm_targets(target_dir)
                error_message = None
            except Exception as e:
                paths = None
                error_message = str(e)
            self.root.after(0, lambda: populate(paths, error_message))

        threading.Thread(target=task, daemon=True).start()

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
        """Reset the branch list when the repository changes without auto-loading."""
        # Clear branch list
        for item in self.branch_tree.get_children():
            self.branch_tree.delete(item)
        self.branch_map = []
        self.branch_dates = {}
        self.branch_heads = {}

        # [CHANGE] Re-initialize with main branch
        self._initialize_main_branch()

        # Update status message
        self.status_var.set("Repository changed. Select main or click Refresh to load branches.")

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

    def refresh_branches(self, auto_refresh=False, metadata_only=False, trigger_auto_sync=True):
        """
        Fetch branch list or selected-branch HEAD from the remote repository.

        Args:
            auto_refresh: If True, this is an automatic refresh (no user interaction)
            metadata_only: If True, skip branch list fetch and check only the selected branch HEAD
            trigger_auto_sync: If True, auto-refresh completion may trigger auto-sync detection
        """
        # Prevent concurrent refresh operations
        if self.is_refreshing:
            if not auto_refresh:
                logging.warning("[Refresh] Already in progress, skipping")
            return

        if metadata_only:
            self.last_metadata_try_time = datetime.now(KST)
        else:
            self.last_branch_try_time = datetime.now(KST)

        # Update state
        self.is_refreshing = True
        self.cancel_refresh = False  # Reset cancel flag
        self._update_controls()

        if metadata_only:
            if auto_refresh:
                self.status_var.set("Auto-refreshing selected branch HEAD...")
            else:
                self.status_var.set("Checking selected branch HEAD...")
        else:
            # [CHANGE] Do NOT clear branch list - preserve existing branches
            if auto_refresh:
                self.status_var.set("Auto-refreshing branch list...")
            else:
                self.status_var.set("Fetching branch list...")

        repo = self.repo_var.get()
        if metadata_only:
            if auto_refresh:
                logging.info(f"[Auto-Refresh] Starting selected branch HEAD check from: {repo}")
            else:
                logging.info(f"[Refresh] Starting selected branch HEAD check from: {repo}")
        else:
            if auto_refresh:
                logging.info(f"[Auto-Refresh] Starting branch fetch from: {repo}")
            else:
                logging.info(f"[Refresh] Starting branch fetch from: {repo}")

        def task():
            try:
                if metadata_only:
                    selected_branch = self._get_selected_branch()
                    if not selected_branch:
                        self.root.after(0, lambda: self._on_refresh_error("Fetch Error", "No branch selected.", auto_refresh))
                        return

                    if self.cancel_refresh:
                        self.root.after(0, lambda: self._on_refresh_cancelled(auto_refresh))
                        return

                    head_start = time.time()
                    head = self.manager.get_remote_branch_head(repo, selected_branch)
                    head_duration = time.time() - head_start

                    if self.cancel_refresh:
                        self.root.after(0, lambda: self._on_refresh_cancelled(auto_refresh))
                        return

                    self.root.after(
                        0,
                        lambda: self._on_branch_head_checked(
                            selected_branch,
                            head,
                            auto_refresh,
                            head_duration,
                            trigger_auto_sync=trigger_auto_sync,
                        ),
                    )
                    return

                if self.cancel_refresh:
                    self.root.after(0, lambda: self._on_refresh_cancelled(auto_refresh))
                    return

                branch_start = time.time()
                branch_heads = self.manager.get_remote_branch_heads_fast(repo)
                branches = sorted(branch_heads)
                branch_duration = time.time() - branch_start

                if self.cancel_refresh:
                    self.root.after(0, lambda: self._on_refresh_cancelled(auto_refresh))
                    return

                self.root.after(
                    0,
                    lambda: self._on_branches_loaded(
                        branches,
                        auto_refresh,
                        branch_duration,
                        branch_heads=branch_heads,
                    ),
                )

            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._on_refresh_error("Fetch Error", error_msg, auto_refresh))

        threading.Thread(target=task, daemon=True).start()

    def _branch_remote_info_text(self, branch: str) -> str:
        committed_at = self.branch_dates.get(branch, "")
        if committed_at:
            head = self.branch_heads.get(branch, "")
            if head:
                return f"{committed_at} ({_short_sha(head)})"
            return committed_at

        head = self.branch_heads.get(branch, "")
        if head:
            return f"HEAD {_short_sha(head)}"
        return ""

    def _update_branch_remote_info(
        self,
        branch: str,
        snapshot: Optional[RemoteBranchSnapshot] = None,
        head: str = "",
    ) -> None:
        if snapshot is not None:
            if snapshot.commit_sha:
                self.branch_heads[branch] = snapshot.commit_sha
            if snapshot.committed_at and snapshot.committed_at != "-":
                self.branch_dates[branch] = snapshot.committed_at
        elif head:
            previous_head = self.branch_heads.get(branch)
            self.branch_heads[branch] = head
            if previous_head != head:
                self.branch_dates.pop(branch, None)

        for item in self.branch_tree.get_children():
            values = self.branch_tree.item(item).get("values", [])
            if values and str(values[0]) == branch:
                self.branch_tree.item(item, values=(branch, self._branch_remote_info_text(branch)))
                return

    def _on_branches_loaded(
        self,
        branches: List[str],
        auto_refresh=False,
        duration=None,
        branch_heads: Optional[Dict[str, str]] = None,
    ):
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
        if branch_heads:
            for branch, head in branch_heads.items():
                if self.branch_heads.get(branch) != head:
                    self.branch_dates.pop(branch, None)
                self.branch_heads[branch] = head

        # Clear tree (but keep dates in self.branch_dates for reuse)
        for item in self.branch_tree.get_children():
            self.branch_tree.delete(item)

        # Insert branches with existing dates if available
        for b in branches:
            self.branch_tree.insert("", "end", values=(b, self._branch_remote_info_text(b)))

        # Restore selection if possible
        if selected_branch and selected_branch in branches:
            index = branches.index(selected_branch)
            items = self.branch_tree.get_children()
            if index < len(items):
                self.branch_tree.selection_set(items[index])
                self.branch_tree.see(items[index])
        elif branches:
            items = self.branch_tree.get_children()
            self.branch_tree.selection_set(items[0])
            self.branch_tree.see(items[0])

        if auto_refresh:
            self.status_var.set("Auto-refresh: Branch list updated.")
            logging.info("[Auto-Refresh] Branch list updated without all-head metadata fetch.")
        else:
            self.status_var.set("Branch list loaded. Start Sync uses the selected branch directly.")
            logging.info("[Refresh] Branch list loaded without all-head metadata fetch.")

        self.is_refreshing = False

        # Update controls (Sync button becomes available if branches loaded)
        self._update_controls()

    def _on_branch_head_checked(
        self,
        branch: str,
        head: str,
        auto_refresh=False,
        duration=None,
        trigger_auto_sync=True,
    ):
        """Handle selected-branch HEAD check completion."""
        if duration is not None:
            self.metadata_fetch_times.append(duration)
            if len(self.metadata_fetch_times) > self.max_samples:
                self.metadata_fetch_times.pop(0)
            self._update_avg_times()

        self._update_branch_remote_info(branch, head=head)
        self.last_metadata_time = datetime.now(KST)
        self.is_refreshing = False
        self._update_controls()

        if auto_refresh:
            self.status_var.set("Auto-refresh completed.")
            logging.info(f"[Auto-Refresh] Selected branch HEAD: {branch} {_short_sha(head)}")
            if trigger_auto_sync:
                self._detect_and_trigger_auto_sync()
        else:
            self.status_var.set("Selected branch HEAD checked.")
            logging.info(f"[Refresh] Selected branch HEAD: {branch} {_short_sha(head)}")

    def _on_dates_loaded(
        self,
        dates: Dict[str, str],
        auto_refresh=False,
        duration=None,
        trigger_auto_sync=True,
    ):
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
            if trigger_auto_sync:
                self.status_var.set("Auto-refresh completed.")
                logging.info("[Auto-Refresh] Completed successfully")
            else:
                self.status_var.set("Metadata refresh completed.")
                logging.info("[Refresh] Metadata-only refresh completed.")
            if trigger_auto_sync:
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
        self.avg_metadata_var.set(f"Avg Remote Check: {metadata_str}")
        self.avg_sync_var.set(f"Avg Sync: {sync_str}")

    def _refresh_branch_dates_only(self, auto_refresh=False, trigger_auto_sync=False):
        """Check the selected branch HEAD without reloading all branch metadata."""
        if not self.branch_map:
            logging.info("[Refresh] Branch list is empty, skipping selected branch HEAD check.")
            return
        self.refresh_branches(
            auto_refresh=auto_refresh,
            metadata_only=True,
            trigger_auto_sync=trigger_auto_sync,
        )

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

        latest_commit = self.branch_heads.get(selected_branch, "")
        if not latest_commit:
            return

        if selected_branch != self.auto_sync_tracking_branch:
            self.auto_sync_tracking_branch = selected_branch
            self.auto_sync_last_synced_commit = latest_commit
            self.auto_sync_pending_commit = None
            logging.info(
                f"[Auto-Sync] Tracking selected branch '{selected_branch}' "
                f"(baseline commit: {_short_sha(latest_commit)})"
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
                f"({_short_sha(self.auto_sync_last_synced_commit)} -> {_short_sha(latest_commit)}), "
                "but sync is already in progress. Will retry on next auto-refresh."
            )
            return

        logging.info(
            f"[Auto-Sync] Update detected on '{selected_branch}' "
            f"({_short_sha(self.auto_sync_last_synced_commit)} -> {_short_sha(latest_commit)}). Starting sync."
        )
        self._execute_auto_sync(selected_branch, latest_commit)

    def start_sync(self):
        # Check if branches are loaded
        if not self.branch_map:
            messagebox.showwarning(
                "Branches Not Loaded",
                "The branch list has not been loaded.\n\n"
                "Select a repository, use the default main branch, or click Refresh to load branches."
            )
            return

        # Get selected branch from Treeview
        selected = self.branch_tree.selection()
        if not selected:
            messagebox.showwarning("No Branch Selected", "Select a branch to sync first.")
            return

        # Extract branch name from selected item
        branch = self.branch_tree.item(selected[0])["values"][0]
        repo = self.repo_var.get()
        mirror = self.mirror_var.get()
        method = self.download_method_var.get()

        # [CHANGE] Record last synced branch for auto-sync
        self.last_synced_branch = branch

        # ZIP mode still replaces local git metadata and files, so keep explicit confirmation.
        if method == "zip" and self.manager._path_lexists(self.manager.cwd / ".git"):
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

        method_text = "ZIP Download" if method == "zip" else "Git Incremental"
        self.status_var.set(f"Syncing {branch}... ({method_text})")

        logging.info(f"[Sync] Starting sync - Repo: {repo}, Branch: {branch}, Method: {method}, Mirror: {mirror}")

        def task():
            error_message = None
            snapshot = RemoteBranchSnapshot(commit_sha="", committed_at="-")
            try:
                snapshot = self.manager.sync(repo, branch, mirror, logging.info, method=method)
            except Exception as e:
                logging.exception(
                    "[Sync] Failed - Repo: %s, Branch: %s, Method: %s, Mirror: %s",
                    repo,
                    branch,
                    method,
                    mirror,
                )
                error_message = f"{type(e).__name__}: {e}"
            finally:
                # Calculate duration
                sync_duration = time.time() - self.sync_start_time
                # error_message is defined outside the except block for safe capture.
                self.root.after(
                    0,
                    lambda msg=error_message, dur=sync_duration, snap=snapshot, b=branch:
                        self._on_sync_complete(msg, dur, snap, b),
                )

        threading.Thread(target=task, daemon=True).start()

    def _on_sync_complete(
        self,
        error_message: Optional[str],
        duration: float = None,
        snapshot: Optional[RemoteBranchSnapshot] = None,
        branch: Optional[str] = None,
    ):
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
            self._on_sync_success(branch, snapshot)

    def _on_sync_success(
        self,
        branch: Optional[str] = None,
        snapshot: Optional[RemoteBranchSnapshot] = None,
    ):
        self.last_sync_time = datetime.now(KST)
        if branch and snapshot is not None:
            self._update_branch_remote_info(branch, snapshot=snapshot)
            if snapshot.commit_sha:
                self.auto_sync_last_synced_commit = snapshot.commit_sha

        self.status_var.set("Sync completed successfully.")

        # Auto-backup after sync if enabled
        if self.auto_backup_var.get():
            logging.info("[Auto-Backup] Starting automatic backup after sync...")
            self._perform_auto_backup()
        else:
            logging.info("[Sync] Skipped post-sync remote metadata refresh; using fetched branch ref.")
            messagebox.showinfo("Success", "Repository sync finished!")
            if self.mode == "Normal":
                self.root.destroy()

    def _on_error(self, title, message):
        # Note: State is managed by caller (_on_sync_complete or _on_refresh_error)

        # Check for credential errors.
        if is_credential_error(message):
            self.status_var.set("Authentication failed: credentials required")
            logging.warning(f"Credential Error Detected: {message}")

            user_message = (
                "Git authentication is required.\n\n"
                "Private repositories require authentication.\n\n"
                "Resolution:\n\n"
                "1. Use an SSH URL (recommended):\n"
                "   - Create an SSH key: ssh-keygen -t ed25519 -C \"your_email@example.com\"\n"
                "   - Register the public key in GitHub: Settings -> SSH and GPG keys\n"
                "   - Change the repository URL to git@github.com:user/repo.git\n\n"
                "2. Use a Personal Access Token (PAT):\n"
                "   - GitHub -> Settings -> Developer settings -> Personal access tokens\n"
                "   - After creating the token, run this command:\n"
                "     git config --global credential.helper store\n"
                "   - Enter the token as the username when Git prompts for credentials.\n\n"
                "3. Use ZIP Download for public repositories only:\n"
                "   - Change Download Method to 'ZIP Download'.\n\n"
                f"Details:\n{message}"
            )
            messagebox.showerror("Git Authentication Required", user_message)

        # Check for network errors.
        elif self._is_network_error(message):
            self.status_var.set("Waiting: network issue detected")
            logging.warning(f"Network Error Detected: {message}")

            user_message = (
                "The corporate proxy server or network appears to have an issue.\n\n"
                "A 502/503 error or connection timeout occurred.\n"
                "Try again later.\n\n"
                f"Details:\n{message}"
            )
            messagebox.showwarning("Network Connection Issue", user_message)
        else:
            # Handle general errors.
            self.status_var.set(f"Error: {title}")
            logging.error(f"{title}: {message}")
            messagebox.showerror(title, message)

    def create_archive_backup(self):
        """Create a compressed archive backup of the current local repository."""
        from tkinter import filedialog

        # Ask user to select target directory
        target_dir = filedialog.askdirectory(
            title="Select Archive Backup Directory",
            initialdir=self.archive_dir_var.get() or DEFAULT_ARCHIVE_DIR
        )

        if not target_dir:
            logging.info("Archive backup cancelled by user")
            return

        # Confirm before proceeding
        skip_office_drm = self._skip_office_drm_for_archive()
        drm_mode = "exclude target files" if skip_office_drm else "use cache; re-save cache misses"
        confirm = messagebox.askyesno(
            "Confirm Archive Backup",
            f"Create archive backup of current repository?\n\n"
            f"Target directory: {target_dir}\n\n"
            f"Office DRM handling: {drm_mode}\n\n"
            f"This will create a compressed archive file containing eligible repository files."
        )

        if not confirm:
            return

        self.status_var.set("Creating archive backup...")
        logging.info(f"[Archive] Starting archive backup to: {target_dir}")
        logging.info(
            "[Archive] Office DRM handling: %s",
            "exclude targets" if skip_office_drm else "use cache; re-save misses",
        )

        # Disable buttons during archive creation
        self.btn_archive.configure(state="disabled")
        self.btn_sync.configure(state="disabled")

        def task():
            error_message = None
            archive_path = None
            try:
                archive_path = self.manager.create_archive_backup(
                    Path(target_dir),
                    logging.info,
                    skip_office_drm=skip_office_drm,
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
            logging.info("[Sync] Skipped post-sync remote metadata refresh; using fetched branch ref.")
            messagebox.showinfo("Success", "Repository sync finished!")
            if self.mode == "Normal":
                self.root.destroy()
            return

        self.status_var.set("Creating automatic backup...")
        logging.info(f"[Auto-Backup] Creating backup to: {target_dir}")
        skip_office_drm = self._skip_office_drm_for_archive()
        logging.info(
            "[Auto-Backup] Office DRM handling: %s",
            "exclude targets" if skip_office_drm else "use cache; re-save misses",
        )

        def task():
            error_message = None
            archive_path = None
            try:
                archive_path = self.manager.create_archive_backup(
                    Path(target_dir),
                    logging.info,
                    skip_office_drm=skip_office_drm,
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

        logging.info("[Sync] Skipped post-sync remote metadata refresh after backup.")

        if self.mode == "Normal":
            self.root.destroy()

    def _perform_auto_backup_silent(self):
        """Perform automatic backup after auto-sync (silent, no popup)."""
        target_dir = self.archive_dir_var.get()

        if not target_dir:
            logging.warning("[Auto-Sync Backup] No archive directory set, skipping auto-backup")
            logging.info("[Auto-Sync] Skipped post-sync remote metadata refresh; using fetched branch ref.")
            return

        self.status_var.set("Creating automatic backup after auto-sync...")
        logging.info(f"[Auto-Sync Backup] Creating backup to: {target_dir}")
        skip_office_drm = self._skip_office_drm_for_archive()
        logging.info(
            "[Auto-Sync Backup] Office DRM handling: %s",
            "exclude targets" if skip_office_drm else "use cache; re-save misses",
        )

        def task():
            error_message = None
            archive_path = None
            try:
                archive_path = self.manager.create_archive_backup(
                    Path(target_dir),
                    logging.info,
                    skip_office_drm=skip_office_drm,
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

        logging.info("[Auto-Sync] Skipped post-backup remote metadata refresh.")

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

            baseline_commit = self.branch_heads.get(selected_branch, "")
            self.auto_sync_tracking_branch = selected_branch
            self.auto_sync_last_synced_commit = baseline_commit
            self.auto_sync_pending_commit = None
            logging.info(
                f"[Auto-Sync] Enabled. Tracking branch: {selected_branch}, "
                f"baseline commit: {_short_sha(baseline_commit) if baseline_commit else '(unknown)'}, "
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
            self.refresh_branches(auto_refresh=True, metadata_only=True, trigger_auto_sync=True)

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

        method_text = "ZIP Download" if method == "zip" else "Git Incremental"
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
            snapshot = RemoteBranchSnapshot(commit_sha="", committed_at="-")
            try:
                snapshot = self.manager.sync(repo, branch, mirror, logging.info, method=method)
            except Exception as e:
                logging.exception(
                    "[Auto-Sync] Failed - Repo: %s, Branch: %s, Method: %s, Mirror: %s, Target: %s",
                    repo,
                    branch,
                    method,
                    mirror,
                    target_commit,
                )
                error_message = f"{type(e).__name__}: {e}"
            finally:
                sync_duration = time.time() - auto_sync_start_time
                self.root.after(
                    0,
                    lambda msg=error_message, dur=sync_duration, b=branch, c=target_commit, snap=snapshot:
                        self._on_auto_sync_complete(msg, dur, b, c, snap),
                )

        threading.Thread(target=task, daemon=True).start()

    def _on_auto_sync_complete(
        self,
        error_message: Optional[str],
        duration: float = None,
        branch: Optional[str] = None,
        target_commit: Optional[str] = None,
        snapshot: Optional[RemoteBranchSnapshot] = None,
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
            if branch and snapshot is not None:
                self._update_branch_remote_info(branch, snapshot=snapshot)
            if (
                branch
                and branch == self.auto_sync_tracking_branch
            ):
                if snapshot is not None and snapshot.commit_sha:
                    self.auto_sync_last_synced_commit = snapshot.commit_sha
                elif target_commit:
                    self.auto_sync_last_synced_commit = target_commit
            self.auto_sync_pending_commit = None

            self.status_var.set("Auto-sync completed successfully.")
            logging.info("[Auto-Sync] Completed successfully")

            # Auto-backup after auto-sync if enabled
            if self.auto_backup_var.get():
                logging.info("[Auto-Sync] Auto-backup enabled, starting backup...")
                self._perform_auto_backup_silent()
            else:
                logging.info("[Auto-Sync] Skipped post-sync remote metadata refresh; using fetched branch ref.")

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
        self.branch_heads = {}

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
            elif branch in self.branch_heads:
                branch_display += f"  (HEAD {_short_sha(self.branch_heads[branch])})"

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
            branch_heads = self.manager.get_remote_branch_heads_fast(self.repo_url)
            branches = sorted(branch_heads)
            self.branches = branches
            self.branch_heads.update(branch_heads)
            self.last_branch_time = datetime.now(KST)

            # Success
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

            snapshot = self.manager.sync(self.repo_url, branch, True, print, method=self.download_method)
            if snapshot.commit_sha:
                self.branch_heads[branch] = snapshot.commit_sha
            if snapshot.committed_at and snapshot.committed_at != "-":
                self.branch_dates[branch] = snapshot.committed_at

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

def _short_sha(commit_sha: str) -> str:
    return commit_sha[:12] if commit_sha else "-"


CLI_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
CLI_RESET = "\033[0m"
CLI_BOLD = "\033[1m"
CLI_DIM = "\033[2m"
CLI_GREEN = "\033[32m"
CLI_YELLOW = "\033[33m"
CLI_MAGENTA = "\033[35m"
CLI_CYAN = "\033[36m"


def _cli_time() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def _strip_cli_style(text: str) -> str:
    return CLI_ANSI_RE.sub("", text)


def _cli_color_enabled() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _cli_style(text: str, *codes: str) -> str:
    if not codes or not _cli_color_enabled():
        return text
    return "".join(codes) + text + CLI_RESET


def _log_cli_file_only(message: str) -> None:
    logger = logging.getLogger()
    clean_message = _strip_cli_style(message)
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __file__,
        0,
        clean_message,
        None,
        None,
    )
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.handle(record)


def _make_cli_log_callback() -> Callable[[str], None]:
    def _log(message: str) -> None:
        print(f"[{_cli_time()}] {message}")
        _log_cli_file_only(message)

    return _log


def _print_cli_event(label: str, message: str, color: str) -> None:
    label_text = _cli_style(f"[{label}]", CLI_BOLD, color)
    print(f"[{_cli_time()}] {label_text} {message}")
    _log_cli_file_only(f"[{label}] {message}")


def _format_commit_timestamp(committed_at: str) -> str:
    value = committed_at if committed_at else "-"
    return _cli_style(value, CLI_BOLD, CLI_MAGENTA)


def _snapshot_with_fallback(
    manager: GitManager,
    repo: str,
    branch: str,
    fallback_sha: str,
    log_callback: Callable[[str], None],
) -> RemoteBranchSnapshot:
    try:
        return manager.get_remote_branch_snapshot(repo, branch)
    except Exception as e:
        log_callback(f"Warning: could not fetch commit timestamp for {branch}: {e}")
        return RemoteBranchSnapshot(commit_sha=fallback_sha, committed_at="-")


def _print_cli_update_commit(
    label: str,
    branch: str,
    snapshot: RemoteBranchSnapshot,
    color: str,
    previous_sha: str = "",
) -> None:
    if previous_sha:
        sha_text = f"{_short_sha(previous_sha)} -> {_short_sha(snapshot.commit_sha)}"
    else:
        sha_text = _short_sha(snapshot.commit_sha)

    _print_cli_event(
        label,
        f"{branch} {sha_text} | committed at {_format_commit_timestamp(snapshot.committed_at)}",
        color,
    )


def _print_cli_sync_done(branch: str, snapshot: RemoteBranchSnapshot, duration_seconds: float) -> None:
    duration_text = f"{duration_seconds:.1f}s"
    _print_cli_event(
        "SYNC DONE",
        (
            f"{branch} synced in {duration_text} | remote {_short_sha(snapshot.commit_sha)} "
            f"| committed at {_format_commit_timestamp(snapshot.committed_at)} "
            f"| completed at {_cli_style(_cli_time(), CLI_BOLD, CLI_GREEN)}"
        ),
        CLI_GREEN,
    )


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("must be a number") from e
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def _resolve_repo_argument(repo_arg: Optional[str]) -> Optional[str]:
    if repo_arg is None:
        return None

    value = repo_arg.strip()
    if not value:
        return None

    if value.isdigit():
        idx = int(value) - 1
        if 0 <= idx < len(REPO_CHOICES):
            return REPO_CHOICES[idx]

    return value


def _select_cli_menu(title: str, choices: List[str], default_index: int = 0) -> Optional[str]:
    if not choices:
        return None

    default_index = min(max(default_index, 0), len(choices) - 1)
    while True:
        print(f"\n{title}")
        for idx, value in enumerate(choices, 1):
            marker = "*" if idx - 1 == default_index else " "
            print(f"[{idx}] {marker} {value}")
        raw = input(f"Choice (1-{len(choices)}, Enter={default_index + 1}, q=quit): ").strip()
        if not raw:
            return choices[default_index]
        if raw.lower() in {"q", "quit", "exit"}:
            return None
        try:
            selected_idx = int(raw) - 1
        except ValueError:
            print("Invalid selection.")
            continue
        if 0 <= selected_idx < len(choices):
            return choices[selected_idx]
        print("Invalid selection.")


def _should_prompt_cli_settings(args: argparse.Namespace) -> bool:
    return sys.stdin.isatty() and not (args.repo and args.branch)


def _select_cli_update_mode(
    auto_arg: Optional[bool],
    manual_arg: Optional[bool],
    watch_arg: Optional[bool],
    loop_arg: Optional[bool],
    prompt_enabled: bool,
) -> Optional[str]:
    requested_modes = set()
    if auto_arg or watch_arg or loop_arg:
        requested_modes.add("auto")
    if manual_arg:
        requested_modes.add("manual")

    if len(requested_modes) > 1:
        raise RuntimeError("Choose only one CLI update mode: auto/watch/loop or manual.")
    if requested_modes:
        return next(iter(requested_modes))
    if not prompt_enabled:
        return "once"

    auto_label = "Auto update mode - watch remote branch and sync on update"
    manual_label = "Manual update mode - sync selected branch when update is entered"
    selected = _select_cli_menu(
        "Select Sync Mode:",
        ["Run once", auto_label, manual_label],
        default_index=0,
    )
    if selected is None:
        return None
    if selected == auto_label:
        return "auto"
    if selected == manual_label:
        return "manual"
    return "once"


def _select_cli_method(method_arg: Optional[str], prompt_enabled: bool) -> Optional[str]:
    if method_arg:
        return method_arg
    if not prompt_enabled:
        return "git"

    return _select_cli_menu("Select Sync Method:", ["git", "zip"], default_index=0)


def _select_cli_mirror(no_mirror_arg: Optional[bool], prompt_enabled: bool) -> Optional[bool]:
    if no_mirror_arg:
        return False
    if not prompt_enabled:
        return True

    mirror_on = "Mirror on - delete local files absent from selected branch"
    mirror_off = "Mirror off - keep extra local files"
    selected = _select_cli_menu(
        "Select Mirror Mode:",
        [mirror_on, mirror_off],
        default_index=0,
    )
    if selected is None:
        return None
    return selected == mirror_on


def _input_cli_positive_float(prompt: str, default_value: float) -> Optional[float]:
    while True:
        raw = input(f"{prompt} (Enter={default_value:g}, q=quit): ").strip()
        if not raw:
            return default_value
        if raw.lower() in {"q", "quit", "exit"}:
            return None
        try:
            return _positive_float(raw)
        except argparse.ArgumentTypeError as e:
            print(f"Invalid value: {e}")


def _select_cli_auto_interval(
    interval_arg: Optional[float],
    update_mode: str,
    prompt_enabled: bool,
) -> Optional[float]:
    if update_mode != "auto":
        return CLI_AUTO_UPDATE_INTERVAL_DEFAULT_SECONDS
    if interval_arg is not None:
        return interval_arg
    if not prompt_enabled:
        return CLI_AUTO_UPDATE_INTERVAL_DEFAULT_SECONDS

    return _input_cli_positive_float(
        "Auto update interval in seconds",
        CLI_AUTO_UPDATE_INTERVAL_DEFAULT_SECONDS,
    )


def _select_cli_repository(repo_arg: Optional[str]) -> Optional[str]:
    repo = _resolve_repo_argument(repo_arg)
    if repo:
        return repo

    if not sys.stdin.isatty():
        return REPO_CHOICES[0]

    return _select_cli_menu("Select Repository:", REPO_CHOICES, default_index=0)


def _select_cli_branch(
    manager: GitManager,
    repo: str,
    branch_arg: Optional[str],
) -> Optional[str]:
    if branch_arg:
        return branch_arg

    if not sys.stdin.isatty():
        raise RuntimeError("--branch is required when --cli runs without an interactive terminal.")

    print(f"\n[{_cli_time()}] Fetching remote branches for CLI selection...")
    branches = manager.get_remote_branches_fast(repo)
    default_index = branches.index("main") if "main" in branches else 0
    return _select_cli_menu("Select Branch:", branches, default_index=default_index)


def _print_cli_error(error_msg: str) -> None:
    if is_credential_error(error_msg):
        logging.warning("Credential Error: %s", error_msg)
        print("\n" + "=" * 60)
        print("Git authentication required")
        print("=" * 60)
        print("Private repositories require authentication.")
        print("\nResolution options:")
        print("1. Use an SSH URL and registered SSH key.")
        print("2. Use a Personal Access Token with a configured credential helper.")
        print("3. Use ZIP Download only for public repositories.")
        print(f"\nDetails: {error_msg}")
        print("=" * 60 + "\n")
        return

    if is_network_error(error_msg):
        logging.warning("Network Error: %s", error_msg)
        print("\n" + "=" * 60)
        print("Network/proxy issue")
        print("=" * 60)
        print("The corporate firewall, proxy, or network path appears slow or unstable.")
        print("Suggested mitigations:")
        print("1. Prefer --method git with --branch to avoid full branch metadata fetches.")
        print("2. Increase GIT_FETCH_TIMEOUT/GIT_BRANCH_TIMEOUT in this script if needed.")
        print("3. Coordinate proxy allowlisting or a local mirror/cache with the IT/network team.")
        print(f"\nDetails: {error_msg}")
        print("=" * 60 + "\n")
        return

    logging.error("CLI Error: %s", error_msg)
    print(f"\nError: {error_msg}")


def _run_cli_sync_once(
    manager: GitManager,
    repo: str,
    branch: str,
    mirror: bool,
    method: str,
) -> int:
    log_callback = _make_cli_log_callback()
    print("\n" + "=" * 60)
    print("Git Sync CLI")
    print("=" * 60)
    print(f"Repository: {repo}")
    print(f"Branch:     {branch}")
    print(f"Method:     {method}")
    print(f"Mirror:     {'on' if mirror else 'off'}")
    print("=" * 60 + "\n")

    try:
        started_at = time.time()
        snapshot = manager.sync(repo, branch, mirror, log_callback, method=method)
    except Exception as e:
        _print_cli_error(str(e))
        return 1

    _print_cli_sync_done(branch, snapshot, time.time() - started_at)
    print()
    return 0


def _run_cli_manual_update(
    manager: GitManager,
    repo: str,
    branch: str,
    mirror: bool,
    method: str,
) -> int:
    log_callback = _make_cli_log_callback()

    print("\n" + "=" * 60)
    print("Git Sync CLI Manual Update")
    print("=" * 60)
    print(f"Repository: {repo}")
    print(f"Branch:     {branch} (default)")
    print(f"Method:     {method}")
    print(f"Mirror:     {'on' if mirror else 'off'}")
    print("Commands:   update, help, quit")
    print("Enter 'update' to sync the default branch. Press Ctrl+C to stop.")
    print("=" * 60 + "\n")

    try:
        while True:
            try:
                raw_command = input("git-sync> ").strip()
            except EOFError:
                print("\nManual update mode stopped because stdin closed.")
                return 0

            command = raw_command.lower()
            if not command:
                continue

            if command in {"q", "quit", "exit"}:
                print("Manual update mode stopped by user.")
                return 0

            if command in {"h", "help", "?"}:
                print("Commands:")
                print("  update  Sync the selected default branch.")
                print("  quit    Exit manual update mode.")
                continue

            if command != "update":
                print("Unknown command. Enter 'update' to sync or 'quit' to exit.")
                continue

            _print_cli_event("UPDATE", f"Syncing default branch: {branch}", CLI_YELLOW)
            try:
                started_at = time.time()
                snapshot = manager.sync(repo, branch, mirror, log_callback, method=method)
            except Exception as e:
                _print_cli_error(str(e))
                continue

            _print_cli_sync_done(branch, snapshot, time.time() - started_at)
    except KeyboardInterrupt:
        print("\nManual update mode stopped by user.")
        return 0
    except Exception as e:
        _print_cli_error(str(e))
        return 1


def _run_cli_auto_update(
    manager: GitManager,
    repo: str,
    branch: str,
    mirror: bool,
    method: str,
    interval_seconds: float,
) -> int:
    log_callback = _make_cli_log_callback()

    print("\n" + "=" * 60)
    print("Git Sync CLI Auto Update")
    print("=" * 60)
    print(f"Repository: {repo}")
    print(f"Branch:     {branch}")
    print(f"Method:     {method}")
    print(f"Mirror:     {'on' if mirror else 'off'}")
    print(f"Interval:   {interval_seconds:g}s")
    print("Press Ctrl+C to stop.")
    print("=" * 60 + "\n")

    try:
        started_at = time.time()
        synced_snapshot = manager.sync(repo, branch, mirror, log_callback, method=method)
        _print_cli_update_commit("AUTO BASE", branch, synced_snapshot, CLI_CYAN)
        _print_cli_sync_done(branch, synced_snapshot, time.time() - started_at)
        last_head = synced_snapshot.commit_sha

        while not last_head:
            try:
                last_head = manager.get_remote_branch_head(repo, branch)
            except Exception as e:
                log_callback(
                    "Auto update baseline check failed; "
                    f"will retry in {interval_seconds:g}s: {e}"
                )
                time.sleep(interval_seconds)

        while True:
            time.sleep(interval_seconds)
            try:
                current_head = manager.get_remote_branch_head(repo, branch)
            except Exception as e:
                log_callback(
                    "Auto update check failed; "
                    f"will retry in {interval_seconds:g}s: {e}"
                )
                continue

            if current_head == last_head:
                log_callback(
                    _cli_style(
                        f"No update detected on {branch} ({_short_sha(current_head)}).",
                        CLI_DIM,
                    )
                )
                continue

            current_snapshot = RemoteBranchSnapshot(commit_sha=current_head, committed_at="-")
            _print_cli_update_commit(
                "UPDATE",
                branch,
                current_snapshot,
                CLI_YELLOW,
                previous_sha=last_head,
            )
            try:
                started_at = time.time()
                synced_snapshot = manager.sync(repo, branch, mirror, log_callback, method=method)
            except Exception as e:
                _print_cli_error(str(e))
                continue

            last_head = synced_snapshot.commit_sha or current_head
            _print_cli_sync_done(branch, synced_snapshot, time.time() - started_at)
    except KeyboardInterrupt:
        print("\nAuto update mode stopped by user.")
        return 0
    except Exception as e:
        _print_cli_error(str(e))
        return 1


def run_command_line_mode(manager: GitManager, args: argparse.Namespace) -> int:
    prompt_settings = _should_prompt_cli_settings(args)
    if prompt_settings:
        print("\n--- Git Sync CLI Interactive Setup ---")

    repo = _select_cli_repository(args.repo)
    if not repo:
        print("No repository selected.")
        return 1

    try:
        branch = _select_cli_branch(manager, repo, args.branch)
    except Exception as e:
        _print_cli_error(str(e))
        return 1

    if not branch:
        print("No branch selected.")
        return 1

    try:
        update_mode = _select_cli_update_mode(
            args.auto,
            args.manual,
            args.watch,
            args.loop,
            prompt_settings,
        )
    except RuntimeError as e:
        _print_cli_error(str(e))
        return 1
    if update_mode is None:
        print("No sync mode selected.")
        return 1

    method = _select_cli_method(args.method, prompt_settings)
    if not method:
        print("No sync method selected.")
        return 1

    mirror_selected = _select_cli_mirror(args.no_mirror, prompt_settings)
    if mirror_selected is None:
        print("No mirror mode selected.")
        return 1
    mirror = bool(mirror_selected)

    auto_interval = _select_cli_auto_interval(
        args.watch_interval,
        update_mode,
        prompt_settings,
    )
    if auto_interval is None:
        print("No auto update interval selected.")
        return 1

    if update_mode == "auto":
        return _run_cli_auto_update(
            manager,
            repo,
            branch,
            mirror,
            method,
            auto_interval,
        )

    if update_mode == "manual":
        return _run_cli_manual_update(
            manager,
            repo,
            branch,
            mirror,
            method,
        )

    return _run_cli_sync_once(manager, repo, branch, mirror, method)


def is_network_error(error_msg: str) -> bool:
    """Check whether the error is network-related for both CLI and GUI flows."""
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
    """Check whether the error is credential-related."""
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
    m = input("Choice (1/2): ").strip()
    mode = "Loop Mode" if m == "2" else "Normal Mode"

    print("\nSelect Repository:")
    for i, r in enumerate(REPO_CHOICES, 1):
        print(f"[{i}] {r}")
    
    try:
        r_idx = int(input(f"Choice (1-{len(REPO_CHOICES)}): ").strip()) - 1
        repo = REPO_CHOICES[r_idx]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return None, None
        
    return repo, mode

def main():
    parser = argparse.ArgumentParser(description="Professional Git Sync Tool")
    parser.add_argument("--cli", action="store_true", help="Run command-line sync mode")
    parser.add_argument("--no-gui", action="store_true", help="Force legacy curses CLI/TUI mode")
    parser.add_argument("--repo", help="Pre-select repository URL or 1-based repository number")
    parser.add_argument("--branch", help="Pre-select branch for command-line sync")
    parser.add_argument("--method", choices=("git", "zip"), help="Sync method for CLI mode")
    parser.add_argument("--no-mirror", action="store_true", default=None, help="Do not delete local files absent from the selected branch")
    parser.add_argument("--auto", action="store_true", default=None, help="Watch the selected branch and sync automatically when it changes")
    parser.add_argument("--manual", action="store_true", default=None, help="Wait for the update command and sync the selected branch")
    parser.add_argument("--watch", action="store_true", default=None, help="Legacy alias for --auto in --cli mode")
    parser.add_argument(
        "--watch-interval",
        type=_positive_float,
        help="Polling interval in seconds for --auto/--watch",
    )
    parser.add_argument("--loop", action="store_true", default=None, help="Legacy alias for --auto in --cli mode")
    parser.add_argument("--archive", metavar="DIR", help="Create archive backup to specified directory and exit")
    parser.add_argument(
        "--skip-office-drm",
        action="store_true",
        help="Exclude Office DRM target files instead of using the cache/re-save flow",
    )
    args = parser.parse_args()
    args.repo = _resolve_repo_argument(args.repo)

    cwd = Path.cwd()
    log_path, redirected_log_path = resolve_log_path(cwd)
    setup_logging(log_path)
    if redirected_log_path is not None:
        logging.warning(
            "%s=%s points inside the repository and was redirected to %s "
            "to avoid git checkout file-lock conflicts.",
            LOG_PATH_ENV,
            redirected_log_path,
            log_path,
        )
    
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
        drm_mode = (
            "exclude target files"
            if args.skip_office_drm
            else "use cache; re-save cache misses"
        )
        print(f"Office DRM handling: {drm_mode}")
        print(f"{'='*60}\n")

        try:
            archive_path = manager.create_archive_backup(
                target_dir,
                print,
                skip_office_drm=args.skip_office_drm,
            )
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

    if args.cli:
        sys.exit(run_command_line_mode(manager, args))

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

                sel = input("Select branch number: ").strip()
                branch = branches[int(sel)-1]

                manager.sync(repo, branch, True, logging.info)

            except Exception as e:
                error_msg = str(e)
                if is_credential_error(error_msg):
                    logging.warning(f"Credential Error: {error_msg}")
                    print("\n" + "="*60)
                    print("Git authentication required")
                    print("="*60)
                    print("Private repositories require authentication.")
                    print("\nResolution:")
                    print("\n1. Use an SSH URL (recommended):")
                    print("   ssh-keygen -t ed25519 -C \"your_email@example.com\"")
                    print("   -> Register the public key in GitHub (Settings -> SSH keys)")
                    print("   -> Change the repository URL to git@github.com:user/repo.git")
                    print("\n2. Personal Access Token (PAT):")
                    print("   git config --global credential.helper store")
                    print("   -> Create a token in GitHub (Settings -> Developer settings)")
                    print("   -> Enter the token as the username when Git prompts for credentials")
                    print("\n3. ZIP Download for public repositories only:")
                    print("   -> Open the GUI and change Download Method to 'ZIP Download'")
                    print(f"\nDetails: {error_msg}")
                    print("="*60 + "\n")
                elif is_network_error(error_msg):
                    logging.warning(f"Network Error: {error_msg}")
                    print("\n" + "="*60)
                    print("Network connection issue")
                    print("="*60)
                    print("The corporate proxy server or network appears to have an issue.")
                    print("A 502/503 error or connection timeout occurred.")
                    print("Try again later.")
                    print(f"\nDetails: {error_msg}")
                    print("="*60 + "\n")
                else:
                    logging.error(f"CLI Error: {error_msg}")
                    print(f"\nError: {error_msg}")

if __name__ == "__main__":
    main()
