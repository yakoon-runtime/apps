from __future__ import annotations

from y5n.base.nodes import NodeFactory, SpaceFactory, provide

from .commands import contact_add, contact_delete, contact_edit, contact_list, contact_show


def setup(factory: SpaceFactory) -> None:
    space = factory.ns("crm")

    space.add("contact-add", contact_add.run, help="Create a new contact")
    space.add("contact-list", contact_list.run, help="List all contacts")
    space.add("contact-show", contact_show.run, help="Show contact details")
    space.add("contact-edit", contact_edit.run, help="Edit a contact")
    space.add("contact-delete", contact_delete.run, help="Delete a contact")
