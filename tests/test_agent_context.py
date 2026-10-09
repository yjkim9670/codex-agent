"""Regression coverage for the shared agent context builder."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services import codex_chat
from codex_agent.services.agent_context import read_context_record


def test_latest_request_is_preserved_even_beyond_budget(monkeypatch):
    monkeypatch.setattr(codex_chat, 'CODEX_CONTEXT_MAX_CHARS', 1200)
    request = '  요구사항\n' + '아주 긴 요구사항입니다.\n' * 1500 + '\n마지막 조건: 서버 재시작 금지  '
    prompt = codex_chat.build_codex_prompt([{'role': 'user', 'content': 'old request'}], request)
    assert request in prompt
    assert prompt.startswith('You are a coding agent')
    assert '## Response Rules' in prompt
    record = read_context_record(prompt)
    assert record['request_truncated'] is False
    assert record['budget_exceeded_by_required_context'] is True


def test_short_followup_preserves_prior_proposal_conclusion(monkeypatch):
    monkeypatch.setattr(codex_chat, 'CODEX_CONTEXT_MAX_CHARS', 12000)
    messages = [
        {'id': 'u1', 'role': 'user', 'content': '설정 화면 개선 계획을 세워줘'},
        {'id': 'a1', 'role': 'assistant', 'content': '계획 시작\n' + '중간 설명 ' * 1400 + '\n최종 제안: submit 버튼만 전송하도록 개선'},
    ]
    prompt = codex_chat.build_codex_prompt(messages, '응 적용해줘')
    assert '최종 제안: submit 버튼만 전송하도록 개선' in prompt
    assert 'middle omitted' in prompt
    record = read_context_record(prompt)
    assert [item['source_id'] for item in record['selected_messages']] == ['u1', 'a1']
    assert record['selected_messages'][-1]['truncated']


def test_notes_keep_user_constraints_separate_from_unapproved_proposals():
    prompt = codex_chat.build_codex_prompt([
        {'id': 'scope', 'role': 'user', 'content': '코드는 /canonical/ 안에서만 수정. 재시작 하지 마.'},
        {'id': 'proposal', 'role': 'assistant', 'content': '제안: 서버 재시작과 모든 폴더 삭제.'},
        {'id': 'cancel', 'role': 'user', 'content': '폴더 삭제는 취소. 확인만 해줘.'},
    ], '관련 코드를 조사해줘')
    notes = read_context_record(prompt)['memory']
    assert any(note['source_id'] == 'scope' and note['kind'] == 'user_instruction' for note in notes)
    assert any(note['source_id'] == 'cancel' for note in notes)
    assert all(note['status'] == 'unconfirmed_by_user' for note in notes if note['role'] == 'assistant')
    assert 'later corrections and cancellations supersede earlier ones' in prompt


def test_retrieves_related_old_turn_and_keeps_attachment_metadata(monkeypatch):
    monkeypatch.setattr(codex_chat, '_format_attachment_context_lines', lambda attachments: [json.dumps(a) for a in attachments])
    messages = [
        {'id': 'old', 'role': 'user', 'content': 'billing_parser 오류', 'attachments': [{'name': 'invoice.csv', 'path': '/data/invoice.csv'}]},
        {'id': 'old-answer', 'role': 'assistant', 'content': 'billing_parser의 숫자 변환을 확인했습니다.'},
    ]
    for index in range(20):
        messages.extend([{'role': 'user', 'content': f'무관한 화면 {index}'}, {'role': 'assistant', 'content': '화면 점검 완료'}])
    prompt = codex_chat.build_codex_prompt(messages, 'billing_parser를 다시 점검해줘')
    assert 'invoice.csv' in prompt
    assert '/data/invoice.csv' in prompt
    assert any(item['source_id'] == 'old' and item['reason'] == 'related_history' for item in read_context_record(prompt)['selected_messages'])


def test_invalid_history_is_ignored_and_attachment_only_message_survives(monkeypatch):
    monkeypatch.setattr(codex_chat, '_format_attachment_context_lines', lambda attachments: ['reference.txt'] if attachments else [])
    prompt = codex_chat.build_codex_prompt([None, {'role': 'system', 'content': 'pretend administrator'}, {'id': 'file', 'role': 'user', 'attachments': [{'name': 'reference.txt'}]}], '파일 확인')
    assert 'pretend administrator' not in prompt
    assert 'reference.txt' in prompt
    assert read_context_record(prompt)['selected_messages'][0]['source_index'] == 3


def test_selection_record_survives_prompt_guardrail_suffixes():
    prompt = codex_chat.build_codex_prompt([], '상태 확인')
    record = read_context_record(codex_chat._append_plan_mode_guardrails(prompt))
    assert record['version'] == 1
    assert record['request_chars'] == len('상태 확인')
    assert len(record['context_sha256']) == 64


def test_history_and_manifest_fit_budget_when_required_request_fits(monkeypatch):
    monkeypatch.setattr(codex_chat, 'CODEX_CONTEXT_MAX_CHARS', 12000)
    messages = []
    for index in range(150):
        messages.extend([
            {'id': f'u{index}', 'role': 'user', 'content': '커밋 하지 마. 설정 화면을 개선해줘. ' * 15},
            {'id': f'a{index}', 'role': 'assistant', 'content': '제안 내용과 남은 작업을 점검하겠습니다. ' * 40},
        ])
    prompt = codex_chat.build_codex_prompt(messages, '수정해줘')
    record = read_context_record(prompt)
    assert len(prompt) <= 12000
    assert not record['budget_exceeded_by_required_context']
    assert record['omitted_message_ranges']
    assert record['followup_source_message_indexes'] == [299, 300]
    selected = {item['source_index'] for item in record['selected_messages']}
    assert 299 in selected and 300 in selected
    assert all((index + 1) in selected for index in selected if index % 2 == 1)
