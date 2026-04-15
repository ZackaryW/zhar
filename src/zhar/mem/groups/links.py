"""Built-in group: links — generic node-to-node traversal edges.

Node types
----------
node_link      A generic link edge between two existing nodes.
"""

from dataclasses import dataclass

from zhar.mem.group import GroupDef, NodeTypeDef


@dataclass
class NodeLinkMeta:
    """Metadata for a generic node-to-node link edge."""

    agent: str = ""
    from_id: str = ""
    to_id: str = ""
    rel_type: str = ""


GROUP = GroupDef(
    name="links",
    node_types=[
        NodeTypeDef(
            name="node_link",
            meta_cls=NodeLinkMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            current_statuses=["active"],
        )
    ],
)