from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from easysql_agentic.knowledge.models import WikiPageDraft
from easysql_agentic.knowledge.organizer import MarkdownOrganizer, markdown_chunks
from easysql_agentic.knowledge.repository import ResourceBusyError, WikiRepository
from easysql_agentic.knowledge.service import WikiService
from easysql_api.infrastructure.db_manager import ControlPlaneDatabaseManager
from tests.agentic.fakes import ScriptedModel


def draft(text: str, key: str = "mpi") -> WikiPageDraft:
    return WikiPageDraft(
        key=key,
        kind="term",
        title="MPI 患者身份",
        domain="医疗/患者身份",
        summary="跨库患者关联标识",
        body_md=text,
        source_quote=text,
        table_ids=["emr.public.patient"],
    )


class Organizer:
    def __init__(self):
        self.calls = 0
        self.fail = False

    async def organize(self, text, db_schemas, domains):
        self.calls += 1
        if self.fail:
            raise ValueError("Deliberate extraction failure")
        return [
            draft(line, f"page-{index}")
            for index, line in enumerate(text.splitlines())
            if line.strip()
        ]


def test_real_adk_structured_markdown_organization_and_chunk_coverage() -> None:
    markdown = "# 患者身份\nMPI 是跨库患者关联标识。"
    payload = {"pages": [draft("MPI 是跨库患者关联标识。").model_dump()]}
    model = ScriptedModel(
        responses=[
            {
                "thought": "I should organize the document before returning its JSON.",
                "text": json.dumps(payload, ensure_ascii=False),
            }
        ]
    )
    pages = asyncio.run(MarkdownOrganizer(model).organize(markdown, {"emr": "public"}, []))
    assert len(pages) == 1
    assert pages[0].source_quote in markdown
    source = "# A\n" + "文本" * 10000 + "\n# B\n末尾规则"
    chunks = markdown_chunks(source)
    assert "末尾规则" in chunks[-1]
    assert all(len(chunk) <= 14000 for chunk in chunks)


def test_atomic_incremental_updates_preserve_other_sources_and_old_revision_on_failure(
    postgres_uri,
) -> None:
    async def run():
        manager = ControlPlaneDatabaseManager()
        manager.init_control_plane(postgres_uri)
        repo = WikiRepository(manager, "wiki_test_" + uuid.uuid4().hex)
        organizer = Organizer()
        service = WikiService(repo, organizer)
        try:
            args = {"source_key": "patients.md", "db_schemas": {"emr": "public"}}
            first = await service.ingest(markdown="MPI 是共享标识。\n历史规则。", **args)
            assert first["revision"] == 1
            assert len(await repo.pages(db_names=["emr"])) == 2
            repeated = await service.ingest(markdown="MPI 是共享标识。\n历史规则。", **args)
            assert repeated["unchanged"] is True
            assert organizer.calls == 1
            await service.ingest(
                source_key="billing.md", markdown="金额单位为分。", db_schemas={"emr": "public"}
            )
            second = await service.ingest(markdown="MPI 新口径。", **args)
            assert second["revision"] == 2
            pages = await repo.pages(db_names=["emr"])
            assert {page.body_md for page in pages} == {"MPI 新口径。", "金额单位为分。"}
            organizer.fail = True
            with pytest.raises(ValueError):
                await service.ingest(markdown="失败的新版。", **args)
            assert (await repo.get_document("patients.md"))["revision"] == 2
            assert len(await repo.revisions(first["id"])) == 2
            assert await repo.pages(db_names=["pms"]) == []
            cards = await service.list_pages(["emr"], "医疗")
            assert all("body_md" not in card for card in cards["pages"])
            outline = await service.outline(["emr"])
            assert outline["children"] == [{"domain": "医疗", "page_count": 2}]
            result = await service.search("MPI", ["emr"])
            assert result["pages"]
            loaded = await service.read(result["pages"][0]["id"], ["emr"])
            assert loaded["body_md"] in {"MPI 新口径。", "金额单位为分。"}
            assert loaded["source_quote"] == loaded["body_md"]
            async with repo.lease("same-document"):
                with pytest.raises(ResourceBusyError):
                    async with repo.lease("same-document"):
                        pytest.fail("Concurrent lease incorrectly acquired")
            await repo.delete_document(first["id"])
            assert {page.source_key for page in await repo.pages()} == {"billing.md"}
        finally:
            await manager.dispose()

    asyncio.run(run())


def test_stale_vector_hits_cannot_resurrect_old_or_deleted_wiki_pages(postgres_uri) -> None:
    class Index:
        hits = []

        def search(self, query, db_names):
            return self.hits

    async def run():
        manager = ControlPlaneDatabaseManager()
        manager.init_control_plane(postgres_uri)
        repo = WikiRepository(manager, "wiki_vectors_" + uuid.uuid4().hex)
        service = WikiService(repo, Organizer())
        try:
            document = await service.ingest(
                source_key="source.md", markdown="旧定义。", db_schemas={"emr": "public"}
            )
            old_page = (await repo.pages())[0]
            await service.ingest(
                source_key="source.md", markdown="新定义。", db_schemas={"emr": "public"}
            )
            index = Index()
            index.hits = [{"id": old_page.id, "revision": old_page.revision}]
            service.index = index
            result = await service.search("unmatched-keyword", ["emr"])
            assert result["pages"] == []
            await repo.delete_document(document["id"])
            assert (await service.search("unmatched-keyword", ["emr"]))["pages"] == []
            service.index = None
            recreated = await service.ingest(
                source_key="source.md", markdown="重新建立的定义。", db_schemas={"emr": "public"}
            )
            assert recreated["id"] != document["id"]
            assert recreated["revision"] == 1
            service.index = index
            assert (await service.search("unmatched-keyword", ["emr"]))["pages"] == []
        finally:
            await manager.dispose()

    asyncio.run(run())


def test_index_failure_preserves_published_wiki_and_retry_uses_current_revision(
    postgres_uri,
) -> None:
    class Index:
        fail = True
        revisions = []

        def replace(self, document_id, revision, pages):
            if self.fail:
                raise ConnectionError("Index is temporarily unavailable")
            self.revisions.append(revision)

    async def run():
        manager = ControlPlaneDatabaseManager()
        manager.init_control_plane(postgres_uri)
        repo = WikiRepository(manager, "wiki_index_retry_" + uuid.uuid4().hex)
        index = Index()
        service = WikiService(repo, Organizer(), index)
        try:
            first = await service.ingest(
                source_key="retry.md", markdown="可检索的事实。", db_schemas={"emr": "public"}
            )
            assert first["index_status"] == "pending"
            assert len(await repo.pages(db_names=["emr"])) == 1
            index.fail = False
            recovered = await service.retry_index("retry.md")
            assert recovered["index_status"] == "ready"
            assert index.revisions == [1]
        finally:
            await manager.dispose()

    asyncio.run(run())
