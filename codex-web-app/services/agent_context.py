"""Deterministic, source-linked conversation context shared by all agent backends.

Extracted notes are evidence, not a semantic summary or an approval classifier.
"""
import hashlib
import json
import re

AUDIT_MARKER = '## Context Selection Record\n'
_POLICY = re.compile(
    r'only|must|never|do not|don.t|constraint|pending|todo|approve|cancel|instead|'
    r'금지|제약|범위|만 수정|만 해|만 변경|하지 마|하지마|확인만|그대로|유지|'
    r'재시작|커밋|승인|취소|미완료|남은|다음|계획|제안|수정해|개선해', re.I)


def _tokens(text):
    return set(re.findall(r'[a-z0-9_./-]{3,}|[가-힣]{2,}', text.lower()))


def _excerpt(text, limit):
    if len(text) <= limit:
        return text
    # Keep both the opening and the conclusion of a long proposal.
    head = (limit - 35) // 2
    return text[:head] + '\n[... middle omitted ...]\n' + text[-head:]


def read_context_record(prompt):
    if AUDIT_MARKER not in prompt:
        return None
    try:
        record, _ = json.JSONDecoder().raw_decode(prompt.rsplit(AUDIT_MARKER, 1)[1])
        if not isinstance(record, dict) or record.get('version') != 1:
            return None
        record['submitted_prompt_chars'] = len(prompt)
        record['submitted_prompt_sha256'] = hashlib.sha256(prompt.encode()).hexdigest()
        return record
    except (ValueError, TypeError):
        return None


def _omitted_ranges(entries, selected):
    ranges = []
    for entry in entries:
        index = entry['source_index']
        if index in selected:
            continue
        if ranges and ranges[-1][1] == index - 1:
            ranges[-1][1] = index
        else:
            ranges.append([index, index])
    return ranges


def extract_context_notes(entries):
    notes = []
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or entry.get('role') not in ('user', 'assistant'):
            continue
        if entry['role'] == 'error':
            continue
        for line in re.split(r'\n+|(?<=[.!?])\s+', str(entry.get('content') or '')):
            if not _POLICY.search(line):
                continue
            notes.append({
                'source_index': entry.get('source_index', index), 'source_id': entry.get('id'),
                'role': entry['role'],
                'kind': 'user_instruction' if entry['role'] == 'user' else 'proposal_or_status',
                'status': 'requires_chronological_review' if entry['role'] == 'user' else 'unconfirmed_by_user',
                'text': line,
            })

    return notes


