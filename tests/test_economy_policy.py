"""Economy routing decisions do not require model calls."""
import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    'economy_policy', Path(__file__).resolve().parents[1]
    / 'codex-web-app/services/economy_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def test_initial_routing():
    assert policy.initial_route('Update the button label')[0] == 'secondary'
    assert policy.initial_route('공용 API 권한 변경')[0] == 'main'
    assert policy.initial_route('Change the RTL interface')[0] == 'main'


def test_review_uses_observations_not_only_success_report():
    report = {'status': 'completed', 'validation': [
        {'command': 'pytest', 'status': 'passed', 'exit_code': 0}]}
    def decide(**changes):
        args = dict(cli_ok=True, report=report, observed_failures=[], changed_files=['src/ui.py'])
        args.update(changes)
        return policy.review_reasons(**args)
    assert decide() == []
    assert decide(changed_files=['rtl/core.sv'])
    assert decide(observed_failures=['pytest failed'])
    assert decide(changed_files=None)
    assert decide(report={'status': 'completed', 'validation': []})
    assert decide(cli_ok=False)
