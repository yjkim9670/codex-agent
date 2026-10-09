# Team execution

Team is a Codex-only execution mode. It replaces Secondary in the desktop and
mobile composer and Shift+Tab cycle: `Work → Plan → Team → Plan+`. Stored
`secondary` composer values migrate to `team`; the secondary model and effort
settings and their other uses remain available.

Set a secondary model explicitly before submitting a Team request. Workbench
captures the main and secondary model/effort, account, and Codex backend at
submission, including queued requests. Changing settings afterward does not
switch the models or backend of that Team request.

The server runs three stages:

1. Main analysis inspects the workspace without editing files and returns one
   to four tasks containing goals, allowed file scope, dependencies, and checks.
2. Secondary workers execute those tasks sequentially in the same workspace.
   Later workers receive earlier results. A failed worker stops subsequent
   dependent tasks and hands the failure to main review.
3. Main review receives the original context and worker reports, inspects the
   actual diff, repairs omissions/failures, runs integration checks, and returns
   the final answer. Invalid or failed analysis also goes to main review.

File scope and the prohibition on further delegation are worker instructions.
The analysis stage additionally uses the existing read-only execution policy.
Team uses the existing execution sandbox for workers and review. It does not
introduce separate filesystem sandboxes for individual task scopes.

Attachments, account, and execution directory carry through every stage. When
Worktree is selected, one worktree is created for the request and shared by all
stages. Team does not create a worktree for each worker.

The parent chat remains active throughout execution. Live output shows the stage
and model. Its expandable message details retain stage status, reports, and child
session identifiers; the child sessions contain individual execution logs and
model usage. The server persists phase transitions, so browser refreshes and
mobile disconnects do not control execution. Team supports up to four workers,
a 30-minute overall deadline (including execution-gate waiting), and no automatic
worker retries. Workers cannot delegate further.

Stopping the parent also stops its active child and prevents further Team stages.
Stopping a child causes the parent to treat that stage as failed. Work, Plan,
Plan+, read-only Sub jobs, and structured reports retain their existing paths.
A structured report selected while Team is active still uses the report path.

After a server process restart, opening the parent session marks a persisted
running Team request as interrupted. Completed reports and existing workspace
changes remain. No stage is automatically replayed: review the changes and submit
a follow-up request to continue. Automatic checkpoint resume and parallel workers
are not included in this version.

## Team P1 safeguards

Workers now report explicit JSON status and per-check commands, exit codes, and
validation status. Failed, skipped, missing or malformed check results stop
dependent workers and go to main review. These results are model-reported;
independent verification of the recorded commands is not yet provided.

The controller fingerprints dirty/untracked Git paths before and after each
worker, compares changes with allowed relative path/glob scopes, and flags
out-of-scope modifications or new Git HEAD revisions. It never resets edits.
Non-Git workspaces fail closed for workers.

An OS advisory Codex execution lock spans the whole Team lifecycle, including
gaps between stages. Team child threads inherit permission to share the lock
without deadlock. The 30-minute limit includes waiting for that lock.
