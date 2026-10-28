"""The model's only filesystem capability: private text artifacts beneath /tmp.

Directory descriptors and O_NOFOLLOW prevent path traversal and symlink races.
No shell, arbitrary reads, recursive deletion, or execution is exposed.
"""
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile

TOOL_NAME = 'chat_artifact'
LIMIT = 1024 * 1024
TOOL = {'type': 'function', 'name': TOOL_NAME,
        'description': 'Create, replace, read or delete UTF-8 text artifacts in the private /tmp directory given in instructions. Paths are relative filenames, with optional subdirectories. Never executes files. No access to repositories or other local files.',
        'inputSchema': {'type': 'object', 'properties': {
            'operation': {'type': 'string', 'enum': ['write', 'read', 'delete']},
            'path': {'type': 'string'}, 'content': {'type': 'string'}},
            'required': ['operation', 'path'], 'additionalProperties': False}}


class Artifacts:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix='workbench-chat-', dir='/tmp'))
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self):
        os.close(self.fd)  # Keep the user's artifacts after the request finishes.

    def call(self, params):
        try:
            if params.get('tool') != TOOL_NAME or params.get('namespace') not in (None, 'functions'):
                raise ValueError('허용되지 않은 도구입니다.')
            args = params.get('arguments')
            if not isinstance(args, dict) or set(args) - {'operation', 'path', 'content'}:
                raise ValueError('산출물 요청 형식이 올바르지 않습니다.')
            operation, path = args.get('operation'), args.get('path')
            if operation not in ('write', 'read', 'delete') or not isinstance(path, str):
                raise ValueError('산출물 작업과 상대 경로가 필요합니다.')
            parts = path.split('/')
            if len(path) > 512 or len(parts) > 16 or any(p in ('', '.', '..') or '\x00' in p or '\\' in p for p in parts):
                raise ValueError('산출물은 전용 /tmp 디렉터리 안의 상대 경로만 허용합니다.')
            content = args.get('content', '')
            if not isinstance(content, str) or len(content.encode('utf-8')) > LIMIT:
                raise ValueError('텍스트 산출물은 1 MiB까지 허용합니다.')
            parent = os.dup(self.fd)
            try:
                for part in parts[:-1]:
                    if operation == 'write':
                        try:
                            os.mkdir(part, 0o700, dir_fd=parent)
                        except FileExistsError:
                            pass
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    os.close(parent)
                    parent = child
                name = parts[-1]
                try:
                    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    info = None
                if info and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                    raise ValueError('일반 산출물 파일만 허용합니다. 링크는 사용할 수 없습니다.')
                result = {'path': str(self.root / path), 'operation': operation}
                if operation == 'write':
                    temporary = '.artifact-' + secrets.token_hex(16)
                    try:
                        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                        with os.fdopen(fd, 'w', encoding='utf-8') as target:
                            target.write(content)
                        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                    finally:
                        try:
                            os.unlink(temporary, dir_fd=parent)
                        except FileNotFoundError:
                            pass
                elif operation == 'delete':
                    os.unlink(name, dir_fd=parent)
                else:
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                    with os.fdopen(fd, 'rb') as source:
                        info = os.fstat(source.fileno())
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                            raise ValueError('일반 산출물 파일만 읽을 수 있습니다.')
                        data = source.read(LIMIT + 1)
                    if len(data) > LIMIT:
                        raise ValueError('파일 크기 제한을 초과했습니다.')
                    result['content'] = data.decode('utf-8')
            finally:
                os.close(parent)
            return {'success': True, 'contentItems': [{'type': 'inputText', 'text': json.dumps(result, ensure_ascii=False)}]}
        except (ValueError, OSError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else '산출물 경로가 없거나 접근이 차단되었습니다.'
            return {'success': False, 'contentItems': [{'type': 'inputText', 'text': message}]}
