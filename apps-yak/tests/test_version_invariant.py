"""The identity invariant: one identity through every station, claimed at
``.yak/component.yml``.

``.yak/component.yml`` declares name and version (ADR-23). The native
build's wheel METADATA must prove that declaration — the builder may not
relabel it. From the verified ArtifactInfo the chain keeps running:
artifact.yml == artifact dir name == release tag == resolved artifact.
A decoy pack.toml stays irrelevant.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from y5n.apps.yak.builder.python import PythonBuildProvider
from y5n.apps.yak.builder.protocol import IdentityMismatchError
from y5n.apps.yak.cap.models import read_component, read_mount
from y5n.apps.yak.resolver.artifact import DirectorySource
from y5n.apps.yak.resolver.github import release_tag_for

from conftest import _write_wheel


def _project(root: Path, name: str, version: str, mount: str) -> Path:
    """A native project with its Yakoon contract (component.yml)."""
    project = root / name
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}"\n'
        f'version = "{version}"\n'
    )
    # A stale pack manifest must be irrelevant (regression guard).
    (project / "pack.toml").write_text(
        f'name = "{name}"\nversion = "0.1.0"\n'
    )
    (project / ".yak").mkdir()
    (project / ".yak" / "component.yml").write_text(
        f"name: {name}\nversion: {version}\n"
    )
    (project / ".yak" / "mount.yml").write_text(
        f"source: structure\npath: {mount}\n"
    )
    return project


def _wheel_for(project: Path, name: str, version: str) -> Path:
    dist = project / "dist"
    dist.mkdir(exist_ok=True)
    _write_wheel(dist, name, version, ())
    return next(dist.glob("*.whl"))


def test_identity_through_the_whole_chain_starts_at_component_yml():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        name, version = "acme-pack", "0.8.0"
        project = _project(root, name, version, "/opt/acme")

        # 1. The declared identity comes from .yak/component.yml.
        expected = read_component(project)
        assert expected is not None
        assert expected.name == name
        assert expected.version == version

        builder = PythonBuildProvider()

        # 2. The wheel carries the same identity and the builder verifies it.
        wheel = _wheel_for(project, name, version)
        info = builder._parse_wheel(wheel)
        assert info is not None
        builder._validate(expected, info)
        assert info.name == name
        assert info.version == version

        # 3. The artifact dir name is built from the same identity.
        assert info.filename == f"{name}-{version}.python.artifact"

        # 4. The artifact manifest records the same identity + mount.
        info.mount = read_mount(project)
        artifact_dir = root / info.filename
        artifact_dir.mkdir()
        (artifact_dir / "artifact.yml").write_text(info.to_yml())
        yml = (artifact_dir / "artifact.yml").read_text()
        assert f"version: {version}" in yml
        assert "mount:" in yml
        assert "path: /opt/acme" in yml
        assert "source: structure" in yml

        # 5. The release tag derives from the artifact dir name.
        assert release_tag_for(name, artifact_dir) == f"{name}-v{version}"

        # 6. Resolution reports the same identity.
        resolved = DirectorySource(root).resolve(name)
        assert resolved is not None
        assert resolved.version == version
        assert resolved.mount == "/opt/acme"


def test_version_mismatch_fails_the_build():
    """component.yml declares 0.9.0, the wheel proves 0.8.0 → build error."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        name, declared = "acme-pack", "0.9.0"
        project = _project(root, name, declared, "/opt/acme")
        # The native metadata disagrees with the declaration.
        (project / "pyproject.toml").write_text(
            "[project]\n"
            f'name = "{name}"\n'
            'version = "0.8.0"\n'
        )

        builder = PythonBuildProvider()
        wheel = _wheel_for(project, name, "0.8.0")
        info = builder._parse_wheel(wheel)
        assert info is not None

        expected = read_component(project)
        assert expected is not None
        with pytest.raises(IdentityMismatchError, match="0.8.0"):
            builder._validate(expected, info)


