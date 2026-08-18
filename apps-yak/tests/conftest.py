"""Shared helpers for the source-catalog model (ADR-20).

The test suite is hermetic: an autouse guard blocks real GitHub network
calls and redirects ``Path.home`` into a per-test tempdir, so no test
run can touch the real registry, pollute ``~/.yak`` or upload to a real
repository. Transport tests fake ``urlopen``/``Request`` explicitly.
"""

from __future__ import annotations

import base64
import hashlib
import zipfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_real_github(monkeypatch):
    """Block real GitHub transport in the resolver modules.

    A test must fake ``urlopen``/``Request`` explicitly (FakeGithub); a
    test that would reach the real network fails loudly instead of
    operating on the real repositories or uploading fake artifacts.
    """
    def _block(*args, **kwargs):
        raise AssertionError(
            "real GitHub network call attempted in tests — fake the "
            "transport (FakeGithub) or use a local catalog"
        )

    import y5n.apps.yak.resolver.catalog as catalog_mod
    import y5n.apps.yak.resolver.github as github_mod

    monkeypatch.setattr(github_mod, "urlopen", _block)
    monkeypatch.setattr(github_mod, "Request", _block)
    monkeypatch.setattr(catalog_mod, "urlopen", _block)
    monkeypatch.setattr(catalog_mod, "Request", _block)


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    """Keep every test off the real ``~/.yak`` global store and cache."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))


def make_source(
    path: Path,
    components: dict | None = None,
    bundles: dict | None = None,
) -> Path:
    """Create a source directory with a declared catalog.yml (ADR-23 Step 3).

    The catalog lists ``location`` entries only — it never declares an
    identity. Each location must be a component root, so a
    ``.yak/component.yml`` declaring the component's own name is created
    at every listed location (never overwritten).
    """
    path.mkdir(parents=True, exist_ok=True)
    components = components or {}
    lines = ["components:"]
    if components:
        for name, entry in components.items():
            location = entry if isinstance(entry, str) else entry["location"]
            lines.append(f"  - location: {location!r}")
            root = path / location
            root.mkdir(parents=True, exist_ok=True)
            manifest = root / ".yak" / "component.yml"
            if not manifest.exists():
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text(f"name: {name}\nversion: 0.1.0\n")
    else:
        lines.append("  []")
    if bundles:
        lines.append("bundles:")
        for name, members in bundles.items():
            lines.append(f"  {name}:")
            for member in members:
                lines.append(f"    - {member!r}")
    (path / "catalog.yml").write_text("\n".join(lines) + "\n")
    return path


def source_pack(path: Path, name: str, mount: str) -> Path:
    """A source component: .yak/component.yml identity + mount + structure."""
    (path / "structure").mkdir(parents=True, exist_ok=True)
    (path / "structure" / "payload.txt").write_text(f"{name}-source")
    (path / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["setuptools>=68", "wheel"]\n'
        'build-backend = "setuptools.build_meta"\n'
        "\n"
        "[project]\n"
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
    )
    (path / ".yak").mkdir(parents=True, exist_ok=True)
    (path / ".yak" / "component.yml").write_text(
        f"name: {name}\nversion: 0.1.0\n"
    )
    (path / ".yak" / "mount.yml").write_text(f"path: {mount}\n")
    return path


def artifact(
    path: Path,
    name: str,
    mount: str,
    content: str = "data",
    fingerprint: str | None = None,
) -> Path:
    """An artifact component: artifact.yml + structure."""
    (path / "structure").mkdir(parents=True, exist_ok=True)
    (path / "structure" / "payload.txt").write_text(content)
    (path / "artifact.yml").write_text(
        "name: " + name + "\n"
        "version: 0.1.0\n"
        "kind: package\n"
        "builder: python\n"
        "host: python\n"
        "mount: " + mount + "\n"
        "fingerprint: sha256:" + (fingerprint or name) + "\n"
    )
    return path


def wheel_artifact(
    path: Path,
    name: str,
    version: str,
    deps: tuple = (),
    mount: str | None = None,
) -> Path:
    """An artifact component with a real wheel: artifact.yml + wheel."""
    (path / "structure").mkdir(parents=True, exist_ok=True)
    (path / "structure" / "payload.txt").write_text("data")
    _write_wheel(path, name, version, deps)
    mount_line = f"mount: {mount}\n" if mount else ""
    (path / "artifact.yml").write_text(
        f"name: {name}\n"
        f"version: {version}\n"
        "kind: package\n"
        "builder: python\n"
        "host: python\n"
        f"{mount_line}"
        f"fingerprint: sha256:{name}\n"
    )
    return path


def _write_wheel(artifact_dir: Path, name: str, version: str, deps: tuple) -> None:
    """Write a minimal installable pure-python wheel into an artifact dir."""
    dist = name.replace("-", "_")
    meta = (
        "Metadata-Version: 2.1\n"
        f"Name: {name}\n"
        f"Version: {version}\n"
        + "".join(f"Requires-Dist: {d}\n" for d in deps)
        + "\n"
    )
    wheel_text = (
        "Wheel-Version: 1.0\n"
        "Generator: yak-test\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )
    files = {
        f"{dist}/__init__.py": "",
        f"{dist}-{version}.dist-info/METADATA": meta,
        f"{dist}-{version}.dist-info/WHEEL": wheel_text,
    }
    record_lines = []
    for filename, content in files.items():
        digest = base64.urlsafe_b64encode(
            hashlib.sha256(content.encode()).digest()
        ).rstrip(b"=").decode()
        record_lines.append(f"{filename},sha256={digest},{len(content)}\n")
    record = "".join(record_lines) + f"{dist}-{version}.dist-info/RECORD,,\n"
    files[f"{dist}-{version}.dist-info/RECORD"] = record

    wheel = artifact_dir / f"{dist}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)


def source_proj(
    path: Path,
    name: str,
    version: str,
    deps: tuple = (),
    mount: str | None = None,
) -> Path:
    """A source component that pip can install editable (pyproject + module)."""
    pkg = name.replace("-", "_")
    (path / "src" / pkg).mkdir(parents=True)
    (path / "src" / pkg / "__init__.py").write_text("")
    deps_list = "".join(f'    "{d}",\n' for d in deps)
    (path / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["setuptools>=68", "wheel"]\n'
        'build-backend = "setuptools.build_meta"\n'
        "\n"
        "[project]\n"
        f'name = "{name}"\n'
        f'version = "{version}"\n'
        "requires-python = '>=3.13'\n"
        + (f"dependencies = [\n{deps_list}]\n" if deps else "")
        + "\n"
        "[tool.setuptools]\n"
        'package-dir = {"" = "src"}\n'
        "\n"
        "[tool.setuptools.packages.find]\n"
        'where = ["src"]\n'
    )
    if mount:
        (path / "structure").mkdir(parents=True, exist_ok=True)
        (path / "structure" / "payload.txt").write_text(f"{name}-source")
    (path / ".yak").mkdir(parents=True, exist_ok=True)
    (path / ".yak" / "component.yml").write_text(
        f"name: {name}\nversion: {version}\n"
    )
    if mount:
        (path / ".yak" / "mount.yml").write_text(f"path: {mount}\n")
    return path
