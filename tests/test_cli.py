"""CLI surface tests for the non-async commands, fully offline.

Covers ``--version`` and the ``profiles`` discovery command (the migrate/report
paths are exercised by test_migration.py / test_pricing.py).
"""
from __future__ import annotations

import pytest

from agentrec import __version__
from agentrec.cli import main


def test_version_flag_prints_version_and_exits_zero(capsys):
    # argparse's version action raises SystemExit(0) after printing.
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_profiles_lists_builtin_profiles(capsys):
    assert main(["profiles"]) == 0
    out = capsys.readouterr().out
    # The three snapshots shipped as package data should all be discoverable.
    assert "anthropic-list" in out
    assert "openai-list" in out
    assert "mistral-list" in out
    # Discovery output is console-facing: ASCII-safe like render_console.
    assert out.isascii(), "profiles output must survive a Windows code page"
