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

The five stages are run separately:

```text
brief → research → outline → draft → review
```

## Five-run article cycle

One article always remains active until its five stages have completed:

```text
brief → research → outline → draft → review/final
```

This is stage-count based, not calendar based. If fewer than five lightweight
tasks run in a day, the same article simply resumes at its next stage on a
later run. After `review` succeeds, Workbench marks that article complete and
appends one new deterministic topic candidate to `backlog.json`; this local
rotation does not create an additional model request or spend tokens.
Customize the completion rotation with `topic_rotation_seeds` (or set
`topic_rotation_enabled` to `false`):

```json
{
  "topic_rotation_enabled": true,
  "topic_rotation_seeds": [
    "반복 업무를 줄이는 작은 AI 활용법",
    "AI 결과물을 안전하게 검토하는 방법"
  ]
}
```

The completion-counted ID prevents duplicates if completion handling is
replayed. A new candidate is queued behind any existing topics; the pipeline
still completes the active article one stage at a time.

After review, the completed article is in `blog/posts/<post-id>/final.md`, and
the next queued topic becomes active. The pipeline reads only the small set of
files needed by the current stage and keeps `continuity.json` compact.

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

The pipeline never starts while the selected account already has an active
Codex stream in the same process. A failed stage records a 30-minute retry
time for explicit API runs; it does not cause another automatic usage-window
submission.
