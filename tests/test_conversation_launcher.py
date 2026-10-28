"""Exercise the actual launcher with Proc Manager's modified HOME."""
import os
from pathlib import Path
import subprocess
import sys


def test_launcher_loads_dependencies_without_inherited_pythonpath(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONUSERBASE', 'PYTHONNOUSERSITE'):
        env.pop(key, None)
    env.update(HOME=str(tmp_path), CHAT_PYTHON_BIN=sys.executable,
               CHAT_DATA_DIR=str(tmp_path / 'chat'))
    result = subprocess.run(
        ['/bin/bash', str(root / 'run_conversation_server.sh'), '--help'],
        env=env, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert 'Workbench Chat' in result.stdout
    assert not (tmp_path / 'chat').exists()
