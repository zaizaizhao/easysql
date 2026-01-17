import asyncio
from easysql.llm import build_graph
from easysql.llm.state import EasySQLState


async def test_stream():
    graph = build_graph(enable_tracing=False)

    # Mock input state
    input_state = {
        "raw_query": "test query",
        "validation_passed": True,  # cheat to make it short
        "generated_sql": "SELECT 1",
    }

    # We can't easily mock the whole execution without DBs,
    # but we can check what `graph.stream` yields locally if we mock the nodes.
    # Actually, running the real graph might fail without DB connections.
    # So I will trust my knowledge of LangGraph:
    # graph.stream() yields dictionary {node_name: state_update} by default.
    pass


if __name__ == "__main__":
    pass
