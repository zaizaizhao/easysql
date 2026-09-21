"""Rebuildable Milvus and Neo4j projections of the authoritative PostgreSQL wiki."""

from __future__ import annotations

import json
from typing import Any

from easysql.config import get_settings
from easysql.retrieval.runtime import get_retrieval_runtime
from easysql_agentic.knowledge.models import WikiPage


class WikiIndex:
    @property
    def collection(self) -> str:
        return f"{get_settings().project_namespace}_wiki_pages"

    def replace(self, document_id: str, revision: int, pages: list[WikiPage]) -> None:
        from pymilvus import DataType

        runtime = get_retrieval_runtime()
        client = runtime.milvus_repository.client
        embeddings = runtime.embedding_service.encode_batch(
            [f"{page.domain}\n{page.title}\n{page.summary}\n{page.body_md}" for page in pages]
        )
        if not client.has_collection(self.collection):
            schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("id", DataType.VARCHAR, max_length=80, is_primary=True)
            schema.add_field("page_id", DataType.VARCHAR, max_length=36)
            schema.add_field("document_id", DataType.VARCHAR, max_length=36)
            schema.add_field("revision", DataType.INT64)
            schema.add_field("db_names", DataType.JSON)
            schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=len(embeddings[0]))
            index = client.prepare_index_params()
            index.add_index("embedding", index_type="AUTOINDEX", metric_type="COSINE")
            client.create_collection(self.collection, schema=schema, index_params=index)
        # New rows carry their source revision. Readers recheck it in PostgreSQL;
        # an interrupted projection can never reactivate an obsolete fact.
        rows = [
            {
                "id": f"{page.id}:{revision}",
                "page_id": page.id,
                "document_id": document_id,
                "revision": revision,
                "db_names": page.db_names,
                "embedding": embedding,
            }
            for page, embedding in zip(pages, embeddings, strict=True)
        ]
        for start in range(0, len(rows), 100):
            client.upsert(self.collection, data=rows[start : start + 100])
        client.delete(
            self.collection,
            filter=f"document_id == {json.dumps(document_id)} and revision < {revision}",
        )
        reader = runtime.neo4j_reader
        with reader.driver.session(database=reader.database) as session:
            session.execute_write(self._write_graph, document_id, pages, reader.project_namespace)

    @staticmethod
    def _write_graph(tx: Any, document_id: str, pages: list[WikiPage], namespace: str) -> None:
        revision = pages[0].revision if pages else 0
        accepted = tx.run(
            "MERGE (s:WikiSource {id:$id, project_namespace:$namespace}) "
            "ON CREATE SET s.revision=0 WITH s WHERE s.revision <= $revision "
            "SET s.revision=$revision RETURN s.revision AS revision",
            id=document_id,
            namespace=namespace,
            revision=revision,
        ).single()
        if accepted is None:
            return
        tx.run(
            "MATCH (p:WikiPage {document_id:$document_id, project_namespace:$namespace}) "
            "DETACH DELETE p",
            document_id=document_id,
            namespace=namespace,
        )
        for page in pages:
            tx.run(
                "MERGE (p:WikiPage {id:$id, project_namespace:$namespace}) "
                "SET p.document_id=$document_id, p.revision=$revision, p.title=$title, "
                "p.summary=$summary, p.domain=$domain, p.kind=$kind "
                "WITH p UNWIND $tables AS table_id "
                "MERGE (ref:SchemaReference {id:table_id, project_namespace:$namespace}) "
                "MERGE (p)-[:DESCRIBES]->(ref) "
                "WITH ref OPTIONAL MATCH (t:Table {id:ref.id, project_namespace:$namespace}) "
                "FOREACH (item IN CASE WHEN t IS NULL THEN [] ELSE [t] END | "
                "MERGE (ref)-[:RESOLVES_TO]->(item))",
                id=page.id,
                namespace=namespace,
                document_id=document_id,
                revision=page.revision,
                title=page.title,
                summary=page.summary,
                domain=page.domain,
                kind=page.kind,
                tables=page.table_ids,
            )
            if page.join_rule:
                rule = page.join_rule
                tx.run(
                    "MATCH (p:WikiPage {id:$id, project_namespace:$namespace}), "
                    "(a:SchemaReference {id:$source, project_namespace:$namespace}), "
                    "(b:SchemaReference {id:$target, project_namespace:$namespace}) "
                    "SET p.column_pairs=$pairs, p.cardinality=$cardinality, "
                    "p.conditions=$conditions, p.grain=$grain "
                    "MERGE (a)-[:JOIN_SOURCE]->(p) MERGE (p)-[:JOIN_TARGET]->(b)",
                    id=page.id,
                    namespace=namespace,
                    source=rule.source_table,
                    target=rule.target_table,
                    pairs=json.dumps([pair.model_dump() for pair in rule.column_pairs]),
                    cardinality=rule.cardinality,
                    conditions=rule.conditions,
                    grain=rule.grain,
                )

    def search(self, query: str, db_names: list[str]) -> list[dict[str, Any]]:
        # PostgreSQL applies scope and current-revision filtering to every hit.
        runtime = get_retrieval_runtime()
        client = runtime.milvus_repository.client
        if not client.has_collection(self.collection):
            return []
        excluded = sorted(set(get_settings().databases) - set(db_names))
        scope_filter = (
            f"not json_contains_any(db_names, {json.dumps(excluded)})" if excluded else ""
        )
        hits = client.search(
            self.collection,
            data=[runtime.embedding_service.encode(query)],
            limit=40,
            output_fields=["revision", "page_id"],
            filter=scope_filter,
            search_params={"metric_type": "COSINE"},
        )
        return [
            {"id": str(hit["entity"]["page_id"]), "revision": hit["entity"]["revision"]}
            for hit in hits[0]
        ]

    def delete(self, document_id: str) -> None:
        runtime = get_retrieval_runtime()
        client = runtime.milvus_repository.client
        if client.has_collection(self.collection):
            client.delete(self.collection, filter=f"document_id == {json.dumps(document_id)}")
        reader = runtime.neo4j_reader
        with reader.driver.session(database=reader.database) as session:
            session.run(
                "MATCH (p:WikiPage {document_id:$document_id, project_namespace:$namespace}) "
                "DETACH DELETE p",
                document_id=document_id,
                namespace=reader.project_namespace,
            ).consume()
