"""The version invariant: one version through every station.

``pyproject.version`` == wheel METADATA == ArtifactInfo == artifact.yml
== artifact dir name == release tag == resolved artifact. No second
manifest may relabel the builder's result — a decoy pack.toml is ignored.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from y5n.apps.yak.builder.python import PythonBuildProvider
from y5n.apps.yak.cap.models import read_mount
from y5n.apps.yak.resolver.artifact import DirectorySource
from y5n.apps.yak.resolver.github import release_tag_for

from conftest import _write_wheel


def test_one_version_through_the_whole_chain():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        name, version = "acme-pack", "0.8.0"

        # A native project with its own manifest.
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
        (project / ".yak" / "mount.yml").write_text("path: /opt/acme\n")

        builder = PythonBuildProvider()

        # 1. The wheel carries the native version.
        dist = project / "dist"
        dist.mkdir()
        _write_wheel(dist, name, version, ())
        wheel = next(dist.glob("*.whl"))

        # 2. The builder reads it back without relabeling.
        info = builder._parse_wheel(wheel)
        assert info.name == name
        assert info.version == version

        # 3. The artifact dir name is built from the same version.
        assert info.filename == f"{name}-{version}.python.artifact"

        # 4. The artifact manifest records the same version + mount.
        info.mount = read_mount(project)
        artifact_dir = root / info.filename
        artifact_dir.mkdir()
        (artifact_dir / "artifact.yml").write_text(info.to_yml())
        yml = (artifact_dir / "artifact.yml").read_text()
        assert f"version: {version}" in yml
        assert "mount: /opt/acme" in yml

        # 5. The release tag derives from the artifact dir name.
        assert release_tag_for(name, artifact_dir) == f"{name}-v{version}"

        # 6. Resolution reports the same version.
        resolved = DirectorySource(root).resolve(name)
        assert resolved is not None
        assert resolved.version == version
        assert resolved.mount == "/opt/acme"


def test_mount_is_optional():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        name, version = "plain-lib", "0.1.0"
        project = root / name
        project.mkdir()
        (project / "pyproject.toml").write_text(
            "[project]\n"
            f'name = "{name}"\n'
            f'version = "{version}"\n'
        )
        builder = PythonBuildProvider()
        dist = project / "dist"
        dist.mkdir()
        _write_wheel(dist, name, version, ())
        wheel = next(dist.glob("*.whl"))
        info = builder._parse_wheel(wheel)
        assert info.mount is None
        assert release_tag_for(name, root / info.filename) == f"{name}-v{version}"
