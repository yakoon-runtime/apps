"""ADR-23 Step 4: the catalog is a name → location mapping.

The catalog key is a discovery binding / index key only — never a
normative identity. Identity and version stay in each location's
``.yak/component.yml``; remote discovery performs no per-location
``component.yml`` fetch, so the remote index costs O(catalogs/repos)
requests instead of O(components). Identity is validated at the actual
materialization.
"""

from __future__ import annotations

import pytest
from conftest import make_source
from y5n.apps.yak.resolver.catalog import CatalogError, build_index


def test_index_is_built_from_catalog_keys(tmp_path):
    """build_index maps each catalog key to its location without reading it."""
    make_source(tmp_path, {"a": "packs/a", "b": "packs/b"})
    index = build_index([str(tmp_path)], tmp_path)
    assert set(index.components) == {"a", "b"}
    catalog, ref = index.resolve("a")
    assert catalog.spec == str(tmp_path)
    assert ref.name == "a"
    assert ref.location == "packs/a"


def test_location_without_component_yml_is_discovered(tmp_path):
    """A location is discovered purely from the mapping — the manifest is
    only consulted at the actual access (materialization), never eagerly."""
    make_source(tmp_path, {"a": "packs/a"})
    (tmp_path / "packs/a" / ".yak" / "component.yml").unlink()
    index = build_index([str(tmp_path)], tmp_path)
    assert set(index.components) == {"a"}


def test_components_must_be_a_mapping(tmp_path):
    """The old location-list shape is rejected, not half-parsed."""
    (tmp_path / "catalog.yml").write_text(
        "components:\n  - location: a\n"
    )
    with pytest.raises(CatalogError, match="mapping"):
        build_index([str(tmp_path)], tmp_path)


def test_each_component_needs_a_location(tmp_path):
    (tmp_path / "catalog.yml").write_text(
        "components:\n  a:\n    release: a-v0.9.0\n"
    )
    with pytest.raises(CatalogError, match="location"):
        build_index([str(tmp_path)], tmp_path)


def test_extra_fields_are_ignored(tmp_path):
    """version/release/distribution fields are dead config — never read."""
    make_source(tmp_path, {"a": "packs/a"})
    catalog_file = tmp_path / "catalog.yml"
    catalog_file.write_text(
        "components:\n"
        "  a:\n"
        "    location: packs/a\n"
        "    release: a-v0.9.0\n"
        "    distribution: github:acme/elsewhere\n"
        "    version: 9.9.9\n"
    )
    index = build_index([str(tmp_path)], tmp_path)
    catalog, ref = index.resolve("a")
    assert catalog.spec == str(tmp_path)
    assert ref.location == "packs/a"


def test_first_hit_wins_by_key(tmp_path):
    """The same key from two sources resolves to the first source."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_source(first, {"a": "packs/a", "mine": "packs/mine"})
    make_source(second, {"a": "other/a"})

    index = build_index([str(first), str(second)], tmp_path)
    catalog, ref = index.resolve("a")
    assert catalog.spec == str(first)
    assert ref.location == "packs/a"  # never overridden by the later source


def test_remote_discovery_fetches_catalogs_only(monkeypatch, tmp_path):
    """A remote index is built from the catalog mapping — no per-location
    component.yml fetch. 8 sources cost 8 catalog reads, not 8 + N."""
    import y5n.apps.yak.resolver.catalog as cat

    catalog_yml = (
        "components:\n"
        "  a:\n"
        "    location: packs/a\n"
        "  b:\n"
        "    location: packs/b\n"
    )
    responses = {"catalog.yml": catalog_yml.encode()}
    requested: list[str] = []

    def fake_urlopen(req):
        url = req.full_url
        key = url.split("/contents/", 1)[1]
        requested.append(key)
        body = responses[key]

        class _Resp:
            def read(self) -> bytes:
                return body

            def __enter__(self):
                return self

            def __exit__(self, *args) -> bool:
                return False

        return _Resp()

    monkeypatch.setattr(cat, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        cat,
        "Request",
        lambda url, headers=None: type("Q", (), {"full_url": url})(),
    )

    index = build_index(["github:acme/multi"], tmp_path)
    assert set(index.components) == {"a", "b"}
    # Only the catalog is fetched — identities come from the mapping keys.
    assert requested == ["catalog.yml"]
    assert not any("component.yml" in r for r in requested)
    assert not any("tar.gz" in r for r in requested)


def test_remote_catalog_without_component_yml_resolves(tmp_path, monkeypatch):
    """A remote location without component.yml is discovered fine — the
    mapping is the discovery binding; the manifest is validated later."""
    import y5n.apps.yak.resolver.catalog as cat

    responses = {
        "catalog.yml": b"components:\n  a:\n    location: packs/a\n",
    }

    def fake_urlopen(req):
        url = req.full_url
        key = url.split("/contents/", 1)[1]
        body = responses[key]

        class _Resp:
            def read(self) -> bytes:
                return body

            def __enter__(self):
                return self

            def __exit__(self, *args) -> bool:
                return False

        return _Resp()

    monkeypatch.setattr(cat, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        cat,
        "Request",
        lambda url, headers=None: type("Q", (), {"full_url": url})(),
    )

    index = build_index(["github:acme/multi"], tmp_path)
    assert index.resolve("a") is not None


def test_eight_sources_cost_eight_catalog_reads(monkeypatch, tmp_path):
    """The E2E invariant, counted: 8 repositories with 18 components cost
    exactly 8 Contents-API catalog reads during discovery — the
    per-component component.yml reads of the old model are gone."""
    import y5n.apps.yak.resolver.catalog as cat

    # 8 repos; the first two offer 3 components each, the rest 2 each:
    # 6 + 12 = 18 components total, resolved purely from catalog keys.
    per_repo: dict[str, int] = {
        "repo1": 3,
        "repo2": 3,
        "repo3": 2,
        "repo4": 2,
        "repo5": 2,
        "repo6": 2,
        "repo7": 2,
        "repo8": 2,
    }
    requested: list[str] = []

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

    def fake_urlopen(req):
        url = req.full_url
        repo = "/".join(url.split("/repos/", 1)[1].split("/")[:2])
        key = url.split("/contents/", 1)[1]
        requested.append(f"{repo}/{key}")
        return _Resp(responses[repo])

    def fake_request(url, headers=None):
        return type("Q", (), {"full_url": url})()

    responses: dict[str, bytes] = {}
    sources = [f"github:acme/{repo}" for repo in per_repo]
    for repo, count in per_repo.items():
        entries = "".join(
            f"  y5n-c{repo[4:]}-{i}:\n    location: packages/c{repo[4:]}-{i}\n"
            for i in range(1, count + 1)
        )
        responses[f"acme/{repo}"] = f"components:\n{entries}".encode()

    monkeypatch.setattr(cat, "urlopen", fake_urlopen)
    monkeypatch.setattr(cat, "Request", fake_request)

    index = build_index(sources, tmp_path)
    assert len(index.components) == 18
    assert len(requested) == 8
    assert all(r.endswith("/catalog.yml") for r in requested)
    assert not any("component.yml" in r for r in requested)