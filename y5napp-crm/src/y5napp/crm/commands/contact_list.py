from __future__ import annotations

from y5n.base.nodes import NodeSpace
from y5n.base.runtime import Outcome, out
from y5n.api.ports import OnProject
from y5n.base.models.outcome import ProjectionHeader

from ..model import Contact


async def run(space: NodeSpace) -> AsyncGenerator[Outcome, None]:
    on_project = await space.ports.get(OnProject)

    store = space.node.space.store
    contacts: list[Contact] = []
    async for key in store.scan(prefix="crm/contact/"):
        doc = await store.get(key)
        if doc and doc.data:
            contacts.append(Contact(**doc.data))

    rows = []
    for c in contacts:
        rows.append({"name": c.name, "company": c.company, "email": c.email})

    projection = await on_project(
        name="crm/contact_list",
        lang=space.session.lang,
        state={
            "rows": rows,
            "total": len(contacts),
        },
    )

    yield out(projection)
