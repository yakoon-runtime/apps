"""Bundle support (ADR-21): catalogs declare bundles, the index resolves them.

A bundle is a name → list of component names. Bundles are global: the
merged index holds them with first-hit-wins precedence, exactly like
components. A bundle names components only — never other bundles, and
resolution of its members is an install-time concern, not a parse error.
"""

from __future__ import annotations

import pytest
from conftest import make_source
from y5n.apps.yak.resolver.catalog import CatalogError, build_index


def _index(root, **kwargs):
    make_source(root, **kwargs)
    return build_index([str(root)], root)


def test_catalog_parses_bundles(tmp_path):
    index = _index(tmp_path, bundles={"runtime": ["a", "b", "c"]})
    hit = index.resolve_bundle("runtime")
    assert hit is not None
    catalog, members = hit
    assert members == ("a", "b", "c")
    assert catalog.spec == str(tmp_path)
    assert index.resolve_bundle("missing") is None


def test_bundle_first_hit_wins(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_source(first, bundles={"runtime": ["a"]})
    make_source(second, bundles={"runtime": ["z"]})

    index = build_index([str(first), str(second)], tmp_path)
    hit = index.resolve_bundle("runtime")
    assert hit is not None
    catalog, members = hit
    assert members == ("a",)
    assert catalog.spec == str(first)


def test_bundle_members_are_not_resolved_at_parse_time(tmp_path):
    """A bundle names components; whether they resolve is install-time."""
    index = _index(tmp_path, bundles={"runtime": ["no-such-component"]})
    assert index.resolve_bundle("runtime") is not None


def test_bundle_and_component_namespaces_are_separate(tmp_path):
    index = _index(
        tmp_path,
        components={"runtime": {"location": "packs/runtime"}},
        bundles={"runtime": ["a"]},
    )
    assert index.resolve("runtime") is not None
    assert index.resolve_bundle("runtime") is not None


def test_bundle_must_be_a_mapping(tmp_path):
    make_source(tmp_path)
    catalog = tmp_path / "catalog.yml"
    catalog.write_text("bundles:\n  - runtime\n")
    with pytest.raises(CatalogError, match="'bundles' must be a mapping"):
        build_index([str(tmp_path)], tmp_path)


def test_bundle_must_be_a_list(tmp_path):
    make_source(tmp_path)
    catalog = tmp_path / "catalog.yml"
    catalog.write_text("bundles:\n  runtime: nope\n")
    with pytest.raises(CatalogError, match="bundle 'runtime'"):
        build_index([str(tmp_path)], tmp_path)


def test_bundle_members_must_be_strings(tmp_path):
    make_source(tmp_path)
    catalog = tmp_path / "catalog.yml"
    catalog.write_text("bundles:\n  runtime:\n    - 42\n")
    with pytest.raises(CatalogError, match="bundle 'runtime'"):
        build_index([str(tmp_path)], tmp_path)
