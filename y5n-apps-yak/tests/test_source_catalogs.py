"""Source resolution tests (ADR-20): --from exclusivity and misses."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from conftest import artifact as make_artifact
from conftest import make_source
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _mgr(ctx: Context) -> InstallationManager:
    return InstallationManager(FileRepository(), DirectoryArtifactStore(), context=ctx)


@pytest.mark.slow
def test_h_from_is_exclusive():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        official = root / "official"
        make_artifact(official / "cool-art", "cool-shell", "/opt/official")
        make_source(
            official,
            {"cool-shell": {"location": "cool-art", "release": "cool-art"}},
        )
        acme = root / "acme"
        make_artifact(acme / "cool-art", "cool-shell", "/opt/acme")
        make_source(
            acme,
            {"cool-shell": {"location": "cool-art", "release": "cool-art"}},
        )

        ctx = Context(path=root, sources=[str(official)])
        mgr = _mgr(ctx)
        inst = mgr.install(root / "inst")

        # --from acme: only acme is consulted, its artifact wins.
        mgr.add("cool-shell", inst.root, from_source=str(acme))
        state = mgr.load(inst.root)
        assert state is not None
        record = next(c for c in state.components if c.name == "cool-shell")
        assert record.mount == "/opt/acme"


@pytest.mark.slow
def test_i_from_miss_is_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        official = root / "official"
        make_artifact(official / "foo-art", "foo", "/opt/foo")
        make_source(official, {"foo": {"location": "foo-art"}})
        acme = root / "acme"
        make_source(acme, {"other": {"location": "other-art"}})

        ctx = Context(path=root, sources=[str(official)])
        mgr = _mgr(ctx)
        inst = mgr.install(root / "inst")

        with pytest.raises(ValueError, match="Unknown component"):
            mgr.add("foo", inst.root, from_source=str(acme))
