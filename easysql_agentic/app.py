"""Run with: uvicorn easysql_agentic.app:app --port 8000.

Shares the API shell and persistence adapters; the default query runtime is ADK.
Set QUERY_BACKEND=langgraph only to run the historical implementation.
"""

from easysql_api.app import create_app

app = create_app()
