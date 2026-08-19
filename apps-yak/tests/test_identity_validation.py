"""Identity is validated at the actual access (ADR-23 Step 4 §2).

The catalog key is a discovery binding only. Whenever a component is
materialized the expected name is checked against the component's own
contract: the source's ``.yak/component.yml`` or the artifact's
``artifact.yml``. A mismatch fails loudly and unambiguously.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from conftest import artifact, make_source
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _mgr(root: Path, sources: list[str]) -> InstallationManager:
    ctx = Context(path=root, sources=sources)
    return InstallationManager(FileRepository(), DirectoryArtifactStore(), context=ctx)


@pytest.fixture(autouse=True)
def _no_pip(monkeypatch):
    from y5n.apps.yak.installer.installer import Installer

    monkeypatch.setattr(Installer, "install", lambda self, root, candidates: None)


def test_source_identity_mismatch_fails_loudly(tmp_path):
    """The catalog keys a name the component.yml does not declare."""
    src = tmp_path / "src"
    (src / "apps"/ "widget").mkdir(parents=True)
    (src / "apps" / "widget" / ".yak").mkdir(parents=True)
    (src / "apps" / "widget" / ".yak" / "component.yml").write_text(
        "name: other\nversion: 0.1.0\n"
    )
    make_source(src, {"acme-widget": "apps/widget"})

    mgr = _mgr(tmp_path, [])
    with pytest.raises(Exception, match="identity mismatch.*acme-widget.*other"):
        mgr.install(tmp_path / "inst", identity="acme-widget", paths=[str(src)])


def test_source_without_component_yml_fails_at_access(tmp_path):
    """A location without component.yml is discovered, but materializing it
    fails — the manifest must exist and declare the expected identity."""
    src = tmp_path / "src"
    (src / "widget").mkdir(parents=True)
    make_source(src, {"acme-widget": "widget"})
    (src / "widget" / ".yak" / "component.yml").unlink()

    mgr = _mgr(tmp_path, [])
    with pytest.raises(Exception, match="component.yml"):
        mgr.install(tmp_path / "inst", identity="acme-widget", paths=[str(src)])


def test_artifact_identity_mismatch_fails_loudly(monkeypatch, tmp_path):
    """An artifact whose artifact.yml does not declare the resolved name
    fails loudly — the release index entry must agree with the artifact."""
    src = tmp_path / "src"
    make_source(src, {"acme-widget": "widget"})

    mgr = _mgr(tmp_path, [str(src)])
    wrong = tmp_path / "wrong"
    artifact(wrong, "other", "/opt/x")
    monkeypatch.setattr(
        type(mgr), "_materialize_release", lambda self, catalog, name: wrong
    )

    with pytest.raises(Exception, match="identity mismatch.*acme-widget.*other"):
        mgr.install(tmp_path / "inst", identity="acme-widget")


def test_matching_identities_pass(monkeypatch, tmp_path):
    """A correct source and a correct artifact resolve without complaint."""
    src = tmp_path / "src"
    artifact(src / "artifacts" / "acme-widget", "acme-widget", "/opt/x")
    make_source(src, {"acme-widget": "artifacts/acme-widget"})

    mgr = _mgr(tmp_path, [str(src)])
    inst = mgr.install(tmp_path / "inst", identity="acme-widget")
    assert inst is not None
    record = next(c for c in inst.components if c.name == "acme-widget")
    assert record.mode == "artifact"