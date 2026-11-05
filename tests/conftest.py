"""Keep tests and their subprocesses away from the personal shared registry."""
import pytest


@pytest.fixture(autouse=True)
def isolate_shared_account_state(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_WORKBENCH_SHARED_ACCOUNT_STATE_DIR', str(tmp_path / 'shared-account-state'))
