"""Shared mutable state for Gemini chat server."""

import threading

gemini_streams = {}
gemini_streams_lock = threading.Lock()
