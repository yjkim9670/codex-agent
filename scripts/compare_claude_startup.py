"""Sequential Claude startup comparisons. Inherits authentication/proxy environment.

Use a harmless prompt: every repetition makes a real model request. Raw logs are
local diagnostic artifacts and may contain sensitive CLI output.
"""
import argparse
import csv
import json
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'codex-web-app' / 'services'))
from claude_diagnostics import observed_lines, summarize_debug_log

CASES = ('baseline', 'baseline_debug', 'no_mcp', 'user_settings', 'no_commands', 'empty_cwd')


def command_for_case(command, case, directory):
    command = list(command)
    if case != 'baseline':
        command += ['--debug-file', str(directory / 'claude.debug.log')]
    if case == 'no_mcp':
        config = directory / 'empty-mcp.json'
        config.write_text('{"mcpServers": {}}', encoding='utf-8')
        command += ['--strict-mcp-config', '--mcp-config', str(config)]
    elif case == 'user_settings':
        command += ['--setting-sources', 'user']
    elif case == 'no_commands':
        command += ['--disable-slash-commands']
    return command


def run_probe(command, prompt, cwd, directory, timeout, label):
    directory.mkdir(parents=True, mode=0o700)
    result = {'status': 'starting', 'exit_code': None}
    lock = threading.Lock()
    started = time.monotonic()

    def mark(name):
        with lock:
            result.setdefault(name, round((time.monotonic() - started) * 1000, 3))

    try:
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        result.update(status='start_failed', error_type=type(exc).__name__)
        return result
    mark('process_spawned_ms')

    def reader(pipe, name):
        try:
            mark(name + '_reader_started_ms')
            with (directory / (name + '.log')).open('w', encoding='utf-8') as log:
                for line in observed_lines(pipe, lambda: mark('first_' + name + '_byte_ms')):
                    mark('first_' + name + '_line_ms')
                    log.write(line)
                    if name == 'stdout':
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(event, dict):
                            if event.get('type') == 'system' and event.get('subtype') == 'init':
                                mark('claude_system_init_ms')
                            if event.get('type') == 'result':
                                mark('claude_result_ms')
                                if event.get('is_error'):
                                    with lock:
                                        result['cli_result_error'] = True
        except (OSError, ValueError) as exc:
            with lock:
                result[name + '_collector_error'] = type(exc).__name__
        finally:
            pipe.close()

    def writer():
        try:
            process.stdin.write(prompt)
            process.stdin.close()
            mark('stdin_finished_ms')
        except (OSError, ValueError) as exc:
            with lock:
                result['stdin_error'] = type(exc).__name__

    threads = [threading.Thread(target=reader, args=(process.stdout, 'stdout'), daemon=True),
               threading.Thread(target=reader, args=(process.stderr, 'stderr'), daemon=True),
               threading.Thread(target=writer, daemon=True)]
    for thread in threads:
        thread.start()
    try:
        while process.poll() is None:
            elapsed = time.monotonic() - started
            print(f'\r{label}: {elapsed:.1f}s', end='', flush=True)
            if elapsed >= timeout:
                result['status'] = 'timeout'
                process.kill()
                break
            time.sleep(0.2)
        process.wait()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        for thread in threads:
            thread.join(timeout=3)
        print()
    mark('completed_ms')
    if any(thread.is_alive() for thread in threads):
        result['status'] = 'collector_incomplete'
    elif result['status'] == 'starting':
        result['status'] = ('ok' if process.returncode == 0
                            and 'claude_system_init_ms' in result
                            and 'claude_result_ms' in result
                            and not result.get('cli_result_error')
                            and not any(key.endswith('_error') for key in result)
                            else 'failed')
    result['exit_code'] = process.returncode
    for name, start, end in (
        ('spawn_to_init_ms', 'process_spawned_ms', 'claude_system_init_ms'),
        ('spawn_to_byte_ms', 'process_spawned_ms', 'first_stdout_byte_ms'),
        ('byte_to_line_ms', 'first_stdout_byte_ms', 'first_stdout_line_ms'),
    ):
        if start in result and end in result:
            result[name] = round(result[end] - result[start], 3)
    if (directory / 'claude.debug.log').exists():
        result['debug_summary'] = summarize_debug_log(directory / 'claude.debug.log')
    with lock:
        return dict(result)


def summarize(rows):
    summaries = {}
    for case in CASES:
        eligible = [row for row in rows if row['case'] == case
                    and not row['warmup'] and row['status'] == 'ok']
        entry = {'successful_measured_runs': len(eligible)}
        for field in ('spawn_to_init_ms', 'spawn_to_byte_ms', 'byte_to_line_ms', 'completed_ms'):
            values = [row[field] for row in eligible if field in row]
            if values:
                entry[field] = {'median': round(statistics.median(values), 3),
                                'min': min(values), 'max': max(values)}
        summaries[case] = entry
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--command-file', type=Path, required=True,
                        help='UTF-8 JSON array of baseline Claude argv, without credentials/debug/comparison flags')
    parser.add_argument('--prompt-file', type=Path, required=True)
    parser.add_argument('--cwd', type=Path, required=True)
    parser.add_argument('--empty-cwd', type=Path, required=True,
                        help='Empty local folder outside the project and its parents')
    parser.add_argument('--output', type=Path, required=True, help='New result directory')
    parser.add_argument('--repeats', type=int, default=3, choices=range(3, 6))
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    command = json.loads(args.command_file.read_text(encoding='utf-8-sig'))
    forbidden = ('--debug', '--debug-file', '--mcp-config', '--strict-mcp-config',
                 '--setting-sources', '--disable-slash-commands')
    if (not isinstance(command, list) or not command
            or not all(isinstance(item, str) for item in command)
            or any(item.split('=')[0] in forbidden for item in command)):
        parser.error('Baseline must be an argv array without debug/comparison flags.')
    if '--output-format' not in command or 'stream-json' not in command or '--verbose' not in command:
        parser.error('Baseline requires --output-format stream-json --verbose.')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    cwd = args.cwd.resolve(strict=True)
    empty = args.empty_cwd.resolve()
    if empty == cwd or cwd in empty.parents or empty in cwd.parents:
        parser.error('--empty-cwd must be outside the project and its parents')
    empty.mkdir(parents=True, exist_ok=True)
    if any(empty.iterdir()):
        parser.error('--empty-cwd must initially be empty')
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    prompt = args.prompt_file.read_bytes()
    rows = []
    # First pass is warmup, excluded from aggregates. Reverse alternate rounds
    # so baseline is not always the first request in each measured round.
    for round_index in range(args.repeats + 1):
        cases = CASES if round_index % 2 == 0 else tuple(reversed(CASES))
        for case in cases:
            directory = output / f'{round_index:02d}-{case}'
            directory.mkdir(mode=0o700)
            probe_command = command_for_case(command, case, directory)
            row = run_probe(probe_command, prompt, str(empty if case == 'empty_cwd' else cwd),
                            directory, args.timeout, f'round={round_index} {case}')
            row.update(case=case, round=round_index, warmup=round_index == 0)
            rows.append(row)
            (output / 'results.json').write_text(json.dumps({
                'runs': rows, 'summary': summarize(rows)}, indent=2), encoding='utf-8')
            fields = sorted(set().union(*(row.keys() for row in rows)) - {'debug_summary'})
            with (output / 'results.csv').open('w', newline='', encoding='utf-8') as destination:
                writer = csv.DictWriter(destination, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            if row['status'] == 'collector_incomplete':
                return 1
    print(json.dumps(summarize(rows), indent=2))
    return int(any(row['status'] != 'ok' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
