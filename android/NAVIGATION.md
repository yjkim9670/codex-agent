# Android navigation

The server selection screen is the root screen of the Codex Workbench Android app.

- App launch opens the server selection screen directly.
- Pressing the Android Back button from a connected Codex Workbench page returns to server selection instead of navigating WebView history.
- Pressing Back from the process dashboard browser returns to server selection.
- Tapping the system dashboard card connects immediately.
- Codex Workbench cards keep the select-then-connect flow.


Version 1.2.0 adds Task / Chat selection. Both modes use only Tailscale or Cloudflare. Chat connects to the conversation server using HTTPS, and source links open externally. Completion notifications bypass selection and open the completed Workbench session. Restoring an Activity recreates its selected connection instead of discarding it.

See [implementation and handoff](IMPROVEMENTS.md) for connection policy, build instructions and remaining device checks.
