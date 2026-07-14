"""Test harness for imperal-ext-notifications. The tools only talk to the
gateway over HTTP (httpx), so tests respx-mock the three gateway GETs +
PATCH — no SDK stub client needed."""
import os
import sys
from types import SimpleNamespace

# Make the ext modules importable (they use bare `import app`, `from app import …`)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
# Make `conftest` importable by name from test modules (`from conftest import …`)
# even though tests/ is a package (tests/__init__.py) under pytest's prepend mode.
sys.path.insert(0, os.path.dirname(__file__))


def make_ctx(imperal_id: str = "imp_u_TEST"):
    """Minimal ctx stand-in: only ctx.user.imperal_id is used by app.py/handlers.py."""
    user = SimpleNamespace(imperal_id=imperal_id)
    return SimpleNamespace(user=user)


class Empty:
    """Stand-in for params when the real EmptyParams model isn't imported yet."""
    pass
