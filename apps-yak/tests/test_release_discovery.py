"""Release resolution over the repository-local releases.yml (ADR-23 Step 4).

The catalog carries no version. The currently offered artifact of a
component resolves through ``releases.yml`` at the catalog's boundary —
never through a scan of the GitHub Releases API. The download goes over
the release-asset CDN; the recorded artifact digest is checked against
the downloaded bytes before the artifact is used or reused.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile

import pytest
from y5n.apps.yak.resolver.catalog import (
    CatalogError,
    _fetch_release_index,
    _parse_release_index,
    fetch_github_release,
    release_index_path,
)


def test_release_index_path_is_at_the_catalog_boundary():
    assert release_index_path("github:acme/packs") == "releases.yml"
    assert release_index_path("github:acme/packs:dir/catalog.yml") == "dir/releases.yml"


def test_parse_release_index_contract():
    index = _parse_release_index(
        "github:acme/packs",
        {
            "components": {
                "y5n-caps-system": {
                    "version": "0.8.0",
                    "tag": "y5n-caps-system-v0.8.0",
                    "digest": "sha256:abc",
                }
            }
        },
    )
    entry = index["y5n-caps-system"]
    assert entry.version == "0.8.0"
    assert entry.tag == "y5n-caps-system-v0.8.0"
    assert entry.digest == "sha256:abc"


def test_parse_release_index_requires_tag_version_digest_type():
    with pytest.raises(CatalogError, match="tag"):
        _parse_release_index("github:acme/packs", {"components": {"x": {}}})
    with pytest.raises(CatalogError, match="version"):
        _parse_release_index(
            "github:acme/packs", {"components": {"x": {"tag": "x-v1"}}}
        )
    with pytest.raises(CatalogError, match="mapping"):
        _parse_release_index("github:acme/packs", {"components": ["x"]})


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
    """Fake transport for releases.yml (Contents API) + CDN download.

    Serves only the release index and the asset download — any request to
    the /releases API scan fails the test, proving resolution never scans.
    """

    def __init__(self, monkeypatch, name: str, tag: str) -> None:  # noqa: ANN001
        self.requests: list[str] = []
        self.name = name
        self.tag = tag
        self.releases_yml: bytes = b"components: {}"
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
            if path == "releases.yml":
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


def test_resolve_fetches_release_index_and_downloads_asset(monkeypatch, tmp_path):
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
        "components:\n"
        f"  {name}:\n"
        f"    version: 0.8.0\n"
        f"    tag: {tag}\n"
        f"    digest: {cat._sha256_hex(asset)}\n"
    ).encode()
    fake.asset = asset

    cached_calls = list(fake.requests)
    result = fetch_github_release(_spec(name), name)
    assert result is not None
    assert (result / "artifact.yml").exists()
    # One Contents read per repo + one CDN download — nothing else.
    assert [r for r in fake.requests if "/contents/" in r] == [
        "https://api.github.com/repos/acme/packs/contents/releases.yml"
    ]
    assert [r for r in fake.requests if "/releases/download/" in r] == [
        f"https://github.com/acme/packs/releases/download/{tag}/{name}.artifact.tar.gz"
    ]
    assert not any("/releases?" in r for r in fake.requests)

    # Second resolution reuses the digest-guarded cache — no new download.
    requests_before = list(fake.requests)
    fetch_github_release(_spec(name), name)
    assert fake.requests == requests_before


def test_resolve_uses_disk_release_index_cache(monkeypatch, tmp_path):
    """The release index is cached on disk like catalogs — a fresh process
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
        "components:\n"
        f"  {name}:\n"
        f"    version: 0.8.0\n"
        f"    tag: {tag}\n"
        f"    digest: {cat._sha256_hex(asset)}\n"
    ).encode()
    fake.asset = asset

    fetch_github_release(_spec(name), name)
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
    result = fetch_github_release(_spec(name), name)
    assert result is not None
    assert fake_fresh.requests == []


def test_resolve_fails_when_component_not_offered(monkeypatch, tmp_path):
    fake = FakeRelease(monkeypatch, "y5n-caps-system", "y5n-caps-system-v0.8.0")
    with pytest.raises(CatalogError, match="not offered"):
        fetch_github_release(_spec(), "y5n-sdk-python")


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
        "components:\n"
        f"  {name}:\n"
        f"    version: 0.8.0\n"
        f"    tag: {tag}\n"
        f"    digest: {cat._sha256_hex(b'other bytes')}\n"
    ).encode()
    fake.asset = asset

    with pytest.raises(CatalogError, match="digest mismatch"):
        fetch_github_release(_spec(name), name)


def test_fetch_release_index_missing_file_fails(monkeypatch, tmp_path):
    import y5n.apps.yak.resolver.catalog as cat

    class _Resp:
        def read(self) -> bytes:
            raise OSError("not found")

        def __enter__(self):
            return self

        def __exit__(self, *a) -> bool:
            return False

    def fake_urlopen(target):
        raise OSError(f"cannot fetch url")

    monkeypatch.setattr(cat, "urlopen", fake_urlopen)
    with pytest.raises(CatalogError, match="cannot fetch"):
        _fetch_release_index("github:acme/packs")