"""Server graph admission: one bounded path selected by typed conditions."""

from database.repositories.exceptions import InvalidStateTransitionError


class GraphRejected(InvalidStateTransitionError):
    def __init__(self, subject, code):
        self.issues = [{"subject": subject, "code": code}]
        super().__init__(code)


def reject(subject, code):
    raise GraphRejected(subject, code)


def validate_graph(graph):
    nodes = {node.id: node for node in graph.nodes}
    if len(nodes) != len(graph.nodes) or len({e.id for e in graph.edges}) != len(
        graph.edges
    ):
        reject("graph", "duplicate_identity")
    starts = [n.id for n in graph.nodes if n.kind == "start"]
    ends = [n.id for n in graph.nodes if n.kind == "end"]
    reviews = [n.id for n in graph.nodes if n.kind == "review"]
    if len(starts) != 1 or len(ends) != 1 or len(reviews) != 1:
        reject("graph", "one_start_end_review_required")
    if not 1 <= sum(n.kind == "agent" for n in graph.nodes) <= 8:
        reject("graph", "task_count_limit")
    outgoing, incoming = {id: [] for id in nodes}, {id: [] for id in nodes}
    for edge in graph.edges:
        if edge.source not in nodes or edge.target not in nodes:
            reject(edge.id, "missing_node")
        source, target = nodes[edge.source], nodes[edge.target]
        if source.output_schema != target.input_schema:
            reject(edge.id, "incompatible_schema")
        if edge.source_port not in (
            {"yes", "no"} if source.kind == "condition" else {"value"}
        ):
            reject(edge.id, "invalid_port")
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)
    for node in graph.nodes:
        ports = [e.source_port for e in outgoing[node.id]]
        expected = (
            []
            if node.kind == "end"
            else ["yes", "no"]
            if node.kind == "condition"
            else ["value"]
        )
        if sorted(ports) != sorted(expected):
            reject(node.id, "bounded_ports_required")
        if (node.kind == "start" and incoming[node.id]) or (
            node.kind != "start" and not incoming[node.id]
        ):
            reject(node.id, "orphan_or_invalid_start")
    seen, active = set(), set()

    def walk(id, reviewed=False, depth=0):
        if id in active:
            reject(id, "cycle")
        if depth > 24:
            reject(id, "depth_limit")
        active.add(id)
        seen.add(id)
        reviewed = reviewed or nodes[id].kind == "review"
        if nodes[id].kind == "end" and not reviewed:
            reject(id, "review_bypass")
        for edge in outgoing[id]:
            walk(edge.target, reviewed, depth + 1)
        active.remove(id)

    walk(starts[0])
    if seen != nodes.keys():
        reject("graph", "unreachable_node")
    if outgoing[reviews[0]][0].target != ends[0]:
        reject(reviews[0], "review_must_precede_end")
    if nodes[starts[0]].output_schema != "text":
        reject(starts[0], "input_requires_text")
    return starts[0], outgoing
