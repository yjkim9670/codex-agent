# Codex Workbench Design Instructions

For UI, infographic, dashboard, and design-system work under this project:

- Read `design.md` first.
- Default to IBM Carbon style unless the user explicitly asks for another visual system.
- Favor structured enterprise layouts over marketing-style cards, gradients, or oversized decorative motion.

## Running Process Safety

- Do not stop or restart proc manager tasks, Codex Workbench servers, Flask servers, or active development servers unless the user explicitly asks for it.
- When code changes require a restart to take effect, leave the running process alone and tell the user which proc manager task or server should be restarted.