def test_name_mismatch_fails_the_build():
    """component.yml declares a name the wheel does not prove → build error."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        name, version = "acme-pack", "0.1.0"
        project = _project(root, name, version, "/opt/acme")
        # The native metadata disagrees with the declaration.
        (project / "pyproject.toml").write_text(
            "[project]\n"
            'name = "acme-widget"\n'
            f'version = "{version}"\n'
        )

        builder = PythonBuildProvider()
        wheel = _wheel_for(project, "acme-widget", version)
        info = builder._parse_wheel(wheel)
        assert info is not None

        expected = read_component(project)
        assert expected is not None
        with pytest.raises(IdentityMismatchError, match="acme-widget"):
            builder._validate(expected, info)


def test_mount_is_optional():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        name, version = "plain-lib", "0.1.0"
        project = _project(root, name, version, "/opt/acme")
        # No mount directory → no mount.yml.
        (project / ".yak" / "mount.yml").unlink()

        builder = PythonBuildProvider()
        expected = read_component(project)
        assert expected is not None and expected.mount is None
        # A component without a mount delivers nothing into the tree.
        wheel = _wheel_for(project, name, version)
        info = builder._parse_wheel(wheel)
        assert info is not None
        assert info.mount is None
        assert release_tag_for(name, root / info.filename) == f"{name}-v{version}"


def test_mount_without_source_or_path_fails_loudly(tmp_path):
    """mount.yml that exists must declare source AND path — no magic."""
    from y5n.apps.yak.cap.models import MountError, read_mount

    project = _project(tmp_path, "acme-c", "0.1.0", "/opt/acme")
    (project / ".yak" / "mount.yml").write_text("path: /opt/acme\n")
    with pytest.raises(MountError, match="source"):
        read_mount(project)

    (project / ".yak" / "mount.yml").write_text("source: structure\n")
    with pytest.raises(MountError, match="path"):
        read_mount(project)


def test_mount_source_is_used_by_the_resolver(tmp_path):
    """The mount source (not a hard-coded name) selects the delivered tree."""
    from conftest import make_source
    from y5n.apps.yak.hosts.cli.cwd import Context
    from y5n.apps.yak.installation.manager import InstallationManager
    from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
    from y5n.apps.yak.repository.file_repo import FileRepository

    src = tmp_path / "src"
    cap = src / "acme-tool"
    (cap / "deploy" / "bin").mkdir(parents=True)
    (cap / "deploy" / "bin" / "hello.txt").write_text("deployed")
    (cap / "pyproject.toml").write_text(
        "[project]\nname = 'acme-tool'\nversion = '0.1.0'\n"
    )
    (cap / ".yak").mkdir(parents=True)
    (cap / ".yak" / "component.yml").write_text(
        "name: acme-tool\nversion: 0.1.0\n"
    )
    (cap / ".yak" / "mount.yml").write_text(
        "source: deploy/bin\npath: /usr/lib/acme\n"
    )
    make_source(src, {"acme-tool": "acme-tool"})

    mgr = InstallationManager(
        FileRepository(),
        DirectoryArtifactStore(),
        context=Context(path=tmp_path, sources=[str(src)]),
    )
    catalog, ref = mgr._index().resolve("acme-tool")
    component = mgr._component_from_ref("acme-tool", catalog, ref, mode="source")
    assert component.structure is not None
    assert component.structure.name == "bin"
    assert (component.structure / "hello.txt").read_text() == "deployed"


def test_mount_source_missing_raises_loudly(tmp_path):
    """A declared mount source that does not exist is a broken component."""
    from conftest import make_source
    from y5n.apps.yak.hosts.cli.cwd import Context
    from y5n.apps.yak.installation.manager import InstallationManager
    from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
    from y5n.apps.yak.repository.file_repo import FileRepository

    src = tmp_path / "src"
    cap = src / "acme-tool"
    (cap / ".yak").mkdir(parents=True)
    (cap / ".yak" / "component.yml").write_text(
        "name: acme-tool\nversion: 0.1.0\n"
    )
    (cap / ".yak" / "mount.yml").write_text(
        "source: does/not/exist\npath: /usr/lib/acme\n"
    )
    make_source(src, {"acme-tool": "acme-tool"})

    mgr = InstallationManager(
        FileRepository(),
        DirectoryArtifactStore(),
        context=Context(path=tmp_path, sources=[str(src)]),
    )
    catalog, ref = mgr._index().resolve("acme-tool")
    with pytest.raises(Exception, match="does/not/exist"):
        mgr._component_from_ref("acme-tool", catalog, ref, mode="source")