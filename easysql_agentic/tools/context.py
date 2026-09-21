"""Request-local ADK FunctionTools; no fixed retrieval workflow runs before the agent."""

from __future__ import annotations

import asyncio
from typing import Any

from google.adk.tools import ToolContext

from easysql.federation import DatabaseScope, FederatedSqlExecutor, FederationStatusProbe
from easysql_agentic.knowledge.service import WikiService
from easysql_agentic.tools.catalog import Catalog
from easysql_agentic.tools.joins import find_paths
from easysql_agentic.tools.sql import parse_read_query, validate_submission


class ContextTools:
    def __init__(
        self,
        scope: DatabaseScope,
        wiki: WikiService,
        *,
        catalog: Catalog | None = None,
        executor: FederatedSqlExecutor | None = None,
        max_calls: int = 40,
    ) -> None:
        self.scope = scope
        self.wiki = wiki
        self.catalog = catalog or Catalog(scope)
        self.executor = executor or FederatedSqlExecutor()
        self.evidence: set[str] = set()
        self.knowledge_revisions: dict[str, int] = {}
        self._wiki_offsets: dict[tuple[str, int], int] = {}
        self.loaded_tables: set[str] = set()
        self.assessment: dict[str, Any] | None = None
        self.outcome: dict[str, Any] | None = None
        self.calls = 0
        self.model_calls = 0
        self.max_calls = max_calls
        self._submission_lock = asyncio.Lock()

    def _start(self) -> None:
        self.calls += 1
        if self.outcome is not None:
            raise ValueError("This request already has a final outcome")
        if self.calls > self.max_calls:
            raise ValueError(
                "Context tool budget exhausted; clarify or report insufficient context"
            )
        self.assessment = None

    def _remember(self, evidence_id: str) -> None:
        self.evidence.add(evidence_id)

    async def describe_database_scope(self) -> dict[str, Any]:
        """List allowed databases, SQL dialects and credential-free dblink connection names."""
        self._start()
        return {"databases": self.scope.names, "instructions": self.scope.render_prompt_context()}

    async def browse_wiki(self, domain: str = "") -> dict[str, Any]:
        """Read the wiki's next directory level. Start with an empty domain; no page bodies load."""
        self._start()
        return await self.wiki.outline(self.scope.names, domain)

    async def list_wiki_pages(self, domain: str, offset: int = 0) -> dict[str, Any]:
        """List up to 20 page summaries under a domain; follow next_offset to see more."""
        self._start()
        if offset < 0:
            raise ValueError("offset must be non-negative")
        return await self.wiki.list_pages(self.scope.names, domain, offset)

    async def search_knowledge(self, query: str) -> dict[str, Any]:
        """Find wiki page summaries about terms, metrics, schema, join rules or validated SQL."""
        self._start()
        return await self.wiki.search(query, self.scope.names)

    async def read_wiki_page(self, page_id: str, offset: int = 0) -> dict[str, Any]:
        """Load a selected wiki page body and its source quote. Follow next_offset for long pages."""
        self._start()
        if offset < 0:
            raise ValueError("offset must be non-negative")
        result = await self.wiki.read(page_id, self.scope.names, offset)
        revision = result["revision"]
        if self.knowledge_revisions.get(page_id) not in {None, revision}:
            self.evidence.discard(page_id)
        self.knowledge_revisions[page_id] = revision
        cursor = (page_id, revision)
        if offset == self._wiki_offsets.get(cursor, 0):
            self._wiki_offsets[cursor] = offset + len(result["body_md"])
            if result["next_offset"] is None:
                self._remember(page_id)
        result["evidence_ready"] = page_id in self.evidence
        return result

    async def search_tables(self, query: str, database: str, top_k: int = 5) -> dict[str, Any]:
        """Semantically find tables in one selected database; then load exact table schemas."""
        self._start()
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be 1-10")
        return await asyncio.to_thread(self.catalog.search_tables, query, database, top_k)

    async def search_columns(self, query: str, database: str, top_k: int = 10) -> dict[str, Any]:
        """Semantically discover columns and their tables in one selected database."""
        self._start()
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be 1-20")
        return await asyncio.to_thread(self.catalog.search_columns, query, database, top_k)

    async def list_database_tables(self, database: str, offset: int = 0) -> dict[str, Any]:
        """Page through live table names when semantic discovery is unavailable or insufficient."""
        self._start()
        if offset < 0:
            raise ValueError("offset must be non-negative")
        return await asyncio.to_thread(self.catalog.list_tables, database, offset)

    async def get_table_schema(self, table_id: str) -> dict[str, Any]:
        """Load live columns, types and complete foreign keys for database.schema.table."""
        self._start()
        result = await asyncio.to_thread(self.catalog.table_schema, table_id)
        self.loaded_tables.add(result["table_id"])
        self._remember("schema:" + result["table_id"])
        return result

    async def expand_related_tables(
        self, database: str, table_names: list[str], depth: int = 1
    ) -> dict[str, Any]:
        """Expand selected tables by one or two physical foreign-key hops in a database."""
        self._start()
        if not 1 <= depth <= 2 or not 1 <= len(table_names) <= 8:
            raise ValueError("Use 1-8 tables and depth 1-2")
        return await asyncio.to_thread(self.catalog.expand_tables, database, table_names, depth)

    async def find_join_paths(self, table_ids: list[str], max_hops: int = 4) -> dict[str, Any]:
        """Find scoped cross-database paths using physical keys and source-backed wiki join rules."""
        self._start()
        result = await find_paths(table_ids, self.catalog, self.wiki.repository, max_hops)
        for path in result["paths"]:
            for step in path["steps"]:
                for rule in step["alternatives"]:
                    self._remember(rule["id"])
                    if rule.get("kind") == "documented_join":
                        self.knowledge_revisions[rule["id"]] = rule["revision"]
        return result

    async def search_sql_examples(self, query: str) -> dict[str, Any]:
        """Retrieve existing few-shot SQL examples in selected databases, plus wiki examples."""
        self._start()
        return {"examples": await asyncio.to_thread(self.catalog.examples, query)}

    async def check_dblink_routes(self) -> dict[str, Any]:
        """Probe directed dblink routes. Choose a primary with routes to the required remote sources."""
        self._start()
        from dataclasses import asdict

        from easysql.config import get_settings

        return asdict(
            await asyncio.to_thread(FederationStatusProbe().check, get_settings(), self.scope.names)
        )

    async def assess_context(
        self,
        sufficient: bool,
        missing: list[str],
        evidence_ids: list[str],
        rationale: str,
    ) -> dict[str, Any]:
        """Record your evidence-based sufficiency judgment before SQL submission. Missing facts require retrieval or clarification."""
        unknown = set(evidence_ids) - self.evidence
        if unknown:
            return {
                "accepted": False,
                "error": "Evidence has not been loaded",
                "unknown": sorted(unknown),
            }
        if sufficient and (missing or not evidence_ids or not self.loaded_tables):
            return {
                "accepted": False,
                "error": "Ready requires loaded schema, evidence and no unresolved gaps",
            }
        self.assessment = {
            "sufficient": sufficient,
            "missing": missing,
            "evidence_ids": evidence_ids,
            "rationale": rationale,
        }
        return {"accepted": True, **self.assessment}

    async def submit_final_sql(
        self, sql: str, primary_db: str, tool_context: ToolContext
    ) -> dict[str, Any]:
        """Submit one complete SQL after assessing context. Validate local AND remote SQL with read-only execution. Success ends this request."""
        async with self._submission_lock:
            if self.outcome:
                return self.outcome
            if not self.assessment or not self.assessment["sufficient"]:
                return {
                    "status": "error",
                    "error": "Call assess_context with sufficient grounded evidence first",
                }
            try:
                primary_db = self.scope.require_primary(primary_db).name
                if self.knowledge_revisions:
                    current = await self.wiki.repository.pages(
                        db_names=self.scope.names, ids=list(self.knowledge_revisions), limit=100
                    )
                    versions = {page.id: page.revision for page in current}
                    stale = [
                        page_id
                        for page_id, version in self.knowledge_revisions.items()
                        if versions.get(page_id) != version
                    ]
                    if stale:
                        self.assessment = None
                        self.evidence.difference_update(stale)
                        for page_id in stale:
                            self.knowledge_revisions.pop(page_id)
                        return {
                            "status": "error",
                            "error": "Wiki evidence changed; reload and reassess",
                            "stale_page_ids": stale,
                        }
                parsed = parse_read_query(sql, self.scope, primary_db)
                missing_tables = set(parsed.tables) - self.loaded_tables
                if missing_tables:
                    return {
                        "status": "error",
                        "error": "Load live schema for all referenced tables",
                        "missing_tables": sorted(missing_tables),
                    }
                parsed, error = await asyncio.to_thread(
                    validate_submission, sql, self.scope, primary_db, self.executor
                )
                if error:
                    return {"status": "error", "error": error}
            except ValueError as exc:
                return {"status": "error", "error": str(exc)}
            self.outcome = {
                "status": "completed",
                "sql": parsed.sql,
                "primary_db": primary_db,
                "db_names": self.scope.names,
                "validation_passed": True,
                "tables_used": parsed.tables,
                "evidence_ids": self.assessment["evidence_ids"],
                "knowledge_revisions": dict(self.knowledge_revisions),
            }
            tool_context.actions.skip_summarization = True
            tool_context.actions.end_of_agent = True
            return self.outcome

    async def ask_clarification(
        self, questions: list[str], tool_context: ToolContext
    ) -> dict[str, Any]:
        """Ask the user to resolve missing or conflicting business definitions; stop this request."""
        if not 1 <= len(questions) <= 3 or any(not question.strip() for question in questions):
            raise ValueError("Ask one to three concrete clarification questions")
        self.outcome = {"status": "awaiting_clarify", "clarification": {"questions": questions}}
        tool_context.actions.skip_summarization = True
        tool_context.actions.end_of_agent = True
        return self.outcome

    async def report_insufficient_context(
        self, reason: str, tool_context: ToolContext
    ) -> dict[str, Any]:
        """Finish with an explicit failure when required metadata or an executable route cannot be obtained."""
        self.outcome = {"status": "failed", "error": reason, "validation_passed": False}
        tool_context.actions.skip_summarization = True
        tool_context.actions.end_of_agent = True
        return self.outcome

    def functions(self) -> list[Any]:
        return [
            self.describe_database_scope,
            self.browse_wiki,
            self.list_wiki_pages,
            self.search_knowledge,
            self.read_wiki_page,
            self.search_tables,
            self.search_columns,
            self.list_database_tables,
            self.get_table_schema,
            self.expand_related_tables,
            self.find_join_paths,
            self.search_sql_examples,
            self.check_dblink_routes,
            self.assess_context,
            self.submit_final_sql,
            self.ask_clarification,
            self.report_insufficient_context,
        ]