def build_context(messages, request, budget, compose, format_message):
    entries = []
    for index, message in enumerate(messages, 1):
        if not isinstance(message, dict):
            continue
        role = str(message.get('role') or 'user').lower()
        if role not in ('user', 'assistant', 'error'):
            continue
        content = str(message.get('content') or '')
        attachments = message.get('attachments') or []
        if not content.strip() and not attachments:
            continue
        entries.append(dict(message, role=role, content=content, source_index=index))

    # Keep request bytes intact; the history budget is soft when mandatory text
    # alone exceeds it. Never slice the final prompt or its framing.
    mandatory = compose([], [], request)
    available = max(0, budget - len(mandatory) - 600)
    turns = []
    for entry in entries:
        if entry['role'] == 'user' or not turns:
            turns.append([])
        turns[-1].append(entry)

    notes = extract_context_notes(entries)

    note_lines = []
    included_notes = []
    note_budget = int(available * .30)
    # User constraints take precedence over assistant proposals.
    priority_notes = sorted(notes, key=lambda note: (note['role'] == 'user', note['source_index']), reverse=True)
    for note in priority_notes:
        line = json.dumps(note, ensure_ascii=False)
        if len(line) + sum(len(item) + 3 for item in note_lines) > note_budget:
            continue
        note_lines.insert(0, line)
        included_notes.insert(0, note)

    included_notes.sort(key=lambda note: note['source_index'])
    note_lines = [json.dumps(note, ensure_ascii=False) for note in included_notes]
    selected = {}
    selections = []
    used = sum(len(line) + 3 for line in note_lines)

    def add_turn(turn, reason, limit):
        nonlocal used
        fresh = [entry for entry in turn if entry['source_index'] not in selected]
        blocks = [(entry, format_message(dict(entry, content=_excerpt(entry['content'], limit)),
                                         entry['source_index'], max_chars=limit)) for entry in fresh]
        cost = sum(len(block) + 1 for _, block in blocks)
        if used + cost > available:
            return False
        for entry, block in blocks:
            selected[entry['source_index']] = block
            selections.append({'source_index': entry['source_index'], 'source_id': entry.get('id'),
                               'reason': reason, 'truncated': len(entry['content']) > limit,
                               'attachment_count': len(entry.get('attachments') or [])})
        used += cost
        return True

    # Reserve the immediate request/answer pair before filling older context.
    if turns:
        if not add_turn(turns[-1], 'latest_turn', max(1400, int(available * .55))):
            add_turn(turns[-1], 'latest_turn', 500)
    query = _tokens(request)
    # Short approvals inherit topic vocabulary from the preceding turn.
    if len(request.strip()) < 80 and turns:
        query |= _tokens(' '.join(entry['content'] for entry in turns[-1]))
    ranked = sorted(turns[:-1], key=lambda turn: (
        len(query & _tokens(' '.join(entry['content'] + ' ' + json.dumps(entry.get('attachments') or [], ensure_ascii=False) for entry in turn))),
        turn[-1]['source_index']), reverse=True)
    retrieval_budget = used + int(max(0, available - used) * .50)
    for turn in ranked:
        score = len(query & _tokens(' '.join(entry['content'] + ' ' + json.dumps(entry.get('attachments') or [], ensure_ascii=False) for entry in turn)))
        if score and used < retrieval_budget:
            add_turn(turn, 'related_history', 1000)
    for turn in reversed(turns[:-1]):
        add_turn(turn, 'recent_turn', 1400)

    def render():
        return compose(note_lines, [selected[index] for index in sorted(selected)], request)

    result = render()
    record = {
        'version': 1, 'strategy': 'source_linked_turns_and_lexical_retrieval',
        'budget_chars': budget, 'budget_unit': 'characters',
        'request_chars': len(request), 'request_truncated': False,
        'followup_source_message_indexes': [entry['source_index'] for entry in turns[-1]] if turns and len(request.strip()) < 80 else [],
        'selected_messages': sorted(selections, key=lambda item: item['source_index']),
        'omitted_message_ranges': _omitted_ranges(entries, selected),
        'omitted_message_count': len(entries) - len(selected),
        'memory': included_notes, 'memory_candidate_count': len(notes),
        'omitted_memory_count': len(notes) - len(included_notes),
        'instructions': re.findall(r'^## (.+)$', result, re.M),
    }
    # Persist the manifest on the assistant message in the existing session
    # store. Retrieval never crosses sessions or users.
    def audit_text():
        compact = dict(record)
        return AUDIT_MARKER + json.dumps(compact, ensure_ascii=False, separators=(',', ':'))

    record['context_sha256'] = '0' * 64
    record['budget_exceeded_by_required_context'] = False
    # Manifest overhead also counts against the soft history budget.
    while len(result) + len(audit_text()) + 2 > budget and (selected or note_lines):
        removable = sorted((item for item in selections if item['reason'] != 'latest_turn'),
                           key=lambda item: (item['reason'] != 'recent_turn', item['source_index']))
        if removable:
            index = removable[0]['source_index']
            # Remove the complete turn, never leave a detached assistant answer.
            turn = next(turn for turn in turns if any(e['source_index'] == index for e in turn))
            for entry in turn:
                selected.pop(entry['source_index'], None)
            selections[:] = [item for item in selections if item['source_index'] in selected]
        elif note_lines:
            note_index = next((index for index, note in enumerate(included_notes)
                               if note['role'] == 'assistant'), 0)
            note_lines.pop(note_index)
            included_notes.pop(note_index)
        else:
            selected.clear()
            selections.clear()
        record['selected_messages'] = sorted(selections, key=lambda item: item['source_index'])
        record['omitted_message_ranges'] = _omitted_ranges(entries, selected)
        record['omitted_message_count'] = len(entries) - len(selected)
        record['omitted_memory_count'] = len(notes) - len(included_notes)
        result = render()
        record['instructions'] = re.findall(r'^## (.+)$', result, re.M)
    record['context_sha256'] = hashlib.sha256(result.encode()).hexdigest()
    record['budget_exceeded_by_required_context'] = len(result) + len(audit_text()) + 2 > budget
    # The manifest accompanies the prompt through all backend-specific wrappers.
    result += '\n\n' + audit_text()
    return result, record
