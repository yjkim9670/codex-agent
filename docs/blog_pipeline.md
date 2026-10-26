# Blog pipeline

The Workbench blog pipeline stores its durable state under `blog/` in the
current workspace. It is disabled until a project is configured with
`enabled: true`, so creating the app does not consume model tokens.

## Configure a project

```bash
curl -X PUT http://127.0.0.1:5000/api/codex/blog \
  -H 'Content-Type: application/json' \
  -d '{
    "project_id": "main-blog",
    "name": "My technical blog",
    "enabled": true,
    "language": "한국어",
    "audience": "개발자가 아닌 실무자도 이해할 수 있는 설명",
    "style_guide": "짧은 문단, 과장 없는 제목, 예시는 실제로 검증 가능한 것만 사용",
    "cadence_minutes": 360,
    "reasoning_effort": "low",
    "backlog": [
      "첫 번째 글의 주제",
      "두 번째 글의 주제"
    ]
  }'
```

## Article cycle and dashboard

Open **Settings → 자동 경량작업 → 블로그 집필 목록 · 작업물 대시보드**
(`/blog`) to read the post list, backlog inspirations, drafts, reviews and final
articles. Article contents are shown as text, including Markdown, without executing
HTML. The page shows per-post cumulative tokens (input, cached input, output and
total), duration, and recent stage runs. Old runs without duration report zero.
Legacy final files are labeled “완성본 있음”; this does not certify their facts.

New articles default to three model runs (`pipeline_mode: compact`):

```text
plan (topic + brief + outline + evidence needs) → draft → review/final
```

If `plan.json` sets `needs_research: true`, a separate `research` run comes before
the draft. If web research is disabled, the article waits at research until it
is enabled. Research must produce a nonempty list of HTTP(S) source URLs in
`sources.json` and `research.md`. The model remains responsible for checking
source relevance and factual support; file validation is not independent fact checking.

Already active legacy articles keep their original six-run flow:
`topic → brief → research → outline → draft → review`. An explicit
`pipeline_mode: legacy` also retains that flow for later articles.
The next article defaults to the compact flow when the setting is absent.

Every successful stage must produce its required nonempty files and update them
in that run. Missing, empty or unchanged files fail the stage without advancing.
Review requires `review.md`, `final.md`, and `review.json` with
`{"verified": true, "pending_claims": []}`. Unsupported claims leave the article
waiting for verification. Recent titles are retained in `continuity.json` to
help avoid repeated topics; review prompts also check structure and phrasing.

`topic_direction`, `audience` and `style_guide` control editorial direction.
Existing projects without `topic_direction` use their audience as the initial
direction. AI topics are allowed by default; `exclude_ai_topics: true` opts out.
`topic_rotation_seeds` supply inspirations. Setting `topic_rotation_enabled` to
false stops new article planning after the current/first article completes.
No deterministic topic is appended after completion: topic planning consumes
one of the model runs described above.

Automatic blog runs honor `cadence_minutes` (default 360, minimum 60),
`daily_run_budget` (default 6), `daily_token_budget` (default 300000), and
`automatic_paused`. Budgets count this workspace's recorded starts/tokens,
including manual runs, by KST date. Token totals include cached input, so this
is a processing budget rather than a monetary cost estimate. A running stage
can exceed the remaining budget; later automatic runs are blocked.
Manual immediate runs bypass the cadence and budgets but retain all locks.
Pausing the blog does not pause TG Platform document synchronization.

Stage history includes prompt character count and the size of allowed files at
submission. These help compare context size with actual input/cache/output
usage; they do not measure every model tool read or attribute token costs to
individual tool calls. The draft can read both research notes and sources.

Use `GET /api/codex/blog` for status. The Usage panel's **manual lightweight
task** button advances this exact same pipeline immediately, one stage at a
time. It bypasses the interval check but retains account, project-lease, and
in-flight-run protection. The endpoint below remains available for an
explicit API-triggered run:

```bash
curl -X POST http://127.0.0.1:5000/api/codex/blog/run \
  -H 'Content-Type: application/json' \
  -d '{"force": true}'
```

## Workbench collision policy

Each run claims `account identity + project_id` in the shared account state
under an inter-process file lock. The claim has a two-hour lease for crash
recovery and a six-hour default cooldown after success. An active claim is
authoritative even for a forced manual run, so simultaneous Usage-panel or API
submissions from separate Workbenches yield `project_busy` rather than starting
a second stage. Give independent blogs different `project_id` values.

There is no separate blog polling worker. Automatic execution is driven only
by the existing usage refresh: when the five-hour usage is observed at exactly
0%, one enabled blog stage is queued for that usage window. The account-wide
zero-window claim prevents another Workbench from submitting a second stage.
Weekly usage is not an automatic trigger. A missing or disabled blog project
does not reserve the window or make a model request.

On a single-user Workbench with the TG Platform runner available, an automatic
lightweight task checks documentation candidates first. With no candidates or
immediate update reasons it advances one blog stage directly. Otherwise it runs
the existing guarded daily documentation batch using the selected account's
Codex home. A successful batch with an explicit empty `changes` list falls back
to one blog stage; a batch that changes documents completes the task itself.
Sync failures, unreadable results, and an active sync defer or fail the task
without starting a blog stage. The account usage-window claim and existing
cross-Workbench blog project claims remain in effect across this decision.
The Usage panel's manual button and explicit blog API still run a blog stage.
Internal multiuser deployments and installations without the TG runner retain
the blog-only behavior. No scheduler is installed or changed by this routing.

The pipeline never starts while the selected account already has an active
Codex stream in the same process. A failed stage records a 30-minute retry time. Automatic submission continues
to use the existing account-wide usage-window reservation and retry policy.
