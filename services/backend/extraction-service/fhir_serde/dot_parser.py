from __future__ import annotations


class Node:
    def __init__(self, name: str):
        self.name = name
        self.successor: list[Node] = []
        self.predecessor: list[Node] = []

class Graph:
    def __init__(self, name: str, nodes: list[Node]):
        self.name = name
        self.nodes = nodes

def parse_file(graphs: str) -> list[Graph]:
    graph_list = graphs.split("&")

    built_graphs: list[Graph] = []

    for g in graph_list:
        name = get_category_name(g)

        if name is None:
            raise RuntimeError("missing category name")

        graph = parse_string(g, name)
        built_graphs.append(graph)


def get_category_name(g: str) -> str | None:
    lines = g.splitlines()
    for line in lines:
        if line.find("#") != -1:
            return line.removeprefix("#")

    return None


def parse_string(raw_graph: str, category_name: str) -> Graph:

    node_names = get_nodes(raw_graph)

    nodes = build_nodes(node_names, raw_graph)

    return Graph(category_name, nodes)


def get_nodes(raw_graph: str) -> list[str]:
    nodes = []

    lines = raw_graph.splitlines()
    for line in lines:
        if line.find("->") == -1 and line.find("{") == -1 and line.find("}") == -1:
            line = line.removesuffix(";")
            nodes.append(line)
        else:
            continue

    return nodes


def build_nodes(node_names: list[str], raw_graph: str) -> list[Node]:

    lines = raw_graph.splitlines()
    built_nodes: list[Node] = []

    for line in lines:
        if line.find("->") != -1:
            dependency = line.split(" -> ")
            if len(dependency) != 2:
                raise RuntimeError("dependency in graph is malformed")

            pre = dependency[0]
            post = dependency[1]

            if pre not in node_names or post not in node_names:
                raise RuntimeError("there is a dependency with a non-existent node")

            pre_node = get_node_from_list(built_nodes, pre)
            post_node = get_node_from_list(built_nodes, post)

            if pre_node is None:
                pre_node = Node(pre)

            if post_node is None:
                post_node = Node(post)

            pre_node.successor.append(post_node)
            post_node.predecessor.append(pre_node)

    return built_nodes


def get_node_from_list(node_list: list[Node], name: str) -> Node | None:

    for n in node_list:
        if n.name == name:
            return n

    return None