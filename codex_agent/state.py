"""Shared mutable state for Codex chat server."""

import threading

codex_streams = {}
codex_streams_lock = threading.Lock()
