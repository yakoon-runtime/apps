"""Distribution resolution (ADR-24) — a distribution.yml as consumer index.

The read side: one metadata object, plain HTTP, digest-verified artifacts.
No catalogs, no Contents API, no Git repositories on this path.
"""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import pytest

from y5n.apps.yak.installation.manager import InstallationManager
from y5n.apps.yak.repository.artifact import DirectoryArtifactStore
from y5n.apps.yak.repository.file_repo import FileRepository
from y5n.apps.yak.resolver.distribution import (
    Distribution,
    DistributionError,
    fetch_distribution_artifact,
    load_distribution,
)


def _dist(url: str = "https://example.org/distribution.yml") -> Distribution:
    return Distribution(
        url,
        {
            "components": {
                "y5n-caps-system": {
                    "releases": {
                        "0.8.0": {
                            "url": "https://example.org/caps-system.artifact.tar.gz",
                            "digest": "sha256:abc",
                            "dependencies": ["y5n-runtime-api", "y5n-sdk-python"],
                        }
                    }
                },
                "y5n-runtime-api": {
                    "releases": {
                        "0.1.0": {
                            "url": "https://example.org/runtime-api.artifact.tar.gz",
                            "digest": "sha256:def",
                            "dependencies": ["pyyaml"],
                        }
                    }
                },
                "y5n-sdk-python": {
                    "releases": {
                        "0.1.0": {
                            "url": "https://example.org/sdk-python.artifact.tar.gz",
                            "digest": "sha256:ghi",
                        }
                    }
                },
            },
            "bundles": {"system": ["y5n-caps-system"]},
        },
    )


def test_distribution_parses_components_bundles_and_releases():
    d = _dist()
    assert set(d.components) == {
        "y5n-caps-system",
        "y5n-runtime-api",
        "y5n-sdk-python",
    }
    assert d.resolve_bundle("system") == ("y5n-caps-system",)
    rel = d.latest("y5n-caps-system")
    assert rel.version == "0.8.0"
    assert rel.digest == "sha256:abc"
    assert rel.dependencies == ("y5n-runtime-api", "y5n-sdk-python")


def test_latest_picks_highest_version():
    d = Distribution(
        "u",
        {
            "components": {
                "eng": {
                    "releases": {
                        "0.7.0": {"url": "u/old", "digest": None},
                        "0.10.0": {"url": "u/new", "digest": None},
                        "0.8.0": {"url": "u/mid", "digest": None},
                    }
                }
            }
        },
    )
    assert d.latest("eng").version == "0.10.0"
    assert d.latest("missing") is None


def test_distribution_rejects_bad_shapes():
    with pytest.raises(DistributionError, match="components"):
        Distribution("u", {"components": ["x"]})
    with pytest.raises(DistributionError, match="releases"):
        Distribution("u", {"components": {"a": {"releases": []}}})
    with pytest.raises(DistributionError, match="url"):
        Distribution("u", {"components": {"a": {"releases": {"1": {"digest": "x"}}}}})


def test_load_distribution_requires_mapping(monkeypatch):
    import y5n.apps.yak.resolver.distribution as dist_mod

    class _Fake:
        def read(self) -> bytes:
            return b"[]"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req):
        return _Fake()

    monkeypatch.setattr(dist_mod, "urlopen", fake_urlopen)
    monkeypatch.setattr(dist_mod, "Request", lambda url, headers=None: object())
    with pytest.raises(DistributionError, match="mapping"):
        load_distribution("https://example.org/distribution.yml")


def _tarball(name: str, content: bytes = b"data") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(f"{name}/artifact.yml")
        payload = (
            f"name: {name}\nversion: 0.1.0\n"
            "kind: package\nbuilder: python\nhost: python\n"
            "mount: /opt/x\nfingerprint: sha256:fp\n"
        ).encode()
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        info = tarfile.TarInfo(f"{name}/structure/payload.txt")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return gzip.compress(buf.getvalue(), mtime=0)


def _fake_fetch(monkeypatch, body: bytes):
    import y5n.apps.yak.resolver.distribution as dist_mod

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(dist_mod, "urlopen", lambda req: _Resp(body))
    monkeypatch.setattr(
        dist_mod,
        "Request",
        lambda url, headers=None: type("Q", (), {"full_url": url})(),
    )


def test_fetch_artifact_verifies_digest(monkeypatch, tmp_path):
    import y5n.apps.yak.resolver.distribution as dist_mod

    body = _tarball("acme", b"hi")
    digest = dist_mod._sha256_hex(body)
    _fake_fetch(monkeypatch, body)
    cache = tmp_path / "cache"

    res = fetch_distribution_artifact(
        "https://example.org/acme.artifact.tar.gz", "acme", digest, cache_root=cache
    )
    assert (res / "artifact.yml").exists()

    # A wrong digest fails loudly.
    _fake_fetch(monkeypatch, body)
    with pytest.raises(DistributionError, match="digest mismatch"):
        fetch_distribution_artifact(
            "https://example.org/acme.artifact.tar.gz",
            "acme",
            f"sha256:{'0' * 64}",
            cache_root=cache,
        )


def test_manager_resolves_identities_closed_over_distribution(tmp_path):
    """_identities expands bundle + transitive distribution-known deps."""
    dist = _dist()
    mgr = InstallationManager(FileRepository(), DirectoryArtifactStore())
    mgr._distribution_override = dist

    assert mgr._identities("system") == [
        "y5n-caps-system",
        "y5n-runtime-api",  # dep of caps-system
        "y5n-sdk-python",  # dep of caps-system
    ]


def test_manager_resolves_component_from_distribution(monkeypatch, tmp_path):
    import y5n.apps.yak.resolver.distribution as dist_mod

    body = _tarball("y5n-caps-system")
    digest = dist_mod._sha256_hex(body)
    _fake_fetch(monkeypatch, body)

    dist = Distribution(
        "https://example.org/distribution.yml",
        {
            "components": {
                "y5n-caps-system": {
                    "releases": {
                        "0.8.0": {
                            "url": "https://example.org/caps.artifact.tar.gz",
                            "digest": digest,
                        }
                    }
                }
            }
        },
    )
    mgr = InstallationManager(FileRepository(), DirectoryArtifactStore())
    mgr._distribution_override = dist

    comp = mgr._resolve_preferred("y5n-caps-system")
    assert comp is not None
    assert comp.mode == "artifact"
    assert comp.artifact is not None
    assert comp.artifact.name == "y5n-caps-system"
