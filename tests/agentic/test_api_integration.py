from __future__ import annotations

import asyncio
import json
import uuid

import httpx
from fastapi import FastAPI
from google.adk.sessions import DatabaseSessionService

from easysql.federation import FederatedSqlExecutor
from easysql.infrastructure.data_plane_engine_registry import DataPlaneEngineRegistry
from easysql_agentic import api as wiki_api
from easysql_agentic import runtime as runtime_module
from easysql_agentic import service as service_module
from easysql_agentic.dependencies import get_wiki_service
from easysql_agentic.knowledge.models import JoinRule, WikiPageDraft
from easysql_agentic.knowledge.organizer import MarkdownOrganizer
from easysql_agentic.knowledge.repository import WikiRepository
from easysql_agentic.knowledge.service import WikiService
from easysql_agentic.runtime import AgentRuntime
from easysql_agentic.service import AdkQueryService
from easysql_agentic.tools import catalog as catalog_module
from easysql_agentic.tools.catalog import Catalog
from easysql_agentic.tools.context import ContextTools
from easysql_api.deps import get_query_service_dep, get_session_repository_dep
from easysql_api.infrastructure.db_manager import ControlPlaneDatabaseManager
from easysql_api.infrastructure.persistence.session_repository import SqlAlchemySessionRepository
from easysql_api.routers.query import router as query_router
from easysql_api.routers.sessions import router as session_router
from tests.agentic.fakes import ScriptedModel


def join_page(target: str) -> WikiPageDraft:
    source = f"emr.public.patient.mpi_id = {target}.public.patient.mpi_id"
    return WikiPageDraft(
        key=f"mpi-{target}",
        domain="医疗/跨库关联",
        kind="join_rule",
        title=f"EMR 与 {target} 患者关联",
        summary=f"按 MPI 关联 EMR 和 {target}",
        body_md=f"# 患者关联\n{source}",
        source_quote=source,
        join_rule=JoinRule(
            source_table="emr.public.patient",
            target_table=f"{target}.public.patient",
            column_pairs=[{"source": "mpi_id", "target": "mpi_id"}],
        ),
    )


class DocumentCatalog(Catalog):
    def physical_edges(self, table_ids):
        return []


def submission_steps(sql: str) -> list[dict]:
    return [
        *[
            {"tool": "get_table_schema", "args": {"table_id": f"{db}.public.patient"}}
            for db in ("emr", "pms", "rvs")
        ],
        {
            "tool": "assess_context",
            "args": {
                "sufficient": True,
                "missing": [],
                "rationale": "已核对患者标识、类型与关联粒度",
                "evidence_ids": [f"schema:{db}.public.patient" for db in ("emr", "pms", "rvs")],
            },
        },
        {"tool": "submit_final_sql", "args": {"sql": sql, "primary_db": "emr"}},
    ]


