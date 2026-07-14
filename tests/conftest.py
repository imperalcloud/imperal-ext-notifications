"""Test harness for imperal-ext-notifications. The tools only talk to the
gateway over HTTP (httpx), so tests respx-mock the three gateway GETs +
PATCH — no SDK stub client needed."""
import os
import sys
from types import SimpleNamespace

import pytest

# Make the ext modules importable (they use bare `import app`, `from app import …`).
# MUST run before any test module does `import app` / `import handlers` / `import panels`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def make_ctx():
    """Factory fixture: minimal ctx stand-in — only ctx.user.imperal_id is used
    by app.py/handlers.py. Auto-discovered by pytest (no cross-module import),
    so it is portable regardless of pytest rootdir / import-mode / how the
    validation host invokes pytest."""
    def _make(imperal_id: str = "imp_u_TEST"):
        user = SimpleNamespace(imperal_id=imperal_id)
        return SimpleNamespace(user=user)
    return _make
