"""ADR-20 gold tests: Source → Catalog → Index → exact lookup.

- A  Official: a catalog entry resolves to an artifact.
- B  Third party: cool-shell uses the exact same mechanism.
- C  Development: a local source first in the list wins over the release.
- D  Fallback: removing the local source returns to the released artifact.
- E  Two sources offer the same identity — the first wins.
- G  GitHub is transport: catalog + location → artifact, no release scan.
- H  --from is exclusive: ACME wins, nothing else is consulted.
- I  --from miss is an error, never a fallback.
- O  Official: the flat bootstrap source list resolves across one repo.
"""

from __future__ import annotations

import io
import tarfile
import tempfile
from pathlib import Path

import pytest
from conftest import artifact as make_artifact
from conftest import make_source
from y5n.apps.yak.hosts.cli.cwd import Context
from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository
from y5n.apps.yak.resolver.catalog import build_index


def _write_catalog(source: Path, components: dict) -> None:
    if not components:
        lines = ["components: {}"]
    else:
        lines = ["components:"]
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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
        assert record.source == str(dev_crm / "crm")
        staged = inst.root / ".yak" / "components" / "y5n-packs-crm" / "structure"
        assert staged.is_symlink()
        assert staged.resolve() == (dev_crm / "crm" / "structure").resolve()


@pytest.mark.slow
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


class _FakeResp:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False


def _fake_urlopen(responses: list[tuple[str, bytes]]):
    def fake(url: str):
        for match, payload in responses:
            if match in url:
                return _FakeResp(payload)
        raise AssertionError(f"unexpected request: {url}")

    return fake


def _repo_tar_gz(artifact_dir: Path, wrapper: str) -> bytes:
    """A codeload-style repo archive: one top-level wrapper dir."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        tar.add(artifact_dir, arcname=f"{wrapper}/{artifact_dir.name}")
    return buffer.getvalue()


def test_g_github_is_transport_no_release_scan(monkeypatch):
    from y5n.apps.yak.resolver import catalog as catalog_module

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

        artifact_dir = root / "ident-artifact"
        make_artifact(artifact_dir, "y5n-packs-ident", "/usr/sbin/ident")
        catalog_yml = (
            b"components:\n" b"  y5n-packs-ident:\n" b"    location: ident-artifact\n"
        )
        monkeypatch.setattr(
            catalog_module,
            "urlopen",
            _fake_urlopen(
                [
                    (
                        "raw.githubusercontent.com/acme/packs/HEAD/catalog.yml",
                        catalog_yml,
                    ),
                    (
                        "codeload.github.com/acme/packs/tar.gz/HEAD",
                        _repo_tar_gz(artifact_dir, "acme-packs"),
                    ),
                ]
            ),
        )

        index = build_index(["github:acme/packs"], root)
        hit = index.resolve("y5n-packs-ident")
        assert hit is not None
        catalog, ref = hit
        assert catalog.base is None  # remote
        assert ref.location == "ident-artifact"

        mgr = _mgr(Context(path=root, sources=["github:acme/packs"]))
        component = mgr._component_from_ref("y5n-packs-ident", catalog, ref)
        assert component is not None
        assert component.mode == "artifact"
        assert component.artifact is not None
        assert component.artifact.name == "y5n-packs-ident"
        assert component.artifact.mount == "/usr/sbin/ident"


@pytest.mark.slow
def test_h_from_is_exclusive():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        official = root / "official"
        make_artifact(official / "cool-art", "cool-shell", "/opt/official")
        make_source(official, {"cool-shell": {"location": "cool-art"}})
        acme = root / "acme"
        make_artifact(acme / "cool-art", "cool-shell", "/opt/acme")
        make_source(acme, {"cool-shell": {"location": "cool-art"}})

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


def test_official_source_graph(monkeypatch):
    """The bootstrap source list is a flat catalog set."""
    from y5n.apps.yak.resolver import catalog as catalog_module

    pack_system = (
        "components:\n  y5n-packs-system:\n    location: system-v1/system.tar.gz\n"
    )
    pack_ident = (
        "components:\n  y5n-packs-ident:\n    location: ident-v1/ident.tar.gz\n"
    )
    pack_crm = "components:\n  y5n-packs-crm:\n    location: crm-v1/crm.tar.gz\n"
    pack_luma = "components:\n  y5n-packs-luma:\n    location: luma-v1/luma.tar.gz\n"
    pack_labs = "components:\n  y5n-packs-labs:\n    location: labs-v1/labs.tar.gz\n"
    runtime_catalog = (
        "components:\n"
        "  y5n-packs-root:\n    location: packs/y5n-packs-root\n"
        "  y5n-runtime-boot:\n    location: packages/y5n-runtime-boot\n"
        "  y5n-runtime-engine:\n    location: packages/y5n-runtime-engine\n"
    )
    sdk = "components:\n  y5n-sdk-python:\n    location: sdk-v1/sdk.tar.gz\n"
    apps = "components:\n  y5n-apps-runtime:\n    location: rt-v1/rt.tar.gz\n"

    def fake(url: str):
        if "yakoon-runtime/pack-system/" in url:
            return _FakeResp(pack_system.encode())
        if "yakoon-runtime/pack-ident/" in url:
            return _FakeResp(pack_ident.encode())
        if "yakoon-runtime/pack-crm/" in url:
            return _FakeResp(pack_crm.encode())
        if "yakoon-runtime/pack-luma/" in url:
            return _FakeResp(pack_luma.encode())
        if "yakoon-runtime/pack-labs/" in url:
            return _FakeResp(pack_labs.encode())
        if "yakoon-runtime/runtime/HEAD/catalog.yml" in url:
            return _FakeResp(runtime_catalog.encode())
        if "yakoon-runtime/sdk/" in url:
            return _FakeResp(sdk.encode())
        if "yakoon-runtime/apps/" in url:
            return _FakeResp(apps.encode())
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(catalog_module, "urlopen", fake)
    index = build_index(
        [
            "github:yakoon-runtime/pack-system",
            "github:yakoon-runtime/pack-ident",
            "github:yakoon-runtime/pack-crm",
            "github:yakoon-runtime/pack-luma",
            "github:yakoon-runtime/pack-labs",
            "github:yakoon-runtime/runtime",
            "github:yakoon-runtime/sdk",
            "github:yakoon-runtime/apps",
        ],
        Path("/tmp/x"),
    )
    assert index.resolve("y5n-packs-system") is not None
    assert index.resolve("y5n-packs-ident") is not None
    assert index.resolve("y5n-packs-crm") is not None
    assert index.resolve("y5n-packs-luma") is not None
    assert index.resolve("y5n-packs-labs") is not None
    assert index.resolve("y5n-packs-root") is not None
    assert index.resolve("y5n-runtime-boot") is not None
    assert index.resolve("y5n-sdk-python") is not None
    assert index.resolve("y5n-apps-runtime") is not None
