"""yak bootstrap — the generic repo-name → checkout mapping (Punkt 2)."""

from __future__ import annotations

import pytest
from y5n.apps.yak.hosts.cli.commands.bootstrap import _to_local_checkout


def test_github_source_maps_to_local_checkout(tmp_path):
    (tmp_path / "runtime").mkdir()
    result = _to_local_checkout("github:yakoon-runtime/runtime", tmp_path)
    assert result == str(tmp_path / "runtime")


def test_github_source_uses_last_path_segment(tmp_path):
    (tmp_path / "pack-crm").mkdir()
    result = _to_local_checkout("github:yakoon-runtime/pack-crm", tmp_path)
    assert result == str(tmp_path / "pack-crm")


def test_non_github_source_passes_through(tmp_path):
    spec = "some/local/path"
    assert _to_local_checkout(spec, tmp_path) == spec


def test_missing_checkout_raises(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        _to_local_checkout("github:yakoon-runtime/runtime", tmp_path)
