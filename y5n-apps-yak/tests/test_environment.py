"""Tests for environment module — models, io, sync."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.environment.io import env_path, from_template, load, save
from y5n.apps.yak.environment.models import Environment
from y5n.apps.yak.environment.sync import add_mount
from y5n.apps.yak.pack.models import Mount, PackName


class TestEnvironmentModels:
    def test_environment_defaults(self):
        env = Environment(name="dev")
        assert env.schema == "1"
        assert env.dependencies == []
        assert env.mounts == []

    def test_environment_with_mounts(self):
        mounts = [Mount(source="/path/to/demo", target="/demo")]
        env = Environment(name="test", mounts=mounts)
        assert len(env.mounts) == 1
        assert env.mounts[0].source == "/path/to/demo"


class TestEnvironmentIO:
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mounts = [Mount(source="/path/to/system", target="/usr/bin")]
            deps = [PackName("y5n-packs-system")]
            env = Environment(
                name="dev",
                dependencies=deps,
                mounts=mounts,
            )
            save(env, root)

            loaded = load(root)
            assert loaded is not None
            assert loaded.name == "dev"
            assert loaded.schema == "1"
            assert loaded.dependencies == deps
            assert len(loaded.mounts) == 1
            assert loaded.mounts[0].source == "/path/to/system"
            assert loaded.mounts[0].target == "/usr/bin"

    def test_load_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assert load(root) is None

    def test_env_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assert env_path(root) == root / ".yak" / "environment.yml"

    def test_from_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "dev.yml"
            template.write_text("""\
name: dev
dependencies:
  - y5n-packs-root
  - y5n-packs-system
workspace:
  path: workspace/structure
  mounts:
    - pack: root
      target: /
    - pack: system
      target: /usr/bin
""")
            env = from_template(template)
            assert env.name == "dev"
            assert env.dependencies == [
                PackName("y5n-packs-root"),
                PackName("y5n-packs-system"),
            ]
            assert len(env.mounts) == 2
            assert env.mounts[0].source == "root"
            assert env.mounts[0].target == "/"

    def test_from_template_minimal(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "minimal.yml"
            template.write_text("name: minimal\n")
            env = from_template(template)
            assert env.name == "minimal"
            assert env.dependencies == []
            assert env.mounts == []


class TestEnvironmentSync:
    def test_add_mount_new(self):
        env = Environment(name="test")
        result = add_mount(env, "/path/to/demo", "/demo")
        assert result.source == "/path/to/demo"
        assert result.target == "/demo"
        assert len(env.mounts) == 1

    def test_add_mount_existing(self):
        mount = Mount(source="/path/to/demo", target="/custom")
        env = Environment(name="test", mounts=[mount])
        result = add_mount(env, "/path/to/demo", "/custom")
        assert result is mount
        assert result.target == "/custom"
        assert len(env.mounts) == 1
