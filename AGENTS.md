# Codex Workbench Design Instructions

For UI, infographic, dashboard, and design-system work under this project:

- Read `design.md` first.
- Default to IBM Carbon style unless the user explicitly asks for another visual system.
- Favor structured enterprise layouts over marketing-style cards, gradients, or oversized decorative motion.

## App Icon

- The canonical Android launcher icon is `android/app/src/main/res/drawable/ic_workbench_foreground.xml` on the deep-navy adaptive-icon background defined by `launcher_background`.
- Keep the current terminal/workbench mark: an open cyan-to-blue-to-violet hexagonal frame, a large terminal `>` chevron, and a short prompt bar.
- Treat this icon as the default Codex Workbench app identity for future Android builds and UI work.
- Do not replace, redesign, or revert the launcher icon unless the user explicitly requests an icon change.

## Running Process Safety

- Do not stop or restart proc manager tasks, Codex Workbench servers, Flask servers, or active development servers unless the user explicitly asks for it.
- When code changes require a restart to take effect, leave the running process alone and tell the user which proc manager task or server should be restarted.

## Canonical Code Modification Scope

- For all future Codex Workbench code, tests, assets, documentation, and project instruction changes on this PC, edit only `/Users/dinya/works/dev_workspace/codex_workbench/`.
- Other Workbench checkouts are read-only references and usage data sources. Do not modify or synchronize their code; the user handles Git sync.
- Shared usage data may be updated by the authorized application collectors; this does not authorize editing code outside the canonical checkout.
- The structured execution prompt repeats this Workbench-only scope when the canonical checkout exists, so Git-synced copies keep the instruction even when another coding agent runs from another workspace.
