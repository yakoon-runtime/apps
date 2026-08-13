"""ADR-20 gold tests: Source → Catalog → Index → exact lookup.

- A  Official: a catalog entry resolves to an artifact.
- B  Third party: cool-shell uses the exact same mechanism.
- C  Development: a local source first in the list wins over the release.
- D  Fallback: removing the local source returns to the released artifact.
- E  Two sources offer the same identity — the first wins.
- F  A → B → C → A is a clear cycle error.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository
from y5n.apps.yak.resolver.catalog import CatalogCycleError, build_index


def _write_catalog(
    source: Path, components: dict, *, sub_sources: list[str] | None = None
) -> None:
    lines = []
    for sub in sub_sources or []:
        lines.append(f"  - {sub!r}")
    if lines:
        lines.insert(0, "sources:")
    if not components:
        lines.append("components: {}")
    else:
        lines.append("components:")
    for name, entry in components.items():
        lines.append(f"  {name}:")
        lines.append(f'    version: {entry.get("version", "")!r}')
        lines.append(f'    location: {entry["location"]!r}')
    (source / "catalog.yml").write_text("\n".join(lines) + "\n")


def _write_source_pack(dir: Path, name: str, mount: str) -> None:
    (dir / "structure").mkdir(parents=True)
    (dir / "structure" / "payload.txt").write_text(f"{name}-source")
    (dir / "pack.toml").write_text(
        f'name = "{name}"\nversion = "0.1"\nmount = "{mount}"\n'
    )


def _write_artifact(dir: Path, name: str, mount: str, content: str = "data") -> None:
    (dir / "structure").mkdir(parents=True)
    (dir / "structure" / "payload.txt").write_text(content)
    (dir / "artifact.yml").write_text(
        "name: " + name + "\n"
        "version: 0.1.0\n"
        "kind: package\n"
        "builder: python\n"
        "host: python\n"
        "mount: " + mount + "\n"
        "fingerprint: sha256:" + name + "\n"
    )


def _mgr(ctx: Context) -> InstallationManager:
    return InstallationManager(FileRepository(), DirectoryArtifactStore(), context=ctx)


def test_a_official_resolves_artifact():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        official = root / "official"
        official.mkdir()
        _write_catalog(
            official,
            {"y5n-packs-ident": {"version": "0.8.0", "location": "ident-artifact"}},
        )
        _write_artifact(
            official / "ident-artifact", "y5n-packs-ident", "/usr/sbin/ident"
        )
        ctx = Context(path=root, sources=[str(official)])
        mgr = _mgr(ctx)
        inst = mgr.install(root / "inst")
        mgr.add("y5n-packs-ident", inst.root)

        state = mgr.load(inst.root)
        assert state is not None
        record = next(c for c in state.components if c.name == "y5n-packs-ident")
        assert record.mode == "artifact"
        staged = inst.root / ".yak" / "components" / "y5n-packs-ident" / "structure"
        assert staged.is_dir() and not staged.is_symlink()


def test_b_third_party_uses_the_same_mechanism():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        acme = root / "acme"
        acme.mkdir()
        _write_catalog(
            acme,
            {"cool-shell": {"version": "2.1.0", "location": "shell-artifact"}},
        )
        _write_artifact(acme / "shell-artifact", "cool-shell", "/opt/cool")
        ctx = Context(path=root, sources=[str(acme)])
        mgr = _mgr(ctx)
        inst = mgr.install(root / "inst")
        mgr.add("cool-shell", inst.root)

        state = mgr.load(inst.root)
        assert state is not None
        record = next(c for c in state.components if c.name == "cool-shell")
        assert record.mode == "artifact"
        assert record.mount == "/opt/cool"


def test_c_local_source_first_wins():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dev_crm = root / "dev" / "crm"
        dev_crm.mkdir(parents=True)
        _write_catalog(
            dev_crm,
            {"y5n-packs-crm": {"version": "0.9.0", "location": "crm"}},
        )
        _write_source_pack(dev_crm / "crm", "y5n-packs-crm", "/opt/crm")

        official = root / "official"
        official.mkdir()
        _write_catalog(
            official,
            {"y5n-packs-crm": {"version": "0.8.0", "location": "crm-artifact"}},
        )
        _write_artifact(official / "crm-artifact", "y5n-packs-crm", "/opt/crm")

        ctx = Context(path=root, sources=[str(dev_crm), str(official)])
        mgr = _mgr(ctx)
        inst = mgr.install(root / "inst")
        mgr.add("y5n-packs-crm", inst.root)

        state = mgr.load(inst.root)
        assert state is not None
        record = next(c for c in state.components if c.name == "y5n-packs-crm")
        assert record.mode == "source"
        assert record.source == str(dev_crm / "crm" / "structure")
        staged = inst.root / ".yak" / "components" / "y5n-packs-crm" / "structure"
        assert staged.is_symlink()
        assert staged.resolve() == (dev_crm / "crm" / "structure").resolve()


def test_d_removing_local_source_returns_to_released():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dev_crm = root / "dev" / "crm"
        dev_crm.mkdir(parents=True)
        _write_catalog(
            dev_crm,
            {"y5n-packs-crm": {"version": "0.9.0", "location": "crm"}},
        )
        _write_source_pack(dev_crm / "crm", "y5n-packs-crm", "/opt/crm")

        official = root / "official"
        official.mkdir()
        _write_catalog(
            official,
            {"y5n-packs-crm": {"version": "0.8.0", "location": "crm-artifact"}},
        )
        _write_artifact(official / "crm-artifact", "y5n-packs-crm", "/opt/crm")

        ctx_dev = Context(path=root, sources=[str(dev_crm), str(official)])
        mgr = _mgr(ctx_dev)
        inst = mgr.install(root / "inst")
        mgr.add("y5n-packs-crm", inst.root)
        staged = inst.root / ".yak" / "components" / "y5n-packs-crm" / "structure"
        assert staged.is_symlink()

        ctx_released = Context(path=root, sources=[str(official)])
        mgr2 = _mgr(ctx_released)
        mgr2.update(inst.root)

        state = mgr2.load(inst.root)
        assert state is not None
        record = next(c for c in state.components if c.name == "y5n-packs-crm")
        assert record.mode == "artifact"
        assert staged.is_dir() and not staged.is_symlink()


def test_e_first_source_wins():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        s1 = root / "s1"
        s2 = root / "s2"
        for source, tag in ((s1, "one"), (s2, "two")):
            source.mkdir()
            _write_catalog(
                source,
                {
                    "y5n-packs-ident": {
                        "version": "0.8.0",
                        "location": f"{tag}-artifact",
                    }
                },
            )
            _write_artifact(
                source / f"{tag}-artifact", "y5n-packs-ident", "/usr/sbin/ident", tag
            )

        index = build_index([str(s1), str(s2)], root)
        hit = index.resolve("y5n-packs-ident")
        assert hit is not None
        catalog, ref = hit
        assert catalog.spec == str(s1)
        assert ref.location == "one-artifact"


def test_f_cycle_is_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, subs in (("a", ["b"]), ("b", ["c"]), ("c", ["a"])):
            source = root / name
            source.mkdir()
            _write_catalog(source, {}, sub_sources=subs)

        with pytest.raises(CatalogCycleError):
            build_index([str(root / "a")], root)
