"""Conservative, deterministic routing decisions for Economy execution.

These rules are signals, not a security boundary. Callers must also inspect
the actual workspace and handle unavailable observations as inconclusive.
"""
import fnmatch
import re


_HIGH_RISK_REQUEST = re.compile(
    r'\b(?:authentication|authorization|permissions?|migration|public\s+api|'
    r'rtl\s+interface|schema\s+change)\b|인증|권한|마이그레이션|공용\s*api|'
    r'공개\s*api|rtl\s*인터페이스', re.IGNORECASE)

DEFAULT_REVIEW_PATHS = (
    '**/migrations/**', 'migrations/**', '**/auth/**', 'auth/**',
    '**/api/**', 'api/**', '**/*.sv', '**/*.v', '*.sv', '*.v',
)


def initial_route(request):
    """Return the initial role and an explanatory reason without a model call."""
    if _HIGH_RISK_REQUEST.search(str(request or '')):
        return 'main', '고위험 요청 신호'
    return 'secondary', '일반 요청'


def review_reasons(*, cli_ok, report, observed_failures, changed_files,
                   workspace_error=None, review_paths=DEFAULT_REVIEW_PATHS):
    """Collect reasons to request main review; a worker report is untrusted.

    Skipped or missing checks are inconclusive and require review.
    """
    reasons = []
    if not cli_ok:
        reasons.append('세컨더리 실행 실패')
    if not isinstance(report, dict) or report.get('status') != 'completed':
        reasons.append('완료 보고가 없거나 실패함')
    checks = report.get('validation') if isinstance(report, dict) else None
    if not isinstance(checks, list) or not checks or any(
            not isinstance(check, dict) or check.get('status') != 'passed'
            or type(check.get('exit_code')) is not int or check['exit_code'] != 0
            or not isinstance(check.get('command'), str) or not check['command'].strip()
            for check in checks):
        reasons.append('검증 결과가 없거나 통과하지 못함')
    if observed_failures:
        reasons.append('실제로 관측된 검증 실패')
    if workspace_error or changed_files is None:
        reasons.append('작업공간 변경을 확인할 수 없음')
    elif any(fnmatch.fnmatchcase(path.replace('\\', '/'), pattern)
             for path in changed_files for pattern in review_paths):
        reasons.append('검토 대상 파일 변경')
    return reasons
