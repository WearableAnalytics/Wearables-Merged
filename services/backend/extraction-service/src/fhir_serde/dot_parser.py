from __future__ import annotations


class Node:
    def __init__(self, name: str):
        self.name = name
        self.successor: list[Node] = []
        self.predecessor: list[Node] = []

class Graph:
    def __init__(self, name: str, nodes: dict[str, Node]):
        self.name = name
        self.nodes = nodes


def parse_graph(raw_graph: str, category_name: str) -> Graph:

    start = raw_graph.index("{")
    end = raw_graph.index("}")
    formatted = raw_graph[start+1:end]

    node_names = get_nodes(formatted)

    nodes = build_dependencies(node_names, formatted)

    return Graph(category_name, nodes)

def get_nodes(raw_graph: str) -> dict[str, Node]:
    nodes: dict[str, Node] = {}

    lines = raw_graph.splitlines()
    for line in lines:
        if line.find("->") == -1 and len(line.strip()) > 0:
            line = line.strip().removesuffix(";")
            new_node = Node(line)
            nodes[line] = new_node
            # print(f"appended line to nodes: {line}")
        else:
            continue

    return nodes


def build_dependencies(nodes: dict[str, Node], raw_graph: str) -> dict[str, Node]:

    lines = raw_graph.splitlines()

    for line in lines:
        if line.find("->") != -1:
            dependency = line.split(" -> ")
            if len(dependency) != 2:
                raise RuntimeError("dependency in graph is malformed")

            pre = dependency[0].strip()
            post = dependency[1].strip().removesuffix(";")

            if nodes[pre] is None or nodes[post] is None:
                raise RuntimeError(f"there is a dependency with a non-existent node; '{pre}' or '{post}'")

            pre_node = nodes[pre]
            post_node = nodes[post]

            pre_node.successor.append(post_node)
            post_node.predecessor.append(pre_node)

    return nodes


def get_node_from_list(node_list: list[Node], name: str) -> Node | None:

    for n in node_list:
        if n.name == name:
            return n

    return None