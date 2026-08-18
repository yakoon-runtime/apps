"""ADR-23 Step 3: the catalog discovers by location, never by identity.

A catalog lists ``location`` entries only. Each location is a component
root whose ``.yak/component.yml`` declares the identity — locally read
from disk, remotely through one small GitHub Contents-API request per
location (never a repo tarball). Because the catalog never names a
component, no catalog/component identity conflict can exist.
"""

from __future__ import annotations

import pytest
from conftest import make_source
from y5n.apps.yak.resolver.catalog import CatalogError, build_index


def test_identity_comes_from_each_locations_component_yml(tmp_path):
    """build_index reads each location's identity from .yak/component.yml."""
    make_source(tmp_path, {"a": "packs/a", "b": "packs/b"})
    (tmp_path / "packs/a" / ".yak" / "component.yml").write_text(
        "name: a\nversion: 1.2.3\n"
    )
    index = build_index([str(tmp_path)], tmp_path)
    assert set(index.components) == {"a", "b"}
    catalog, ref = index.resolve("a")
    assert catalog.spec == str(tmp_path)
    assert ref.location == "packs/a"


def test_location_without_component_yml_fails_clearly(tmp_path):
    """A listed location that is not a component root violates the catalog."""
    make_source(tmp_path, {"a": "packs/a"})
    (tmp_path / "packs/a" / ".yak" / "component.yml").unlink()
    with pytest.raises(CatalogError, match="component.yml"):
        build_index([str(tmp_path)], tmp_path)


def test_components_must_be_a_list(tmp_path):
    """The old name-keyed mapping shape is rejected, not half-parsed."""
    (tmp_path / "catalog.yml").write_text(
        "components:\n  a:\n    location: a\n"
    )
    with pytest.raises(CatalogError, match="list of locations"):
        build_index([str(tmp_path)], tmp_path)


def test_each_component_needs_a_location(tmp_path):
    (tmp_path / "catalog.yml").write_text("components:\n  - nonsense\n")
    with pytest.raises(CatalogError, match="location"):
        build_index([str(tmp_path)], tmp_path)


def test_extra_fields_are_ignored(tmp_path):
    """release:/distribution: fields are dead config — never interpreted."""
    make_source(tmp_path, {"a": "packs/a"})
    catalog_file = tmp_path / "catalog.yml"
    catalog_file.write_text(
        "components:\n"
        "  - location: packs/a\n"
        "    release: a-v0.9.0\n"
        "    distribution: github:acme/elsewhere\n"
    )
    index = build_index([str(tmp_path)], tmp_path)
    catalog, ref = index.resolve("a")
    assert catalog.spec == str(tmp_path)
    assert ref.location == "packs/a"


def test_first_hit_wins_by_identity(tmp_path):
    """The same identity from two sources resolves to the first source."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_source(first, {"a": "packs/a", "mine": "packs/mine"})
    make_source(second, {"a": "other/a"})
    (second / "other" / "a" / ".yak" / "component.yml").write_text(
        "name: a\nversion: 9.9.9\n"
    )

    index = build_index([str(first), str(second)], tmp_path)
    catalog, ref = index.resolve("a")
    assert catalog.spec == str(first)
    assert ref.location == "packs/a"  # never overridden by the later source


def test_remote_discovery_fetches_component_yml_per_location(monkeypatch, tmp_path):
    """A remote catalog resolves identities via Contents API — one small
    request per location, no repo tarball."""
    import y5n.apps.yak.resolver.catalog as cat

    catalog_yml = (
        "components:\n"
        "  - location: packs/a\n"
        "  - location: packs/b\n"
    )
    responses = {
        "catalog.yml": catalog_yml.encode(),
        "packs/a/.yak/component.yml": b"name: a\nversion: 1.0.0\n",
        "packs/b/.yak/component.yml": b"name: b\nversion: 1.0.0\n",
    }
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
    component_requests = [k for k in requested if k != "catalog.yml"]
    assert sorted(component_requests) == [
        "packs/a/.yak/component.yml",
        "packs/b/.yak/component.yml",
    ]
    # Each request is a single manifest — never a repository tarball.
    assert not any("tar.gz" in r for r in requested)


def test_remote_location_without_component_yml_fails(monkeypatch, tmp_path):
    import y5n.apps.yak.resolver.catalog as cat

    responses = {
        "catalog.yml": b"components:\n  - location: packs/x\n",
    }

    def fake_urlopen(req):
        url = req.full_url
        key = url.split("/contents/", 1)[1]
        body = responses.get(key)
        if body is None:
            raise OSError(f"not found: {key}")

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
    with pytest.raises(CatalogError, match="cannot fetch|component.yml"):
        build_index(["github:acme/multi"], tmp_path)