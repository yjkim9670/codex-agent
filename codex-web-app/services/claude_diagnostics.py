"""Dependency-free Claude startup diagnostics shared by the server and CLI probe."""
import codecs
import io
import os
import re
import time
from datetime import datetime


def observed_lines(pipe, on_first_byte):
    """Read available bytes without waiting for a newline; preserve text line parsing.

    The fallback supports in-memory text pipes used by callers/tests. It cannot
    distinguish bytes from lines and deliberately does not report a byte time.
    """
    binary = getattr(pipe, 'buffer', pipe)
    read = getattr(binary, 'read1', None)
    if read is None:
        yield from iter(pipe.readline, '')
        return
    decoder = io.IncrementalNewlineDecoder(
        codecs.getincrementaldecoder('utf-8')(errors='replace'), translate=True)
    pending = ''
    first = True
    while True:
        chunk = read(65536)
        if chunk and first:
            first = False
            on_first_byte()
        pending += decoder.decode(chunk, final=not chunk)
        lines = pending.split('\n')
        pending = lines.pop()
        for line in lines:
            yield line + '\n'
        if not chunk:
            if pending:
                yield pending
            return


def summarize_debug_log(path, limit=4 * 1024 * 1024):
    """Return bounded timing metadata, never raw debug text or extracted values."""
    started = time.monotonic()
    result = {'status': 'missing', 'scanned_bytes': 0, 'truncated': False,
              'timestamped_lines': 0, 'categories': {}, 'longest_gaps': []}
    previous = None
    try:
        with open(path, 'rb') as source:
            result['status'] = 'collected'
            result['file_bytes'] = os.fstat(source.fileno()).st_size
            while result['scanned_bytes'] < limit:
                raw = source.readline(min(65536, limit - result['scanned_bytes']))
                if not raw:
                    break
                result['scanned_bytes'] += len(raw)
                line = raw.decode('utf-8', errors='replace')
                match = re.match(r'^(\d{4}-\d\d-\d\dT[\d:.]+(?:Z|[+-]\d\d:\d\d))', line)
                if not match:
                    continue
                try:
                    stamp = datetime.fromisoformat(match[1].replace('Z', '+00:00')).timestamp()
                except ValueError:
                    continue
                lower = line.lower()
                category = next((name for name, terms in (
                    ('mcp', ('mcp',)), ('hook', ('hook',)),
                    ('auth', ('oauth', 'credential', 'authentication')),
                    ('network', ('request', 'connect', 'fetch', 'retry')),
                    ('settings', ('settings', 'config', 'plugin', 'skill')),
                ) if any(term in lower for term in terms)), 'other')
                counts = result['categories']
                counts[category] = counts.get(category, 0) + 1
                result['timestamped_lines'] += 1
                if previous and stamp >= previous[0]:
                    result['longest_gaps'].append({
                        'gap_ms': round((stamp - previous[0]) * 1000, 3),
                        'before': previous[1], 'after': category})
                    result['longest_gaps'] = sorted(
                        result['longest_gaps'], key=lambda item: item['gap_ms'], reverse=True)[:10]
                previous = stamp, category
            result['truncated'] = bool(source.read(1))
    except OSError:
        pass
    result['summary_scan_ms'] = round((time.monotonic() - started) * 1000, 3)
    return result
