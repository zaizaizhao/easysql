from __future__ import annotations

import asyncio
import subprocess
import sys
from types import SimpleNamespace

from easysql.federation import DatabaseScope
from easysql.models.schema import DatabaseMeta, ForeignKeyMeta
from easysql.writers.neo4j_writer import Neo4jSchemaWriter
from easysql_agentic.knowledge.models import WikiPage
from easysql_agentic.knowledge.service import WikiService
from easysql_agentic.tools.context import ContextTools
from tests.agentic.fakes import FakeCatalog, FakeExecutor
from tests.agentic.test_adk_runtime import settings


def test_progressive_read_requires_complete_page_and_changed_evidence_is_reloaded() -> None:
    class Repository:
        page = WikiPage(
            id="page",
            document_id="document",
            revision=1,
            source_key="source.md",
            source_line=1,
            db_names=["emr"],
            key="metric",
            domain="指标",
            kind="metric",
            title="完整口径",
            summary="正文分两次加载",
            body_md="规则。" * 4000,
            source_quote="规则。",
            table_ids=["emr.public.patient"],
        )

        async def pages(self, **kwargs):
            return [self.page]

    async def run():
        repo = Repository()
        executor = FakeExecutor()
        tools = ContextTools(
            DatabaseScope.resolve(settings(), db_names=["emr"]),
            WikiService(repo),
            catalog=FakeCatalog(),
            executor=executor,
        )
        await tools.get_table_schema("emr.public.patient")
        first = await tools.read_wiki_page("page")
        assert first["evidence_ready"] is False
        assert not (await tools.assess_context(True, [], ["page"], "ready"))["accepted"]
        second = await tools.read_wiki_page("page", first["next_offset"])
        assert second["evidence_ready"] is True
        assert (
            await tools.assess_context(True, [], ["page", "schema:emr.public.patient"], "ready")
        )["accepted"]
        repo.page = repo.page.model_copy(update={"revision": 2})
        outcome = await tools.submit_final_sql(
            "SELECT id FROM public.patient", "emr", SimpleNamespace(actions=SimpleNamespace())
        )
        assert outcome["status"] == "error"
        assert outcome["stale_page_ids"] == ["page"]
        assert not executor.requests

    asyncio.run(run())


def test_physical_composite_foreign_key_keeps_every_column_pair() -> None:
    calls = []

    class Transaction:
        def run(self, query, **kwargs):
            calls.append((query, kwargs))

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute_write(self, fn, *args):
            fn(Transaction(), *args)

    repository = SimpleNamespace(
        driver=SimpleNamespace(session=lambda **kwargs: Session()),
        database="neo4j",
        project_namespace="test",
    )
    meta = DatabaseMeta(
        name="emr",
        db_type="postgresql",
        host="localhost",
        port=5432,
        foreign_keys=[
            ForeignKeyMeta(
                constraint_name="fk_visit_patient",
                from_table="visit",
                from_column=name,
                to_table="patient",
                to_column=name,
            )
            for name in ["hospital_id", "patient_id"]
        ],
    )
    Neo4jSchemaWriter(repository).write_database(meta)
    relations = [kwargs for query, kwargs in calls if "r:FOREIGN_KEY" in query]
    assert len(relations) == 1
    assert relations[0]["from_columns"] == ["hospital_id", "patient_id"]
    assert relations[0]["to_columns"] == ["hospital_id", "patient_id"]


def test_independent_agent_runtime_does_not_import_langgraph() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import easysql_agentic.runtime; "
            "assert not any(name.startswith('langgraph') for name in sys.modules)",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
