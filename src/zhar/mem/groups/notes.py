"""Built-in group: notes — supplemental information attached to primary nodes."""

from dataclasses import dataclass

from zhar.mem.group import GroupDef, NodeTypeDef


@dataclass
class NoteMeta:
    """Metadata for supplemental note nodes."""

    agent: str = ""
    target_ids: str = ""


GROUP = GroupDef(
    name="notes",
    node_types=[
        NodeTypeDef(
            name="note",
            meta_cls=NoteMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            current_statuses=["active"],
            memory_backed=True,
        )
    ],
)