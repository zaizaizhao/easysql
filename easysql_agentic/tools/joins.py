"""Search one graph of scoped physical keys and Markdown-derived business joins."""

from __future__ import annotations

import asyncio
from itertools import islice
from typing import Any

import networkx as nx

from easysql_agentic.knowledge.repository import WikiRepository
from easysql_agentic.tools.catalog import Catalog


async def find_paths(
    tables: list[str],
    catalog: Catalog,
    repository: WikiRepository,
    max_hops: int = 4,
) -> dict[str, Any]:
    tables = list(dict.fromkeys(catalog.require_table(table).id for table in tables))
    if not 2 <= len(tables) <= 8 or not 1 <= max_hops <= 4:
        raise ValueError("Select 2-8 tables and a path depth of 1-4")
    pages = await repository.pages(db_names=catalog.scope.names, kind="join_rule", limit=5000)
    documented = [
        {
            **page.join_rule.model_dump(),
            "id": page.id,
            "kind": "documented_join",
            "source_key": page.source_key,
            "source_quote": page.source_quote,
            "revision": page.revision,
        }
        for page in pages
        if page.join_rule
    ]
    graph = nx.Graph()
    graph.add_nodes_from(tables)
    frontier = set(tables)
    visited: set[str] = set()
    warnings = []
    for _ in range(max_hops):
        if not frontier or len(visited) > 200:
            break
        edges = [
            edge
            for edge in documented
            if edge["source_table"] in frontier or edge["target_table"] in frontier
        ]
        try:
            edges.extend(await asyncio.to_thread(catalog.physical_edges, sorted(frontier)))
        except Exception:
            # Documented relations remain usable even while a schema index is rebuilding.
            warnings.append(
                "Physical graph unavailable; paths contain document-backed relations only"
            )
        next_frontier = set()
        for edge in edges:
            source, target = edge["source_table"], edge["target_table"]
            catalog.require_table(source)
            catalog.require_table(target)
            if not graph.has_edge(source, target):
                graph.add_edge(source, target, rules={})
            graph[source][target]["rules"][edge["id"]] = edge
            next_frontier.update((source, target))
        visited.update(frontier)
        frontier = next_frontier - visited
    paths = []
    missing = []
    for target in tables[1:]:
        if not nx.has_path(graph, tables[0], target):
            missing.append(target)
            continue
        for nodes in islice(nx.all_shortest_paths(graph, tables[0], target), 3):
            if len(nodes) - 1 > max_hops:
                missing.append(target)
                continue
            paths.append(
                {
                    "tables": nodes,
                    "steps": [
                        {"from": a, "to": b, "alternatives": list(graph[a][b]["rules"].values())}
                        for a, b in zip(nodes, nodes[1:], strict=False)
                    ],
                }
            )
    return {
        "paths": paths,
        "unconnected_tables": sorted(set(missing)),
        "warnings": list(dict.fromkeys(warnings)),
        "instruction": "Choose rules by business grain and conditions; a shortest path alone is not proof of correctness",
    }
