"""Incremental publication and progressive-disclosure wiki retrieval."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any

from easysql_agentic.knowledge.models import WikiPage
from easysql_agentic.knowledge.repository import WikiRepository

MAX_MARKDOWN_BYTES = 512 * 1024


def search_terms(query: str) -> list[str]:
    terms = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+", query.lower())
    expanded = []
    for term in terms:
        expanded.append(term)
        if re.fullmatch(r"[\u4e00-\u9fff]{3,}", term):
            expanded.extend(term[index : index + 2] for index in range(len(term) - 1))
    return list(dict.fromkeys(expanded))[:24]


class WikiService:
    def __init__(
        self, repository: WikiRepository, organizer: Any = None, index: Any = None
    ) -> None:
        self.repository = repository
        self.organizer = organizer
        self.index = index

    async def ingest(
        self,
        *,
        source_key: str,
        markdown: str,
        db_schemas: dict[str, str],
        timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        if not source_key.strip() or len(source_key) > 255:
            raise ValueError("A source key of 1-255 characters is required")
        if not markdown.strip() or len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
            raise ValueError("Upload a non-empty Markdown document of at most 512 KiB")
        if not db_schemas:
            raise ValueError("Select the document's applicable databases")
        digest = hashlib.sha256(
            json.dumps([markdown, sorted(db_schemas.items())], ensure_ascii=False).encode()
        ).hexdigest()
        async with self.repository.lease(
            "wiki:" + hashlib.sha256(source_key.encode()).hexdigest(), timeout_seconds + 90
        ):
            current = await self.repository.get_document(source_key)
            if current and current["content_hash"] == digest:
                return {**current, "markdown": None, "unchanged": True}
            if self.organizer is None:
                raise RuntimeError("No Markdown organizer configured")
            domains = await self.repository.domains(list(db_schemas))
            drafts = await asyncio.wait_for(
                self.organizer.organize(markdown, db_schemas, [item["domain"] for item in domains]),
                timeout=timeout_seconds,
            )
            # Validate at the service boundary too, including injected/custom organizers.
            if not drafts:
                raise ValueError("No knowledge extracted; the previous version is preserved")
            for draft in drafts:
                if draft.source_quote not in markdown:
                    raise ValueError("Extracted evidence is not present in the uploaded source")
                if any(table.split(".", 1)[0] not in db_schemas for table in draft.table_ids):
                    raise ValueError("Extracted table is outside the selected databases")
            result = await self.repository.publish(
                source_key=source_key,
                markdown=markdown,
                content_hash=digest,
                db_names=sorted(db_schemas),
                drafts=drafts,
                expected_revision=current["revision"] if current else 0,
            )
            return await self._project(result)

    async def _project(self, document: dict[str, Any]) -> dict[str, Any]:
        if self.index is None:
            return document
        try:
            pages = await self.repository.pages(document_id=document["id"], limit=5000)
            await asyncio.wait_for(
                asyncio.to_thread(self.index.replace, document["id"], document["revision"], pages),
                timeout=90,
            )
            status, error = "ready", None
        except Exception as exc:
            status, error = (
                "pending",
                f"Index unavailable ({type(exc).__name__}); wiki reads remain available",
            )
        await self.repository.mark_index(document["id"], document["revision"], status, error)
        return {**document, "index_status": status, "index_error": error}

    async def retry_index(self, source_key: str) -> dict[str, Any]:
        async with self.repository.lease("wiki:" + hashlib.sha256(source_key.encode()).hexdigest()):
            document = await self.repository.get_document(source_key)
            if document is None:
                raise ValueError("Document not found")
            result = await self._project(document)
            result.pop("markdown", None)
            return result

    async def outline(self, db_names: list[str], domain: str = "") -> dict[str, Any]:
        domains = await self.repository.domains(db_names)
        children: dict[str, int] = {}
        prefix = domain + "/" if domain else ""
        for item in domains:
            path = item["domain"]
            if path == domain:
                continue
            if path.startswith(prefix):
                child = prefix + path[len(prefix) :].split("/")[0]
                children[child] = children.get(child, 0) + item["page_count"]
        return {
            "domain": domain,
            "children": [
                {"domain": name, "page_count": count} for name, count in sorted(children.items())
            ],
            "next": "list_wiki_pages(domain) to inspect summaries; read_wiki_page(id) to load text",
        }

    async def list_pages(
        self,
        db_names: list[str],
        domain: str,
        offset: int = 0,
    ) -> dict[str, Any]:
        pages = await self.repository.pages(
            db_names=db_names, domain=domain, limit=21, offset=offset
        )
        return {
            "pages": [page.card() for page in pages[:20]],
            "next_offset": offset + 20 if len(pages) > 20 else None,
        }

    async def read(
        self,
        page_id: str,
        db_names: list[str],
        offset: int = 0,
        limit: int = 8000,
    ) -> dict[str, Any]:
        pages = await self.repository.pages(db_names=db_names, ids=[page_id], limit=1)
        if not pages:
            raise ValueError("Wiki page not found in the selected database scope")
        page = pages[0]
        body = page.body_md[offset : offset + limit]
        return {
            **page.card(),
            "body_md": body,
            "source_quote": page.source_quote,
            "join_rule": page.join_rule.model_dump() if page.join_rule else None,
            "next_offset": offset + limit if offset + limit < len(page.body_md) else None,
        }

    async def search(self, query: str, db_names: list[str], limit: int = 8) -> dict[str, Any]:
        terms = search_terms(query)
        if not terms:
            raise ValueError("Enter a non-empty search query")
        lexical = await self.repository.pages(db_names=db_names, terms=terms, limit=100)
        lexical.sort(
            key=lambda page: sum(
                3 * (term in (page.title + page.summary).lower()) + (term in page.body_md.lower())
                for term in terms
            ),
            reverse=True,
        )
        dense: list[WikiPage] = []
        search_mode = "lexical"
        if self.index is not None:
            try:
                hits = await asyncio.wait_for(
                    asyncio.to_thread(self.index.search, query, db_names), timeout=15
                )
                candidates = await self.repository.pages(
                    db_names=db_names, ids=[hit["id"] for hit in hits]
                )
                live = {page.id: page for page in candidates}
                dense = [
                    live[hit["id"]]
                    for hit in hits
                    if hit["id"] in live and live[hit["id"]].revision == hit["revision"]
                ]
                search_mode = "hybrid"
            except Exception:
                search_mode = "lexical_index_unavailable"
        scores: dict[str, float] = {}
        found: dict[str, WikiPage] = {}
        for ranking in (lexical, dense):
            for position, page in enumerate(ranking):
                scores[page.id] = scores.get(page.id, 0) + 1 / (60 + position)
                found[page.id] = page
        ordered = sorted(scores, key=scores.get, reverse=True)[:limit]
        return {
            "pages": [found[page_id].card() for page_id in ordered],
            "mode": search_mode,
            "next": "Read relevant pages before using their definitions or join rules",
        }
