"""Tests for environment module — models, io."""

from __future__ import annotations

import tempfile
from pathlib import Path

from y5n.apps.yak.environment.io import env_path, load, save
from y5n.apps.yak.environment.models import Environment
from y5n.apps.yak.pack.models import Mount, PackName


class TestEnvironmentModels:
    def test_environment_defaults(self):
        env = Environment(name="dev")
        assert env.schema == "1"
        assert env.components == []
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
            comps = [PackName("y5n-packs-system")]
            env = Environment(
                name="dev",
                components=comps,
                mounts=mounts,
            )
            save(env, root)

            loaded = load(root)
            assert loaded is not None
            assert loaded.name == "dev"
            assert loaded.schema == "1"
            assert loaded.components == comps
            assert len(loaded.mounts) == 1
            assert loaded.mounts[0].source == "/path/to/system"
            assert loaded.mounts[0].target == "/usr/bin"

    def test_load_legacy_dependencies_key(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_path = root / ".yak" / "environment.yml"
            env_path.parent.mkdir(parents=True)
            env_path.write_text("dependencies:\n- y5n-packs-system\n")
            loaded = load(root)
            assert loaded is not None
            assert loaded.components == [PackName("y5n-packs-system")]

    def test_load_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assert load(root) is None

    def test_env_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assert env_path(root) == root / ".yak" / "environment.yml"
