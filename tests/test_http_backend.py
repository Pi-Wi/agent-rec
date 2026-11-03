"""The client library must match the SDK it is handed to.

A mismatch fails the moment a user passes ``http_client=`` to an SDK, so these
pin the selection rule and that the public facade really uses the chosen library.
"""
import subprocess
import sys

import agentrec
from agentrec._http import BACKEND, httpx


def _backend_with(env_value):
    code = "from agentrec._http import BACKEND; print(BACKEND)"
    env = {"AGENTREC_HTTP_BACKEND": env_value, "PATH": ""}
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )


def test_facade_clients_use_the_resolved_backend():
    assert isinstance(agentrec.async_client(), httpx.AsyncClient)
    assert isinstance(agentrec.sync_client(), httpx.Client)


def test_httpx2_wins_when_installed():
    try:
        import httpx2  # noqa: F401
    except ImportError:
        assert BACKEND == "httpx"
    else:
        assert BACKEND == "httpx2"


def test_explicit_override_selects_httpx():
    result = _backend_with("httpx")
    assert result.stdout.strip() == "httpx", result.stderr


def test_unknown_override_fails_loudly():
    result = _backend_with("requests")
    assert result.returncode != 0
    assert "AGENTREC_HTTP_BACKEND" in result.stderr
