"""Expected and observed circuit graphs.

Nodes are template terminals, board pins, breadboard holes and breadboard
strips. Edges are electrical connections. The observed graph is built ONLY
from observations whose status is ``confirmed`` or ``corrected``; proposals
and rejected observations never contribute an edge. Every node and edge
records where it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from .catalog import (
    Catalog,
    hole_name,
    normalize_board_pin,
    parse_hole,
    strip_id,
    strip_label,
    strip_rule_id,
)
from .schemas import (
    BreadboardModel,
    CircuitGraphData,
    CircuitTemplate,
    Connection,
    Endpoint,
    GraphEdge,
    GraphNode,
    Observation,
)

CONFIRMED_STATES = ("confirmed", "corrected")
BOARD_REF = "BOARD"


def is_confirmed(obs: Observation) -> bool:
    return obs.status in CONFIRMED_STATES


def provenance(obs: Observation) -> str:
    """Compact origin tag, e.g. ``gemma:confirmed`` or ``user:corrected``."""
    return f"{obs.source}:{obs.status}"


# ---------------------------------------------------------------------------
# Expected graph
# ---------------------------------------------------------------------------


def build_expected_graph(tpl: CircuitTemplate) -> tuple[nx.Graph, CircuitGraphData]:
    g = nx.Graph()
    nodes: list[GraphNode] = []
    for n in tpl.expected_nodes:
        kind = "board_pin" if n.instance == BOARD_REF else "terminal"
        g.add_node(n.id, kind=kind, label=n.label)
        nodes.append(GraphNode(id=n.id, kind=kind, label=n.label, sources=[f"template:{tpl.id}"]))
    edges: list[GraphEdge] = []
    for e in tpl.expected_edges:
        g.add_edge(e.a, e.b, id=e.id, kind="expected")
        edges.append(
            GraphEdge(id=e.id, a=e.a, b=e.b, kind="expected", sources=[f"template:{tpl.id}", f"rule:{e.rule_id}"])
        )
    return g, CircuitGraphData(nodes=nodes, edges=edges, nets=_terminal_nets(g))


def _terminal_nets(g: nx.Graph) -> list[list[str]]:
    nets = []
    for comp in nx.connected_components(g):
        terms = sorted(n for n in comp if g.nodes[n]["kind"] in ("terminal", "board_pin"))
        if len(terms) >= 2:
            nets.append(terms)
    return sorted(nets)


# ---------------------------------------------------------------------------
# Observed graph
# ---------------------------------------------------------------------------


@dataclass
class GraphIssue:
    """Something confirmed that the MVP cannot check or cannot interpret."""

    kind: str  # unsupported_endpoint | unknown_part | unmapped_component | bad_hole | unknown_pin | extra_component
    message: str
    observation_ids: list[str]
    holes: list[str] = field(default_factory=list)


@dataclass
class ObservedBuild:
    graph: nx.Graph
    data: CircuitGraphData
    connections: list[Connection]
    issues: list[GraphIssue]
    component_obs: dict[str, Observation]  # template instance ref -> confirmed observation
    node_obs: dict[str, list[str]]  # node id -> observation ids that touch it


def build_observed_graph(
    tpl: CircuitTemplate, catalog: Catalog, observations: list[Observation]
) -> ObservedBuild:
    board = catalog.breadboards[tpl.breadboard_model_id]
    board_part = catalog.parts[tpl.supported_board_id]
    g = nx.Graph()
    edges: list[GraphEdge] = []
    connections: list[Connection] = []
    issues: list[GraphIssue] = []
    component_obs: dict[str, Observation] = {}
    node_obs: dict[str, list[str]] = {}
    counters = {"e": 0, "c": 0}

    def touch(node: str, obs: Observation) -> None:
        node_obs.setdefault(node, [])
        if obs.id not in node_obs[node]:
            node_obs[node].append(obs.id)
        srcs: list[str] = g.nodes[node].setdefault("sources", [])
        tag = provenance(obs)
        if tag not in srcs:
            srcs.append(tag)

    def add_node(node: str, kind: str, label: str) -> None:
        if node not in g:
            g.add_node(node, kind=kind, label=label, sources=[])

    def add_edge(a: str, b: str, kind: str, src: list[str], obs_ids: list[str]) -> str:
        counters["e"] += 1
        eid = f"o{counters['e']}"
        if g.has_edge(a, b):
            # Parallel evidence: keep the first id, merge provenance.
            data = g.edges[a, b]
            for s in src:
                if s not in data["sources"]:
                    data["sources"].append(s)
            for o in obs_ids:
                if o not in data["observation_ids"]:
                    data["observation_ids"].append(o)
            return data["id"]
        g.add_edge(a, b, id=eid, kind=kind, sources=list(src), observation_ids=list(obs_ids))
        return eid

    def resolve_endpoint(ep: Endpoint, obs: Observation, what: str) -> str | None:
        """Turn an endpoint into a graph node id, or record why it cannot be used."""
        if ep.kind == "breadboard_hole":
            parsed = parse_hole(ep.hole, board)
            if not parsed:
                issues.append(GraphIssue("bad_hole", f"{what}: '{ep.hole}' is not a hole on the supported breadboard.", [obs.id]))
                return None
            col, row = parsed
            hole = hole_name(col, row)
            hnode = f"hole:{hole}"
            snode = strip_id(col, row, board)
            add_node(hnode, "hole", f"hole {hole}")
            add_node(snode, "strip", strip_label(snode))
            touch(hnode, obs)
            touch(snode, obs)
            add_edge(hnode, snode, "breadboard_rule", [f"breadboard_model:{board.id}", f"rule:{strip_rule_id(col, board)}"], [obs.id])
            return hnode
        if ep.kind == "board_pin":
            pin = normalize_board_pin(ep.board_pin, board_part)
            if not pin:
                issues.append(
                    GraphIssue(
                        "unknown_pin",
                        f"{what}: board pin '{ep.board_pin}' is not in the verified catalog for {board_part.display_name}, so it is not checked.",
                        [obs.id],
                    )
                )
                return None
            node = f"{BOARD_REF}.{pin}"
            add_node(node, "board_pin", f"Arduino {pin}")
            touch(node, obs)
            return node
        reason = {
            "power_rail": "a breadboard power rail (rails are not modelled in this MVP)",
            "off_grid": "a point outside the calibrated grid",
            "unknown": "an endpoint that could not be identified",
        }[ep.kind]
        issues.append(GraphIssue("unsupported_endpoint", f"{what} ends at {reason}; this connection is NOT CHECKED.", [obs.id]))
        return None

    instances_by_part: dict[str, list[str]] = {}
    for inst in tpl.instances:
        instances_by_part.setdefault(inst.part_id, []).append(inst.ref)

    for obs in observations:
        if not is_confirmed(obs):
            continue
        cand = obs.candidate_part_or_endpoint
        tag = provenance(obs)

        if obs.observation_type == "wire":
            a_ep, b_ep = cand.endpoints.get("end_a"), cand.endpoints.get("end_b")
            if not a_ep or not b_ep:
                issues.append(GraphIssue("unsupported_endpoint", f"{obs.display_name or 'A wire'} is missing an endpoint; NOT CHECKED.", [obs.id]))
                continue
            na = resolve_endpoint(a_ep, obs, obs.display_name or "Wire end A")
            nb = resolve_endpoint(b_ep, obs, obs.display_name or "Wire end B")
            if na and nb:
                eid = add_edge(na, nb, "wire", [tag], [obs.id])
                counters["c"] += 1
                connections.append(
                    Connection(
                        id=f"c{counters['c']}",
                        source_terminal=na,
                        destination_terminal=nb,
                        source_observation_ids=[obs.id],
                        confirmation_status="corrected" if obs.status == "corrected" else "confirmed",
                        kind="wire",
                        description=f"{g.nodes[na]['label']} ⟷ {g.nodes[nb]['label']} via jumper wire",
                    )
                )
            continue

        if obs.observation_type == "component":
            part = catalog.part(cand.part_id)
            if part is None:
                issues.append(
                    GraphIssue(
                        "unknown_part",
                        f"{obs.display_name or cand.kind_hint or 'A component'} is not in the supported catalog; its connections are NOT CHECKED.",
                        [obs.id],
                    )
                )
                continue
            ref = cand.template_ref
            if ref is None:
                candidates = instances_by_part.get(part.id, [])
                ref = candidates[0] if len(candidates) == 1 else None
            if ref is None or tpl.instance(ref) is None or tpl.instance(ref).part_id != part.id:
                issues.append(
                    GraphIssue(
                        "extra_component",
                        f"{part.display_name} does not correspond to any part of this template; its connections are NOT CHECKED.",
                        [obs.id],
                    )
                )
                continue
            if ref in component_obs:
                issues.append(
                    GraphIssue("extra_component", f"A second {part.display_name} was confirmed for {ref}; only the first is used.", [obs.id])
                )
                continue
            component_obs[ref] = obs
            for term in part.terminal_names:
                ep = cand.endpoints.get(term)
                if ep is None:
                    issues.append(GraphIssue("unsupported_endpoint", f"{ref} {term}: no endpoint given; NOT CHECKED.", [obs.id]))
                    continue
                hole_node = resolve_endpoint(ep, obs, f"{ref} {term}")
                tnode = f"{ref}.{term}"
                add_node(tnode, "terminal", f"{ref} {_term_label(part.kind, term)}")
                touch(tnode, obs)
                if hole_node:
                    add_edge(tnode, hole_node, "component_lead", [tag], [obs.id])
                    counters["c"] += 1
                    connections.append(
                        Connection(
                            id=f"c{counters['c']}",
                            source_terminal=tnode,
                            destination_terminal=hole_node,
                            source_observation_ids=[obs.id],
                            confirmation_status="corrected" if obs.status == "corrected" else "confirmed",
                            kind="component_lead",
                            description=f"{g.nodes[tnode]['label']} inserted at {g.nodes[hole_node]['label']}",
                        )
                    )

    nodes = [
        GraphNode(id=n, kind=d["kind"], label=d["label"], sources=list(d.get("sources", [])))
        for n, d in g.nodes(data=True)
    ]
    gedges = [
        GraphEdge(id=d["id"], a=a, b=b, kind=d["kind"], sources=list(d["sources"]), observation_ids=list(d["observation_ids"]))
        for a, b, d in g.edges(data=True)
    ]
    data = CircuitGraphData(nodes=nodes, edges=gedges, nets=_terminal_nets(g))
    return ObservedBuild(g, data, connections, issues, component_obs, node_obs)


def _term_label(kind: str, term: str) -> str:
    if kind == "resistor":
        return f"lead {term}"
    if kind == "led":
        return {"anode": "anode (+)", "cathode": "cathode (−)"}.get(term, term)
    return term


def describe_path(g: nx.Graph, a: str, b: str) -> str:
    """Human-readable shortest path between two nodes, e.g. 'R1 lead 1 → row 10 (a–e) → …'."""
    try:
        path = nx.shortest_path(g, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return "not connected"
    labels = []
    for n in path:
        if g.nodes[n]["kind"] == "hole":
            continue  # holes are implied by their strip; keep the text short
        labels.append(g.nodes[n]["label"])
    return " → ".join(labels)


def strips_in_component(g: nx.Graph, node: str) -> list[str]:
    if node not in g:
        return []
    return sorted(n for n in nx.node_connected_component(g, node) if g.nodes[n]["kind"] == "strip")


def holes_in_component(g: nx.Graph, node: str) -> list[str]:
    if node not in g:
        return []
    return sorted(n.split(":", 1)[1] for n in nx.node_connected_component(g, node) if g.nodes[n]["kind"] == "hole")


def parse_strip(strip: str) -> tuple[int, str]:
    body = strip.split(":", 1)[1]
    return int(body[:-1]), body[-1]
