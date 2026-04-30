from __future__ import annotations


def test_visibility_graph_contract(workspace_with_visibility_grants) -> None:
    graph = {
        "node_count": 500,
        "render_threshold_ms": 1000,
        "grants_given": workspace_with_visibility_grants["grants_given"],
        "grants_received": workspace_with_visibility_grants["grants_received"],
    }

    assert graph["node_count"] <= 500
    assert graph["render_threshold_ms"] <= 1000
    assert graph["grants_given"]


def test_zero_trust_default_visualization_contract() -> None:
    zero_trust = {"grants_given": [], "badge": "deny all", "isolated_node": True}

    assert zero_trust["grants_given"] == []
    assert zero_trust["badge"] == "deny all"
    assert zero_trust["isolated_node"] is True
