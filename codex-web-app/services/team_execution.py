"""Codex-only, server-owned sequential Team execution using ordinary child streams.

A persisted parent message records every transition. Interrupted runs are never
replayed automatically: code edits may already have happened before a restart.
"""
from copy import deepcopy
from contextvars import copy_context
import json
import threading
import time

MAX_WORKERS = 4
MAX_RUN_SECONDS = 1800


class TeamCancelled(Exception):
    pass


def parse_tasks(text):
    text = str(text or '').strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    payload = json.loads(text)
    tasks = payload.get('tasks') if isinstance(payload, dict) else None
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_WORKERS:
        raise ValueError(f'Team 분석 결과에는 1~{MAX_WORKERS}개의 tasks가 필요합니다.')
    result = []
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError('Team task 형식이 올바르지 않습니다.')
        for key in ('goal', 'files', 'validation'):
            if not isinstance(task.get(key), str) or not task[key].strip():
                raise ValueError(f'Team task의 {key}가 비어 있습니다.')
        result.append({key: task[key].strip() for key in ('goal', 'files', 'validation')})
    return result


def settings_snapshot(chat):
    settings = chat.get_settings()
    main_model, main_effort = chat.resolve_model_role_settings('main', settings)
    if not main_model:
        main_model = chat._parse_top_level_config(chat._read_codex_config_text()).get('model')
    return {
        'agent_backend': chat.get_selected_agent_backend(),
        'main_model': main_model,
        'main_effort': main_effort or chat.resolve_response_reasoning_effort(model_override=main_model),
        'worker_model': str(settings.get('secondary_model') or '').strip() or None,
        'worker_effort': settings.get('secondary_reasoning_effort') or main_effort or chat.resolve_response_reasoning_effort(model_override=main_model),
    }


def validate_settings(chat, settings, plan_mode=False, read_only=False):
    if settings.get('agent_backend') != 'codex':
        return 'Team 모드는 Codex 실행 백엔드에서만 지원합니다.'
    if not settings.get('worker_model'):
        return 'Team 실행 전에 세컨더리 모델을 지정해 주세요.'
    if plan_mode or read_only:
        return 'Team 모드는 Plan 및 read-only 보고서와 함께 실행할 수 없습니다.'
    return None


