"""Tests for environment module — models, io."""

from __future__ import annotations

import tempfile
from pathlib import Path

from y5n.apps.yak.environment.io import env_path, load, save
from y5n.apps.yak.environment.models import Environment
from y5n.apps.yak.pack.models import Mount


class TestEnvironmentModels:
    def test_environment_defaults(self):
        env = Environment(name="dev")
        assert env.schema == "2"
        assert env.install == {}
        assert env.mounts == []

    def test_environment_with_install(self):
        env = Environment(name="dev", install={"runtime": ["./runtime"]})
        assert env.install == {"runtime": ["./runtime"]}

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
            install = {"runtime": ["./runtime", "./sdk"], "system": []}
            env = Environment(
                name="dev",
                install=install,
                mounts=mounts,
            )
            save(env, root)

            loaded = load(root)
            assert loaded is not None
            assert loaded.name == "dev"
            assert loaded.schema == "2"
            assert loaded.install == install
            assert len(loaded.mounts) == 1
            assert loaded.mounts[0].source == "/path/to/system"
            assert loaded.mounts[0].target == "/usr/bin"

    def test_load_old_schema_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_path = root / ".yak" / "environment.yml"
            env_path.parent.mkdir(parents=True)
            env_path.write_text("components:\n- y5n-caps-system\n")
            # The old schema stored a resolved component list; it cannot
            # express the user's intent and is treated as absent (clean break).
            assert load(root) is None

    def test_load_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assert load(root) is None

    def test_env_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assert env_path(root) == root / ".yak" / "environment.yml"
