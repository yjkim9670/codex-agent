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
    "name": "오늘의 뜻밖",
    "topic_direction": "이상한 발명·숨은 웹사이트·잊힌 미래·색다른 해결책과 일상의 연결",
    "allow_web_research": true,
    "enabled": true,
    "language": "한국어",
    "audience": "매일 새로운 발견을 만나고 싶은 한국어 독자",
    "style_guide": "친근한 해요체. 오늘의 발견 → 뜻밖의 포인트 → 우리와의 연결 → 직접 보기. 사실 확인과 설명이 붙은 원문 링크.",
    "cadence_minutes": 360,
    "reasoning_effort": "low",
    "backlog": [
      "우주 기술이 일상의 도구가 된 사례",
      "직접 둘러볼 수 있는 디지털 자료실"
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

New project defaults follow **오늘의 뜻밖**: unusual inventions, hidden websites,
forgotten futures and creative solutions, each connected to everyday life.
The voice uses friendly Korean 해요체, short paragraphs and simple explanations.
Articles follow 오늘의 발견 → 뜻밖의 포인트 → 우리와의 연결 → 직접 보기,
with evidence links and dates that distinguish old material from recent news.
Web research is enabled by default. Discovery articles need research before drafting;
allowing web access does not itself verify facts or guarantee a daily publication.
Existing projects retain their saved settings until explicitly updated.

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
Pausing the blog pauses automatic lightweight tasks.

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

Automatic and manual lightweight tasks run only the blog pipeline, regardless
of TG Platform runner availability or documentation candidates. They do not
inspect or synchronize TG Platform documents. The standalone `/metadata-sync`
page remains available for explicit manual documentation work. No external
documentation scheduler is installed or changed by Workbench lightweight tasks.

The pipeline never starts while the selected account already has an active
Codex stream in the same process. A failed stage records a 30-minute retry time. Automatic submission continues
to use the existing account-wide usage-window reservation and retry policy.
