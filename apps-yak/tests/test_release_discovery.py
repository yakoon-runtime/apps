"""Release resolution over the component-local .yak/releases.yml (ADR-23).

The catalog carries no version. The published builds of a component
resolve through the component's own ``releases.yml`` beside its
``.yak/component.yml`` — never through a scan of the GitHub Releases API.
``install`` resolves the highest released version. The download goes over
the release-asset CDN; the recorded artifact digest is checked against the
downloaded bytes before the artifact is used or reused.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from urllib.error import HTTPError

import pytest

from y5n.apps.yak.resolver.catalog import (
    CatalogError,
    _fetch_releases,
    _parse_releases,
    _select_offered,
    fetch_github_release,
    release_index_path,
)


def test_release_index_path_is_component_local_and_plural():
    assert release_index_path(".") == ".yak/releases.yml"
    assert (
        release_index_path("packages/runtime-engine")
        == "packages/runtime-engine/.yak/releases.yml"
    )
    assert (
        release_index_path("./packages/runtime-store")
        == "packages/runtime-store/.yak/releases.yml"
    )


def test_parse_releases_contract():
    catalog = _parse_releases(
        "github:acme/packs",
        {
            "releases": {
                "0.7.0": {"tag": "eng-v0.7.0", "digest": "sha256:old"},
                "0.8.0": {"tag": "eng-v0.8.0", "digest": "sha256:abc"},
            }
        },
    )
    assert list(catalog) == ["0.7.0", "0.8.0"]
    assert catalog["0.8.0"].version == "0.8.0"
    assert catalog["0.8.0"].tag == "eng-v0.8.0"
    assert catalog["0.8.0"].digest == "sha256:abc"
    # digest is optional per release
    assert catalog["0.7.0"].digest == "sha256:old"


def test_parse_releases_requires_tag_and_typed_digest():
    with pytest.raises(CatalogError, match="tag"):
        _parse_releases("github:acme/packs", {"releases": {"0.8.0": {}}})
    with pytest.raises(CatalogError, match="digest"):
        _parse_releases(
            "github:acme/packs",
            {"releases": {"0.8.0": {"tag": "x-v0.8.0", "digest": 5}}},
        )
    with pytest.raises(CatalogError, match="mapping"):
        _parse_releases("github:acme/packs", {"releases": ["0.8.0"]})


def test_select_offered_is_the_highest_released_version():
    catalog = _parse_releases(
        "github:acme/packs",
        {
            "releases": {
                "0.9.0": {"tag": "eng-v0.9.0", "digest": "sha256:c"},
                "0.7.0": {"tag": "eng-v0.7.0", "digest": "sha256:a"},
                "0.10.0": {"tag": "eng-v0.10.0", "digest": "sha256:d"},
                "0.8.0": {"tag": "eng-v0.8.0", "digest": "sha256:b"},
            }
        },
    )
    assert _select_offered(catalog).tag == "eng-v0.10.0"
    assert _select_offered({}) is None


def _tarball(artifact_dir: dict[str, bytes], name: str) -> bytes:
    """A deterministic gzip tarball containing <name> with artifact.yml."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(f"{name}/artifact.yml")
        payload = artifact_dir["artifact.yml"]
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        info = tarfile.TarInfo(f"{name}/structure/payload.txt")
        payload = artifact_dir.get("structure/payload.txt", b"data")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return gzip.compress(buf.getvalue(), mtime=0)


class FakeRelease:
    """Fake transport for a component's releases.yml (Contents API) + CDN.

    Serves only the release catalog and the asset download — any request
    to the /releases API scan fails the test, proving resolution never
    scans.
    """

    def __init__(
        self, monkeypatch, name: str, tag: str, location: str = "."
    ) -> None:  # noqa: ANN001
        self.requests: list[str] = []
        self.name = name
        self.tag = tag
        self.location = location
        self.releases_yml: bytes | None = None
        self.asset: bytes | None = None

        import y5n.apps.yak.resolver.catalog as cat

        monkeypatch.setattr(cat, "urlopen", self.urlopen)
        monkeypatch.setattr(cat, "Request", _FakeRequest)

    def urlopen(self, target):
        url = target.full_url if hasattr(target, "full_url") else str(target)
        self.requests.append(url)
        if "/releases?" in url:
            raise AssertionError("must not scan the GitHub Releases API")
        if "/contents/" in url:
            path = url.split("/contents/", 1)[1]
            if path == release_index_path(self.location):
                if self.releases_yml is None:
                    raise HTTPError(url, 404, "Not Found", {}, None)
                return self._resp(self.releases_yml)
            raise OSError(f"no content for {path}")
        if "/releases/download/" in url:
            assert self.asset is not None
            assert url.endswith(f"{self.name}.artifact.tar.gz")
            return self._resp(self.asset)
        raise AssertionError(f"unexpected request: {url}")

    @staticmethod
    def _resp(body: bytes):
        class _Resp:
            def read(self) -> bytes:
                return body

            def __enter__(self):
                return self

            def __exit__(self, *a) -> bool:
                return False

        return _Resp()


def _spec(name: str = "y5n-caps-system") -> str:
    return f"github:acme/packs"


class _FakeRequest:
    def __init__(self, url, data=None, headers=None, method=None) -> None:
        self.full_url = url
        self.data = data
        self.headers = headers or {}
        self.method = method