def test_markdown_upload_to_wiki_to_single_adk_agent_and_real_dblink(
    federated_settings, monkeypatch
) -> None:
    config = federated_settings.model_copy(
        update={
            "project_namespace": "api_test_" + uuid.uuid4().hex,
            "llm": federated_settings.llm.model_copy(update={"agent_max_iterations": 20}),
        }
    )
    monkeypatch.setattr(wiki_api, "get_settings", lambda: config)
    monkeypatch.setattr(service_module, "get_settings", lambda: config)
    monkeypatch.setattr(runtime_module, "get_settings", lambda: config)
    registry = DataPlaneEngineRegistry()
    monkeypatch.setattr(catalog_module, "get_data_plane_engine_registry", lambda: registry)

    async def run():
        manager = ControlPlaneDatabaseManager()
        manager.init_control_plane(config.postgres_uri)
        adk_sessions = DatabaseSessionService(db_engine=manager.get_engine())
        repo = WikiRepository(manager, config.project_namespace)
        pages = [join_page("pms"), join_page("rvs")]
        wiki = WikiService(
            repo,
            MarkdownOrganizer(
                ScriptedModel(
                    responses=[
                        {
                            "text": json.dumps(
                                {"pages": [page.model_dump() for page in pages]}, ensure_ascii=False
                            )
                        }
                    ]
                )
            ),
        )
        model = ScriptedModel(responses=[])
        runtime = AgentRuntime(adk_sessions, model)
        sql = """SELECT e.mpi_id,p.amount+r.amount AS total FROM public.patient e
        JOIN dblink('pms_conn', $$SELECT mpi_id,amount FROM public.patient$$) AS p(mpi_id text,amount integer) ON p.mpi_id=e.mpi_id
        JOIN dblink('rvs_conn', $$SELECT mpi_id,amount FROM public.patient$$) AS r(mpi_id text,amount integer) ON r.mpi_id=e.mpi_id"""
        session_repository = SqlAlchemySessionRepository(manager)
        service = AdkQueryService(
            session_repository,
            wiki=wiki,
            runtime=runtime,
            tools_factory=lambda scope, wiki: ContextTools(
                scope,
                wiki,
                catalog=DocumentCatalog(scope),
                executor=FederatedSqlExecutor(settings=config, registry=registry),
            ),
        )
        app = FastAPI()
        app.include_router(wiki_api.router, prefix="/api/v1")
        app.include_router(query_router, prefix="/api/v1")
        app.include_router(session_router, prefix="/api/v1")
        app.dependency_overrides[get_wiki_service] = lambda: wiki
        app.dependency_overrides[get_query_service_dep] = lambda: service
        app.dependency_overrides[get_session_repository_dep] = lambda: session_repository
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as client:
                uploaded = await client.post(
                    "/api/v1/knowledge/documents",
                    files={
                        "file": (
                            "join-rules.md",
                            "\n".join(page.source_quote for page in pages).encode(),
                            "text/markdown",
                        )
                    },
                    data={"db_names": '["emr","pms","rvs"]'},
                )
                assert uploaded.status_code == 200, uploaded.text
                assert uploaded.json()["page_count"] == 2
                document_id = uploaded.json()["id"]
                outline = (await client.get("/api/v1/knowledge/wiki")).json()
                assert outline["children"][0]["domain"] == "医疗"
                cards = (
                    await client.get("/api/v1/knowledge/pages", params={"domain": "医疗"})
                ).json()["pages"]
                assert all("body_md" not in card for card in cards)
                page_id = cards[0]["id"]
                assert (await client.get(f"/api/v1/knowledge/pages/{page_id}")).json()[
                    "source_quote"
                ]
                # All retrieval decisions below are ADK FunctionTool calls, not workflow nodes.
                model.responses.extend(
                    [
                        {"tool": "browse_wiki", "args": {}},
                        {"tool": "list_wiki_pages", "args": {"domain": "医疗/跨库关联"}},
                        *[
                            {"tool": "read_wiki_page", "args": {"page_id": card["id"]}}
                            for card in cards
                        ],
                        {
                            "tool": "find_join_paths",
                            "args": {
                                "table_ids": [
                                    "emr.public.patient",
                                    "pms.public.patient",
                                    "rvs.public.patient",
                                ]
                            },
                        },
                        *submission_steps(sql),
                    ]
                )
                response = await client.post(
                    "/api/v1/query",
                    json={
                        "question": "关联三个系统的患者金额",
                        "db_names": ["emr", "pms", "rvs"],
                        "stream": True,
                    },
                )
                assert response.status_code == 200
                events = [
                    json.loads(line[6:])
                    for line in response.text.splitlines()
                    if line.startswith("data: ")
                ]
                completed = next(event["data"] for event in events if event["event"] == "complete")
                assert completed["status"] == "completed", completed
                assert completed["validation_passed"]
                session_id = completed["session_id"]
                first_message = completed["message_id"]
                assert any(event["data"].get("tool") == "read_wiki_page" for event in events)
                persisted = await adk_sessions.get_session(
                    app_name=runtime.app_name, user_id=session_id, session_id=session_id
                )
                assert persisted and len(persisted.events) > 10

                model.responses.append(
                    {
                        "tool": "ask_clarification",
                        "args": {"questions": ["金额是否包含已退费记录？"]},
                    }
                )
                clarification = (
                    await client.post(
                        f"/api/v1/sessions/{session_id}/message",
                        json={
                            "question": "改为净金额",
                            "parent_message_id": first_message,
                        },
                    )
                ).json()
                assert clarification["status"] == "awaiting_clarify", clarification
                model.responses.extend(submission_steps(sql))
                resumed = (
                    await client.post(
                        f"/api/v1/query/{session_id}/continue", json={"answer": "包含"}
                    )
                ).json()
                assert resumed["status"] == "completed", resumed
                session = await session_repository.get(session_id)
                assert len(session.turns) == 2
                assert session.turns[-1].clarifications[-1].answer == "包含"

                model.responses.extend(submission_steps(sql))
                branch = (
                    await client.post(
                        f"/api/v1/sessions/{session_id}/branch",
                        json={
                            "from_message_id": first_message,
                            "question": "从第一轮重新统计",
                        },
                    )
                ).json()
                assert branch["status"] == "completed", branch
                assert branch["thread_id"] != session_id
                fork = await client.post(
                    f"/api/v1/sessions/{session_id}/fork",
                    json={
                        "from_message_id": first_message,
                        "turn_ids": ["turn-001"],
                    },
                )
                assert fork.status_code == 200, fork.text
                assert fork.json()["session_id"] != session_id
                # A new framework service reads the persisted ADK state without a process cache.
                reopened = DatabaseSessionService(db_engine=manager.get_engine())
                restored = await reopened.get_session(
                    app_name=runtime.app_name, user_id=session_id, session_id=session_id
                )
                assert restored and len(restored.events) >= len(persisted.events)
                await reopened.close()
                assert (
                    len(
                        (
                            await client.get(f"/api/v1/knowledge/documents/{document_id}/revisions")
                        ).json()["revisions"]
                    )
                    == 1
                )
                assert (
                    await client.delete(f"/api/v1/knowledge/documents/{document_id}")
                ).status_code == 200
                assert (await client.get(f"/api/v1/knowledge/pages/{page_id}")).status_code == 404
        finally:
            await adk_sessions.close()
            await manager.dispose()
            registry.dispose_all()

    asyncio.run(run())
