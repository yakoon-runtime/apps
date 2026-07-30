from y5n.apps.yak.distribution.models import (
    Distribution,
    Mount,
    PackName,
    PackReference,
)

# PackReference is still used for sub-distribution references
from y5n.apps.yak.resolver.resolver import Resolver


def lookup(distributions: dict[str, Distribution]):

    def resolve(name: str) -> Distribution | None:
        return distributions.get(name)

    return resolve


def test_resolve_single_distribution():
    dist = Distribution(
        name="crm",
        version="1.0",
        mounts=[
            Mount(source="runtime", target="/"),
            Mount(source="system", target="/"),
            Mount(source="ident", target="/"),
            Mount(source="crm", target="/"),
        ],
    )
    resolver = Resolver(lookup({"crm": dist}))
    packs, tools = resolver.resolve(dist)

    assert packs == [
        PackName("runtime"),
        PackName("system"),
        PackName("ident"),
        PackName("crm"),
    ]


def test_resolve_nested_distributions():
    base = Distribution(
        name="base",
        version="1.0",
        mounts=[
            Mount(source="runtime", target="/"),
            Mount(source="system", target="/"),
        ],
    )
    crm = Distribution(
        name="crm",
        version="1.0",
        distributions=[PackReference(name=PackName("base"))],
        mounts=[
            Mount(source="ident", target="/"),
            Mount(source="crm", target="/"),
        ],
    )
    resolver = Resolver(lookup({"base": base, "crm": crm}))
    packs, tools = resolver.resolve(crm)

    assert packs == [
        PackName("runtime"),
        PackName("system"),
        PackName("ident"),
        PackName("crm"),
    ]


def test_resolve_deduplicates():
    a = Distribution(
        name="a",
        version="1.0",
        mounts=[
            Mount(source="shared", target="/"),
            Mount(source="a-only", target="/"),
        ],
    )
    b = Distribution(
        name="b",
        version="1.0",
        mounts=[
            Mount(source="shared", target="/"),
            Mount(source="b-only", target="/"),
        ],
    )
    combined = Distribution(
        name="combined",
        version="1.0",
        distributions=[
            PackReference(name=PackName("a")),
            PackReference(name=PackName("b")),
        ],
    )
    resolver = Resolver(lookup({"a": a, "b": b, "combined": combined}))
    packs, tools = resolver.resolve(combined)

    assert packs == [PackName("shared"), PackName("a-only"), PackName("b-only")]