def test_resolve_fetches_releases_and_downloads_asset(monkeypatch, tmp_path):
    import y5n.apps.yak.resolver.catalog as cat

    name = "y5n-caps-system"
    tag = f"{name}-v0.8.0"
    asset = _tarball(
        {
            "artifact.yml": (
                f"name: {name}\nversion: 0.8.0\n"
                "kind: package\nbuilder: python\nhost: python\n"
                "mount: /opt/x\nfingerprint: sha256:fp\n"
            ).encode(),
            "structure/payload.txt": b"data",
        },
        name,
    )
    fake = FakeRelease(monkeypatch, name, tag)
    fake.releases_yml = (
        "releases:\n"
        f"  0.7.0:\n"
        f"    tag: {name}-v0.7.0\n"
        f"    digest: {cat._sha256_hex(b'old')}\n"
        f"  0.8.0:\n"
        f"    tag: {tag}\n"
        f"    digest: {cat._sha256_hex(asset)}\n"
    ).encode()
    fake.asset = asset

    result = fetch_github_release(_spec(name), name, ".")
    assert result is not None
    assert (result / "artifact.yml").exists()
    # One Contents read per component + one CDN download of the HIGHEST
    # version — nothing else.
    assert [r for r in fake.requests if "/contents/" in r] == [
        "https://api.github.com/repos/acme/packs/contents/.yak/releases.yml"
    ]
    assert [r for r in fake.requests if "/releases/download/" in r] == [
        f"https://github.com/acme/packs/releases/download/{tag}/{name}.artifact.tar.gz"
    ]
    assert not any("/releases?" in r for r in fake.requests)

    # Second resolution reuses the digest-guarded cache — no new download.
    requests_before = list(fake.requests)
    fetch_github_release(_spec(name), name, ".")
    assert fake.requests == requests_before


def test_resolve_uses_disk_releases_cache(monkeypatch, tmp_path):
    """The release catalog is cached on disk like catalogs — a fresh process
    reads it from the cache and never re-fetches within the TTL."""
    import y5n.apps.yak.resolver.catalog as cat

    name = "y5n-caps-system"
    tag = f"{name}-v0.8.0"
    asset = _tarball(
        {
            "artifact.yml": (
                f"name: {name}\nversion: 0.8.0\n"
                "kind: package\nbuilder: python\nhost: python\n"
                "mount: /opt/x\nfingerprint: sha256:fp\n"
            ).encode(),
        },
        name,
    )
    fake = FakeRelease(monkeypatch, name, tag)
    fake.releases_yml = (
        "releases:\n"
        f"  0.8.0:\n"
        f"    tag: {tag}\n"
        f"    digest: {cat._sha256_hex(asset)}\n"
    ).encode()
    fake.asset = asset

    fetch_github_release(_spec(name), name, ".")
    contents_calls = [r for r in fake.requests if "/contents/" in r]
    assert len(contents_calls) == 1

    # Simulate a new process (fresh in-memory state), same disk cache:
    # the cached releases.yml is used and the download is skipped.
    monkeypatch.setattr(cat, "_BRANCH_CACHE", {})
    import y5n.apps.yak.resolver.catalog as fresh

    class FakeFresh:
        def __init__(self) -> None:
            self.requests: list[str] = []

        def urlopen(self, target):
            url = target.full_url if hasattr(target, "full_url") else str(target)
            self.requests.append(url)
            raise AssertionError(f"must not re-fetch within TTL: {url}")

    fake_fresh = FakeFresh()
    monkeypatch.setattr(fresh, "urlopen", fake_fresh.urlopen)
    result = fetch_github_release(_spec(name), name, ".")
    assert result is not None
    assert fake_fresh.requests == []


def test_resolve_fails_when_component_not_offered(monkeypatch, tmp_path):
    fake = FakeRelease(monkeypatch, "y5n-caps-system", "y5n-caps-system-v0.8.0")
    with pytest.raises(CatalogError, match="not offered"):
        fetch_github_release(_spec(), "y5n-sdk-python", ".")


def test_digest_mismatch_fails_loudly(monkeypatch, tmp_path):
    import y5n.apps.yak.resolver.catalog as cat

    name = "y5n-caps-system"
    tag = f"{name}-v0.8.0"
    asset = _tarball(
        {
            "artifact.yml": (
                f"name: {name}\nversion: 0.8.0\n"
                "kind: package\nbuilder: python\nhost: python\n"
                "mount: /opt/x\nfingerprint: sha256:fp\n"
            ).encode(),
        },
        name,
    )
    fake = FakeRelease(monkeypatch, name, tag)
    fake.releases_yml = (
        "releases:\n"
        f"  0.8.0:\n"
        f"    tag: {tag}\n"
        f"    digest: {cat._sha256_hex(b'other bytes')}\n"
    ).encode()
    fake.asset = asset

    with pytest.raises(CatalogError, match="digest mismatch"):
        fetch_github_release(_spec(name), name, ".")


def test_fetch_releases_404_means_nothing_offered(monkeypatch):
    import y5n.apps.yak.resolver.catalog as cat

    class _FakeRequest:
        def __init__(self, url, data=None, headers=None, method=None) -> None:
            self.full_url = url

    def fake_urlopen(target):
        url = getattr(target, "full_url", str(target))
        raise HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(cat, "Request", _FakeRequest)
    monkeypatch.setattr(cat, "urlopen", fake_urlopen)
    assert _fetch_releases("github:acme/packs", "packages/runtime-engine") == {}


def test_fetch_releases_transport_error_fails(monkeypatch):
    import y5n.apps.yak.resolver.catalog as cat

    class _FakeRequest:
        def __init__(self, url, data=None, headers=None, method=None) -> None:
            self.full_url = url

    def fake_urlopen(target):
        raise OSError("down")

    monkeypatch.setattr(cat, "Request", _FakeRequest)
    monkeypatch.setattr(cat, "urlopen", fake_urlopen)
    with pytest.raises(CatalogError, match="cannot fetch"):
        _fetch_releases("github:acme/packs", ".")
