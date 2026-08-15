"""Language-neutrality contract: a component without a Python package.

A non-Python artifact (no wheel, no pip) materializes its structure
through the normal install path. Nothing is installed into a venv — the
installer is a no-op, so no venv/pip is created.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from conftest import make_source
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository


def _dotnet_artifact(staging: Path) -> Path:
    store = staging / "acme-test-1.0.0.dotnet.artifact"
    (store / "structure" / ".yak").mkdir(parents=True)
    (store / "structure" / ".yak" / "yak.yml").write_text(
        "title: Acme\n"
        "resolvable: false\n"
        "navigable: true\n"
        "contextual: false\n"
        "expose: true\n"
    )
    (store / "structure" / "hello" / ".yak").mkdir(parents=True)
    (store / "structure" / "hello" / ".yak" / "yak.yml").write_text(
        "title: Acme Hello\n"
        "resolvable: true\n"
        "navigable: false\n"
        "contextual: false\n"
        "host: /boot/dotnet/runtime\n"
        "entry:\n"
        "  run: acme.hello:main\n"
    )
    (store / "payload").mkdir()
    (store / "payload" / "acme-test").write_text("#!/bin/sh\necho hello\n")
    (store / "artifact.yml").write_text(
        "name: acme-test\n"
        "version: 1.0.0\n"
        "kind: package\n"
        "builder: dotnet\n"
        "host: dotnet\n"
        "mount: /opt/acme\n"
        "fingerprint: sha256:xyz\n"
    )
    return store


def test_non_python_component_materializes_structure(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        _dotnet_artifact(repo / "artifacts")
        make_source(
            repo,
            {
                "acme-test": {
                    "location": "acme-test-1.0.0.dotnet.artifact",
                }
            },
            bundles={"app": ["acme-test"]},
        )
        ctx = Context(path=root, sources=[str(repo)])
        mgr = InstallationManager(
            FileRepository(), DirectoryArtifactStore(), context=ctx
        )
        # No venv/pip: a non-Python component has no Python candidate.
        monkeypatch.setattr(
            type(mgr._installer), "install", lambda self, root, candidates: None
        )

        inst = mgr.install(root / "inst", identity="app")
        assert inst is not None

        staged = inst.root / ".yak" / "components" / "acme-test" / "structure"
        assert staged.is_dir() and not staged.is_symlink()
        assert (staged / "hello" / ".yak" / "yak.yml").exists()

        ws = inst.root / "structure" / "opt" / "acme"
        assert ws.is_symlink()
        assert (ws / "hello").exists()

        record = next(
            c for c in mgr.load(inst.root).components if c.name == "acme-test"
        )
        assert record.mode == "artifact"
        assert record.package == ""
