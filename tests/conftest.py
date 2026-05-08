import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def runtime_path() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "skills" / "shared" / "session_absorb_core.py"


@pytest.fixture(scope="session")
def run_runtime(runtime_path):
    def _run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, str(runtime_path), *args],
            capture_output=True,
            text=True,
            env=merged_env,
            check=False,
        )
    return _run
