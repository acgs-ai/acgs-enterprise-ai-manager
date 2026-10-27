"""
The frontend must only call API paths that exist in the RBAC route policy.

RBACMiddleware answers 403 for any /api/v1 path that does not exactly match a
route (no trailing-slash redirect), so a frontend call such as
apiClient.get('/tasks') would silently break. This test keeps both sides in sync.
"""

import re
from pathlib import Path

import pytest

from backend.auth.policy import ROUTE_POLICY

pytestmark = pytest.mark.integration

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
API_PREFIX = "/api/v1"
CALL_RE = re.compile(r"apiClient\.(get|post|put|delete)\(\s*(['`])(.*?)\2")


def _template_regex(template: str) -> re.Pattern:
    parts = re.split(r"(\{[^}]+\})", template)
    return re.compile(
        "".join("[^/]+" if p.startswith("{") else re.escape(p) for p in parts) + "$"
    )


def _frontend_calls():
    calls = []
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if path.suffix not in (".vue", ".js") or ".test." in path.name:
            continue
        for method, _, url in CALL_RE.findall(path.read_text()):
            concrete = re.sub(r"\$\{[^}]+\}", "x", url.split("?")[0])
            calls.append((path.relative_to(FRONTEND_SRC), method.upper(), concrete))
    return calls


def test_frontend_has_api_calls_to_check():
    assert len(_frontend_calls()) >= 20


@pytest.mark.parametrize("source,method,url", _frontend_calls())
def test_frontend_call_matches_a_policy_route(source, method, url):
    full = API_PREFIX + url
    matches = [
        template
        for (m, template) in ROUTE_POLICY
        if m == method and _template_regex(template).match(full)
    ]
    assert matches, f"{source}: {method} {full} matches no route in ROUTE_POLICY"
