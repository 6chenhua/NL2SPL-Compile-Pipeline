"""R8.1 ConstructEdge / ConstructGraph snapshot and dedup tests."""

from __future__ import annotations

from nl2spl.compiler.irs.graph import ConstructEdge, ConstructGraph


class TestConstructEdgeKey:
    """Edge key determinism and span-order independence."""

    def test_edge_key_deterministic(self) -> None:
        """Same edge produces same key across calls."""
        edge = ConstructEdge(
            from_id="a", to_id="b", edge_type="contains",
            source_span_ids=["s2", "s1"],
        )
        assert edge.key() == edge.key()

    def test_edge_key_different_by_type(self) -> None:
        """Different edge_type produces different key."""
        e1 = ConstructEdge(from_id="a", to_id="b", edge_type="contains")
        e2 = ConstructEdge(from_id="a", to_id="b", edge_type="produces")
        assert e1.key() != e2.key()

    def test_edge_key_different_by_target(self) -> None:
        """Different to_id produces different key."""
        e1 = ConstructEdge(from_id="a", to_id="b", edge_type="contains")
        e2 = ConstructEdge(from_id="a", to_id="c", edge_type="contains")
        assert e1.key() != e2.key()

    def test_edge_key_span_order_independent(self) -> None:
        """source_span_ids order does not affect key."""
        e1 = ConstructEdge(
            from_id="a", to_id="b", edge_type="contains",
            source_span_ids=["s1", "s2"],
        )
        e2 = ConstructEdge(
            from_id="a", to_id="b", edge_type="contains",
            source_span_ids=["s2", "s1"],
        )
        assert e1.key() == e2.key()


class TestConstructEdgeSnapshot:
    """Edge snapshot determinism."""

    def test_edge_snapshot_deterministic(self) -> None:
        """to_snapshot() returns stable dict."""
        edge = ConstructEdge(
            from_id="a", to_id="b", edge_type="contains",
            source_span_ids=["s2", "s1"],
            metadata={"z": 1, "a": 2},
        )
        snap1 = edge.to_snapshot()
        snap2 = edge.to_snapshot()
        assert snap1 == snap2
        # Keys are sorted
        assert snap1["source_span_ids"] == ["s1", "s2"]
        assert list(snap1["metadata"].keys()) == ["a", "z"]

    def test_edge_snapshot_contains_all_fields(self) -> None:
        """Snapshot includes all edge fields."""
        edge = ConstructEdge(
            from_id="x", to_id="y", edge_type="invokes",
            source_span_ids=["s1"],
            metadata={"key": "val"},
        )
        snap = edge.to_snapshot()
        assert snap["edge_type"] == "invokes"
        assert snap["from_id"] == "x"
        assert snap["to_id"] == "y"
        assert snap["source_span_ids"] == ["s1"]
        assert snap["metadata"] == {"key": "val"}


class TestConstructGraphHelpers:
    """Graph add, dedup, and snapshot sorting."""

    def test_add_edge_adds_nodes(self) -> None:
        """add_edge ensures both endpoints are in nodes."""
        graph = ConstructGraph()
        graph.add_edge(ConstructEdge(from_id="a", to_id="b", edge_type="contains"))
        assert "a" in graph.nodes
        assert "b" in graph.nodes

    def test_add_node_no_duplicate(self) -> None:
        """add_node does not add duplicates."""
        graph = ConstructGraph()
        graph.add_node("a")
        graph.add_node("a")
        assert graph.nodes.count("a") == 1

    def test_dedup_removes_duplicates(self) -> None:
        """deduped() removes edges with same key."""
        graph = ConstructGraph(edges=[
            ConstructEdge(from_id="a", to_id="b", edge_type="contains"),
            ConstructEdge(from_id="a", to_id="b", edge_type="contains"),
        ])
        deduped = graph.deduped()
        assert len(deduped.edges) == 1

    def test_dedup_preserves_different_edges(self) -> None:
        """deduped() keeps edges with different keys."""
        graph = ConstructGraph(edges=[
            ConstructEdge(from_id="a", to_id="b", edge_type="contains"),
            ConstructEdge(from_id="a", to_id="b", edge_type="produces"),
            ConstructEdge(from_id="a", to_id="c", edge_type="contains"),
        ])
        deduped = graph.deduped()
        assert len(deduped.edges) == 3

    def test_edge_snapshots_sorted(self) -> None:
        """edge_snapshots() returns sorted by (edge_type, from_id, to_id)."""
        graph = ConstructGraph(edges=[
            ConstructEdge(from_id="z", to_id="a", edge_type="produces"),
            ConstructEdge(from_id="a", to_id="b", edge_type="contains"),
            ConstructEdge(from_id="a", to_id="c", edge_type="contains"),
        ])
        snaps = graph.edge_snapshots()
        assert len(snaps) == 3
        # Sorted: contains < produces; within contains: a->b < a->c
        assert snaps[0]["edge_type"] == "contains"
        assert snaps[0]["to_id"] == "b"
        assert snaps[1]["edge_type"] == "contains"
        assert snaps[1]["to_id"] == "c"
        assert snaps[2]["edge_type"] == "produces"