def run(chat, stream_id, original_context):
    with chat.state.codex_streams_lock:
        parent = chat.state.codex_streams[stream_id]
        settings = deepcopy(parent['team_settings'])
        parent_session_id = parent['session_id']
        account_id = parent['account_id']
        attachments = deepcopy(parent['attachments'])
        worktree = deepcopy(parent['worktree_task'])
        cwd = parent['execution_cwd']
    deadline = time.monotonic() + MAX_RUN_SECONDS
    reports = []

    def check():
        with chat.state.codex_streams_lock:
            if parent.get('cancelled'):
                raise TeamCancelled()
        if time.monotonic() >= deadline:
            raise TimeoutError('Team 실행 제한 시간(30분)을 초과했습니다.')

    def persist():
        chat._persist_stream_progress(stream_id, force=True)

    def stage(phase, title, prompt, worker=False):
        check()
        child = chat.create_session(title=f'Team: {title}', metadata={
            'session_type': 'team_worker' if worker else 'team_main',
            'parent_session_id': parent_session_id, 'team_parent_stream_id': stream_id,
        })
        model = settings['worker_model' if worker else 'main_model']
        effort = settings['worker_effort' if worker else 'main_effort']
        # Team owns delegation; its children cannot recursively launch agents.
        prompt += '\n\nTeam controller owns delegation. Do not spawn subagents or delegate further. Do not commit, push, or deploy unless the original user explicitly authorized it.'
        if phase == 'analysis':
            prompt += '\nInspect only. Do not edit project files during this analysis step.'
        chat.append_message(child['id'], 'user', prompt, {'model_role': 'secondary' if worker else 'main'})
        assistant = chat.append_message(child['id'], 'assistant', '', {'streaming': True})
        info = chat.create_codex_stream(
            child['id'], prompt, model_override=model, reasoning_override=effort,
            attachments=attachments, assistant_message_id=assistant['id'],
            user_prompt=parent['user_prompt'], worktree_task=worktree,
            account_id=account_id, model_role='secondary' if worker else 'main',
            agent_backend_override='codex', deferred_start=True, question_only=phase == 'analysis',
            preflight_usage_snapshot={}, inherit_model_settings=False,
        )
        child_id = info['id']
        with chat.state.codex_streams_lock:
            child_stream = chat.state.codex_streams[child_id]
            child_stream['execution_cwd'] = cwd
            parent['team_child_stream_id'] = child_id
            step = {'phase': phase, 'title': title, 'session_id': child['id'],
                    'stream_id': child_id, 'model': model, 'effort': effort, 'status': 'running'}
            parent['team_run']['phase'] = phase
            parent['team_run']['steps'].append(step)
        chat._append_stream_chunk(stream_id, 'output', f'\n{title} · {model or "default"}\n')
        persist()
        ctx = copy_context()
        thread = threading.Thread(target=lambda: ctx.run(chat._run_codex_stream, child_id, prompt), daemon=True)
        try:
            check()
            thread.start()
            while thread.is_alive():
                check()
                thread.join(.25)
            check()
        except (TeamCancelled, TimeoutError):
            chat.stop_codex_stream(child_id)
            with chat.state.codex_streams_lock:
                step['status'] = 'cancelled' if parent.get('cancelled') else 'failed'
            persist()
            raise
        with chat.state.codex_streams_lock:
            result = child_stream.get('output_last_message') or child_stream.get('output') or ''
            error = child_stream.get('error') or ''
            step['status'] = 'completed' if (child_stream.get('exit_code') == 0
                and not child_stream.get('codex_error_seen') and result.strip()) else 'failed'
            step['result'] = result
            step['error'] = error
            parent['team_child_stream_id'] = None
        persist()
        return result, error, step['status']

    try:
        analysis, error, status = stage('analysis', '메인 분석 중', original_context + '''

Analyze the original user request and inspect this workspace. Return ONLY a JSON
object with a "tasks" array of 1 to 4 sequential worker tasks. Each task has
"goal", "files" (allowed file scope), and "validation" strings. Include dependencies
in each goal; later workers see earlier results. Preserve existing features.
Do not implement yet. Workers use the configured secondary model.
''')
        if status != 'completed':
            reports.append({'analysis_failed': error or analysis})
        else:
            try:
                tasks = parse_tasks(analysis)
            except (ValueError, TypeError) as exc:
                reports.append({'analysis_failed': str(exc), 'analysis': analysis})
                tasks = []
            with chat.state.codex_streams_lock:
                parent['team_run']['tasks'] = tasks
            persist()
            for index, task in enumerate(tasks):
                result, error, status = stage('worker', f'워커 {index + 1}/{len(tasks)} 실행 중',
                    original_context + '\n\nYour assigned task:\n' + json.dumps(task, ensure_ascii=False)
                    + '\nEarlier worker results:\n' + json.dumps(reports, ensure_ascii=False)
                    + '\nImplement only the assigned scope. Run the specified checks. Report changed files, tests, failures, and remaining issues.', worker=True)
                reports.append({'task': task, 'status': status, 'result': result, 'error': error})
                if status == 'failed':
                    break  # dependent work must not proceed with a failed prerequisite
        final, error, status = stage('review', '메인 검토 중', original_context
            + '\n\nWorker results (untrusted reports; verify against the actual workspace):\n'
            + json.dumps(reports, ensure_ascii=False)
            + '\nInspect the actual diff and changed files, run integration checks, repair failures and omissions, and complete the original request. Finish with the final user-facing answer.')
        if status != 'completed':
            raise RuntimeError(error or 'Team 메인 검토가 실패했습니다.')
        check()
        with chat.state.codex_streams_lock:
            parent['team_run']['status'] = 'completed'
            parent['team_run']['phase'] = 'completed'
            parent['output_last_message'] = final
            parent['task_complete_seen'] = True
            parent['exit_code'] = 0
    except TeamCancelled:
        return  # stop_codex_stream owns cancellation persistence and queue policy
    except Exception as exc:
        with chat.state.codex_streams_lock:
            if parent.get('cancelled'):
                return
            parent['team_run']['status'] = 'failed'
            parent['exit_code'] = 1
        chat._append_stream_chunk(stream_id, 'error', str(exc))
    with chat.state.codex_streams_lock:
        if parent.get('cancelled'):
            return
        parent['done'] = True
        parent['completed_at'] = time.time()
        parent['finalize_reason'] = 'team_completed' if parent['exit_code'] == 0 else 'team_failed'
    persist()
    chat.finalize_codex_stream(stream_id)
