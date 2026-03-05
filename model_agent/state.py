"""Shared mutable state for Model Agent server."""

import threading

model_streams = {}
model_streams_lock = threading.Lock()

# Backward-compatible aliases for legacy imports.
gemini_streams = model_streams
gemini_streams_lock = model_streams_lock
