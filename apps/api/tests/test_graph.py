from __future__ import annotations

from recallgraph.graph.builder import deduplicate_nodes
from recallgraph.graph.models import GraphNode


def test_graph_node_deduplication_uses_stable_id() -> None:
    first = GraphNode(id="memory:1", type="memory", label="old", data={})
    replacement = GraphNode(id="memory:1", type="memory", label="new", data={})
    result = deduplicate_nodes([first, replacement])
    assert len(result) == 1
    assert result[0].label == "new"
