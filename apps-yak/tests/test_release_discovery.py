"""Release discovery contract — the catalog carries no version.

The repository's own release list is the version truth: a component
resolves to the tag of its highest published version that carries a valid
Yak artifact asset. Selection is pure and version-aware (``0.10.0`` beats
``0.9.0``); legacy and mislabeled releases are ignored.
"""

from __future__ import annotations

from y5n.apps.yak.resolver.catalog import _index_repo_releases


def _release(tag: str, assets: list[str]) -> dict:
    return {
        "tag_name": tag,
        "assets": [{"name": n, "digest": "sha256:x"} for n in assets],
    }


def test_discovers_highest_published_version_with_valid_asset():
    releases = [
        _release("y5n-runtime-api-v0.8.0", ["y5n-runtime-api.artifact.tar.gz"]),
        _release("y5n-runtime-api-v0.9.0", ["y5n-runtime-api.artifact.tar.gz"]),
        _release("y5n-runtime-api-v0.10.0", ["y5n-runtime-api.artifact.tar.gz"]),
        # A component asset under a wrong tag prefix does not count.
        _release(
            "legacy-y5n-runtime-api-v9.0.0", ["y5n-runtime-api.artifact.tar.gz"]
        ),
        # An asset not named after the component does not count.
        _release("y5n-runtime-api-v0.4.0", ["other.artifact.tar.gz"]),
        # Another component in the same repository resolves independently.
        _release("y5n-caps-root-v0.1.0", ["y5n-caps-root.artifact.tar.gz"]),
    ]
    index = _index_repo_releases(releases)

    assert index["y5n-runtime-api"] == ("y5n-runtime-api-v0.10.0", "sha256:x")
    assert index["y5n-caps-root"] == ("y5n-caps-root-v0.1.0", "sha256:x")
