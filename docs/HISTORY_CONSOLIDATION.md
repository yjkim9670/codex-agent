# Workbench history consolidation

The standalone **통합 기록** link opens `/history`. It provides a single project
selector and conversation viewer across registered Workbench installations.
Original JSON histories are read live. SQLite databases, execution homes,
queues, accounts, and working directories stay with their original Workbench.
The viewer cannot submit prompts, replay pending jobs, or modify original data.
Internal multi-user and company deployments do not expose this standalone
library, to preserve user isolation and encrypted chat transport.

## Import and refresh

The library defaults to `~/.codex-workbench/history/library.json`, under the
existing shared account-state root. `CODEX_WORKBENCH_SHARED_ACCOUNT_STATE_DIR`
also changes this root. Set `CODEX_WORKBENCH_HISTORY_LIBRARY` for an explicit
library file; the CLI accepts `--library` too. CLI and server must use the same
path. Treat the library as private conversation data; keep it out of Git.

Preview the import before applying it:

```bash
python3.14 scripts/consolidate_history.py --source /path/to/project/codex_agent
python3.14 scripts/consolidate_history.py --source /path/to/project/codex_agent --apply
```

Repeat `--source` to import multiple installations. The default project path is
its parent, matching the standard Workbench launch behavior. For a custom
`CODEX_WORKSPACE_DIR`, use one `--source` plus `--workspace /actual/project`.
For custom state locations use:

```bash
python3.14 scripts/consolidate_history.py \
  --workspace /actual/project \
  --store /custom/state/codex_chat_sessions.json --apply
```

Imports validate all source JSON before writing and abort on invalid sources or
an invalid existing library. Sessions are merged by project and session ID,
using the existing Workbench message and timestamp merge rules. Same session
IDs in different projects remain distinct. Imported records retain original IDs
and metadata, including queued data, but the viewer never executes them.

Writes take a process lock and atomically replace the library with a private
file. Every replacement preserves the previous library in a timestamped
`library.json.backup-*` file. Original stores are never overwritten. Re-import
refreshes the archived snapshot without dropping previously archived messages.
Backups are deliberately retained until the operator validates the transition.

The viewer uses readable live source files, including deletions, as authoritative.
When any registered original becomes missing or corrupt, it uses the imported
snapshot alongside remaining originals and displays a fallback notice. Refresh
snapshots before moving or archiving old installations. Cross-machine Git sync
moves the implementation, not local paths, private records, or credentials;
register the target machine's paths separately.

## Operational transition

Use the development Workbench as the primary history viewer. On this machine,
5 installations were registered with 2,127 project-scoped conversations:

| Project | Conversations |
| --- | ---: |
| `/Users/dinya/works` | 603 |
| `/Users/dinya/works/dev_workspace` | 251 |
| `/Users/dinya/works/Sensor_Projects/CommonTG-Verification-Platform` | 700 |
| `/Users/dinya/works/Personal-Finance-Manager` | 507 |
| `/Users/dinya/works/Sensor_Projects/GL-FW-DV-Constraint-Review` | 66 |

These counts are the initial import, not a global unique-session count. A copied
conversation in separate projects intentionally remains available in both.

The existing shared accounts and usage architecture is retained. This change
centralizes history viewing and archival imports; it does **not** route execution,
file browsing, terminals, or Git commands across projects. Keep existing project
servers until those operations support project-scoped execution and have been
validated. Do not delete execution databases or symlink separate execution homes
together. Full retirement of replica servers remains a later rollout step.

After syncing this code, restart the development Workbench when its active jobs
finish to expose the new `/history` route. No existing server is automatically
stopped or restarted. After reviewing recent conversations and usage, refresh
the archive and retain old installations for the planned two-week stabilization
period before considering deletion.

## Validation

```bash
python3.14 -m pytest -q tests/test_history_library.py
python3.14 -m pytest -q tests/test_codex_chat_streams.py -k 'session_store or merge_session or session_storage'
python3.14 scripts/verify_browser_ui.py --url http://127.0.0.1:PORT/history --selector '#history-count'
```

Use a temporary server on an unused loopback port for browser checks. Disable
background queue and usage workers in the temporary test process; leave the
operating servers alone.
