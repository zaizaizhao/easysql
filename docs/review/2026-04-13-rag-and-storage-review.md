# RAG And Storage Review

## Scope And Thesis

This review covers the EasySQL retrieval and storage lane across schema retrieval, graph expansion, few-shot retrieval, code-context retrieval, and prompt assembly. The lane is already functional and reasonably feature-rich, but the architecture is organized around storage-specific imperative flows rather than stable retrieval contracts. The biggest practical risks are weak database isolation on the main Milvus schema retrieval path, orchestration concentrated into one service plus storage-aware LangGraph nodes, and relatively weak testability because core retrieval behavior is encoded in live-service flows more than in tight unit-level contracts.

## Current Implementation In EasySQL

The main schema retrieval flow is centralized in `SchemaRetrievalService.retrieve()`. One method performs table candidate generation from Milvus, foreign-key expansion from Neo4j, bridge-table identification, filter-chain execution, FK-target protection, table-column hydration, semantic-column retrieval, and join-path hydration before returning a single `RetrievalResult` object ([easysql/retrieval/schema_retrieval.py](../easysql/retrieval/schema_retrieval.py):74, [easysql/retrieval/schema_retrieval.py](../easysql/retrieval/schema_retrieval.py):169, [easysql/retrieval/schema_retrieval.py](../easysql/retrieval/schema_retrieval.py):228, [easysql/retrieval/schema_retrieval.py](../easysql/retrieval/schema_retrieval.py):281, [easysql/retrieval/schema_retrieval.py](../easysql/retrieval/schema_retrieval.py):304, [easysql/retrieval/schema_retrieval.py](../easysql/retrieval/schema_retrieval.py):313).

The filter chain looks modular at first glance, but its contract is weak. Filters operate on `list[str]` table names plus a mutable `FilterContext`, not on typed scored candidates. `FilterContext.original_tables` is documented as the original Milvus results, but `BridgeFilter` mutates that field by appending bridge and protected neighbor tables, which means provenance is not stable through the pipeline ([easysql/retrieval/base.py](../easysql/retrieval/base.py):13, [easysql/retrieval/base.py](../easysql/retrieval/base.py):23, [easysql/retrieval/base.py](../easysql/retrieval/base.py):102, [easysql/retrieval/bridge_filter.py](../easysql/retrieval/bridge_filter.py):49, [easysql/retrieval/bridge_filter.py](../easysql/retrieval/bridge_filter.py):69, [easysql/retrieval/bridge_filter.py](../easysql/retrieval/bridge_filter.py):88).

Milvus and Neo4j responsibilities are separated, but unevenly. `MilvusSchemaReader` exposes raw vector search for tables and columns with optional free-form filter strings and output fields ([easysql/readers/milvus_reader.py](../easysql/readers/milvus_reader.py):12, [easysql/readers/milvus_reader.py](../easysql/readers/milvus_reader.py):31, [easysql/readers/milvus_reader.py](../easysql/readers/milvus_reader.py):68). `Neo4jSchemaReader` owns graph-specific enrichment such as FK expansion, bridge discovery, join-path lookup, and full column hydration ([easysql/readers/neo4j_reader.py](../easysql/readers/neo4j_reader.py):11, [easysql/readers/neo4j_reader.py](../easysql/readers/neo4j_reader.py):25, [easysql/readers/neo4j_reader.py](../easysql/readers/neo4j_reader.py):112, [easysql/readers/neo4j_reader.py](../easysql/readers/neo4j_reader.py):153, [easysql/readers/neo4j_reader.py](../easysql/readers/neo4j_reader.py):249, [easysql/readers/neo4j_reader.py](../easysql/readers/neo4j_reader.py):297). The repositories underneath are thin connection wrappers rather than true domain-facing adapters ([easysql/repositories/milvus_repository.py](../easysql/repositories/milvus_repository.py):14, [easysql/repositories/milvus_repository.py](../easysql/repositories/milvus_repository.py):36, [easysql/repositories/neo4j_repository.py](../easysql/repositories/neo4j_repository.py):14, [easysql/repositories/neo4j_repository.py](../easysql/repositories/neo4j_repository.py):29).

The main Milvus schema writer stores `database_name` on both table and column vectors, which suggests cross-database isolation is intended at the storage level ([easysql/writers/milvus_writer.py](../easysql/writers/milvus_writer.py):64, [easysql/writers/milvus_writer.py](../easysql/writers/milvus_writer.py):109, [easysql/writers/milvus_writer.py](../easysql/writers/milvus_writer.py):155, [easysql/writers/milvus_writer.py](../easysql/writers/milvus_writer.py):208). But the main schema retrieval path does not make `db_name` a first-class input to Milvus search: table search takes only an optional `filter_expr`, and column search only filters on table names, not database names ([easysql/readers/milvus_reader.py](../easysql/readers/milvus_reader.py):31, [easysql/readers/milvus_reader.py](../easysql/readers/milvus_reader.py):68). In contrast, few-shot retrieval explicitly filters by `db_name`, which is a stronger isolation pattern inside the same repository ([easysql/readers/few_shot_reader.py](../easysql/readers/few_shot_reader.py):54, [easysql/readers/few_shot_reader.py](../easysql/readers/few_shot_reader.py):119, [easysql/readers/few_shot_reader.py](../easysql/readers/few_shot_reader.py):141, [easysql/writers/few_shot_writer.py](../easysql/writers/few_shot_writer.py):117, [easysql/writers/few_shot_writer.py](../easysql/writers/few_shot_writer.py):155).

Code context is also Milvus-backed, but with a much weaker retrieval contract. The code-chunk collection stores only file path, file hash, language, content, and embedding. `search_with_tables()` does not apply table-aware metadata filtering; it simply concatenates table names into the semantic query text ([easysql/code_context/storage/milvus_writer.py](../easysql/code_context/storage/milvus_writer.py):21, [easysql/code_context/storage/milvus_writer.py](../easysql/code_context/storage/milvus_writer.py):61, [easysql/code_context/storage/milvus_reader.py](../easysql/code_context/storage/milvus_reader.py):34, [easysql/code_context/storage/milvus_reader.py](../easysql/code_context/storage/milvus_reader.py):76). On the LangGraph side, `RetrieveCodeNode` then appends the formatted code context to the already-built user prompt as raw string concatenation instead of feeding it through the same section abstraction used by schema, join path, and few-shot context ([easysql/llm/nodes/retrieve_code.py](../easysql/llm/nodes/retrieve_code.py):26, [easysql/llm/nodes/retrieve_code.py](../easysql/llm/nodes/retrieve_code.py):88, [easysql/llm/nodes/retrieve_code.py](../easysql/llm/nodes/retrieve_code.py):94; [easysql/context/builder.py](../easysql/context/builder.py):15, [easysql/context/builder.py](../easysql/context/builder.py):101, [easysql/context/builder.py](../easysql/context/builder.py):186).

One more subtle inconsistency appears in few-shot storage. Duplicate detection embeds only the question text, but insertion stores embeddings for `question + sql`, so duplicate detection and persisted retrieval are operating in different vector spaces ([easysql/writers/few_shot_writer.py](../easysql/writers/few_shot_writer.py):117, [easysql/writers/few_shot_writer.py](../easysql/writers/few_shot_writer.py):134, [easysql/writers/few_shot_writer.py](../easysql/writers/few_shot_writer.py):189).

## Comparison With Strong Reference Patterns

Milvus’s official guidance treats filtered vector search as a first-class capability, not a fallback. EasySQL already uses output fields and free-form filters, but only inconsistently. The few-shot lane follows the stronger pattern by isolating on `db_name`, while the main schema lane leaves that responsibility implicit at the caller level instead of making it part of the reader contract.

Neo4j’s official Python-driver guidance emphasizes explicit database selection and clean read access patterns. EasySQL does specify the database on sessions, which is good, but the retrieval layer still mixes graph traversal semantics directly into business retrieval orchestration instead of exposing a cleaner “graph expansion” or “graph protection” retriever boundary.

The biggest contrast is with hybrid retrieval reference designs such as Neo4j GraphRAG and LlamaIndex. Those systems distinguish base retrievers, graph-augmented retrievers, postprocessors, and query engines as composable stages. EasySQL approximates that structure informally with Milvus search, Neo4j expansion, semantic filter, bridge filter, and LLM filter, but the composition is implemented as one imperative method over raw table-name lists plus mutable side-channel state. The result is functionally similar but architecturally less replaceable and less testable.

## Review Findings

1. The highest-risk correctness issue is weak database isolation on the main Milvus schema retrieval path. The storage schema includes `database_name`, but table search does not take `db_name` as a first-class argument and column search only filters by table name. If one collection prefix ever contains multiple logical databases, retrieval can mix candidates across databases before later graph logic narrows things back down.

2. Retrieval orchestration is too concentrated in one service method. `SchemaRetrievalService.retrieve()` mixes candidate generation, graph expansion, bridge protection, re-scoring, filter-chain execution, FK completion, and prompt-facing hydration. That makes it difficult to benchmark or replace individual stages without touching the whole flow.

3. The filter contract is impure and order-sensitive in a dangerous way. `FilterContext.original_tables` is documented as original Milvus results, but `BridgeFilter` mutates it. Once provenance becomes mutable shared state, later filters cannot distinguish “came from vector search” from “was injected by bridge protection.”

4. FK expansion currently performs additional Milvus lookups for newly expanded tables. That creates an N+1 pattern where graph expansion has to reach back into vector storage for score assignment, increasing latency and coupling graph logic to Milvus query details.

5. Code-context retrieval is only heuristically table-aware. Relevant tables are concatenated into the query text instead of being expressed as structured metadata constraints, and the final code context bypasses the structured prompt-section system by being appended as raw text.

6. Storage and orchestration boundaries leak into LangGraph state handling. Retrieval output is effectively serialized through `__dict__`-style structures and later reconstructed manually in downstream nodes. That makes retrieval artifacts more brittle than they need to be and couples node logic to retrieval serialization details.

7. Testability is weaker than this lane needs. Several retrieval validations are live-service scripts against real Milvus or Neo4j instances, while focused unit coverage is much better in context rendering and chunking than in the core retrieval contracts themselves.

## Optimization Directions

1. Introduce first-class retrieval stage interfaces. Split the current flow into explicit concepts such as table candidate retrieval, graph expansion, table postprocessing, column retrieval, and context artifact assembly. That would align the lane more closely with stronger retriever-plus-postprocessor patterns and make stage-level testing possible.

2. Make `db_name` a required structured input to Milvus schema retrieval. `search_tables()` and `search_columns()` should accept database scoping explicitly and build Milvus filters internally instead of relying on callers to assemble partial string filters.

3. Replace mutable filter context with typed candidates that carry provenance. A candidate should be able to say whether it came from vector search, FK expansion, bridge protection, or must-keep logic, along with score and database metadata. That removes the `original_tables` mutation bug and makes ordering behavior auditable.

4. Stop re-querying Milvus per expanded table. Either preserve graph-expanded tables as graph-only candidates with explicit provenance or add a bulk metadata lookup path. This reduces latency and keeps graph expansion from depending on vector-search semantics for bookkeeping.

5. Promote code context and few-shot context into the same prompt-assembly abstraction used by schema and join-path sections. If code context is product-critical, add structured metadata such as referenced tables or entities to the code index so retrieval can filter on more than semantic similarity.

6. Add focused unit tests around the core contracts:
   cross-database isolation for Milvus search,
   filter-chain purity,
   FK-target protection,
   few-shot duplicate detection consistency,
   code-context retrieval semantics,
   and retrieval DTO serialization boundaries.

## Why These Changes Are Justified

These changes are justified because they address correctness and future change cost, not just neatness. The main Milvus retrieval path currently exposes an isolation inconsistency that the few-shot path already avoids. That means the codebase itself demonstrates the stronger pattern and also demonstrates where the weaker pattern lives.

They also reduce performance waste and hidden coupling. The current retrieval service has to perform extra vector queries after graph expansion, and downstream nodes have to understand retrieval serialization details and prompt-shaping side effects. Those costs compound as more retrieval modes are added.

Finally, they improve replaceability. Right now Milvus and Neo4j usage leak upward into retrieval orchestration, LangGraph nodes, and prompt construction. Stronger retriever and context-artifact boundaries would let the project optimize for recall, precision, or latency more intentionally instead of burying those tradeoffs inside one large imperative flow.

## Suggested Priority And Follow-up Questions

Priority:

- `P0`: make Milvus database scoping first-class for table and column retrieval, then add targeted tests for cross-database isolation.
- `P1`: split [schema_retrieval.py](../easysql/retrieval/schema_retrieval.py) into typed retriever and postprocessor stages and remove `FilterContext` mutation.
- `P1`: make code context a first-class prompt section and add real metadata filtering if table-aware code retrieval is meant to be operational.
- `P2`: clean up retrieval serialization boundaries so LangGraph nodes consume DTOs or explicit artifacts rather than loosely reconstructed dicts.
- `P2`: revisit few-shot duplicate detection so deduplication and persisted search use the same embedding space.

Follow-up questions:

- Are Milvus collection prefixes guaranteed to be single-database in production, or can one prefix hold multiple source databases?
- Is code-context retrieval expected to be table-aware in a real sense, or is general semantic code lookup acceptable?
- Is the LLM filter intended for production retrieval or mainly for debugging and tuning?
- Should retrieval quality be optimized for recall, precision, or latency first? The current architecture hides that tradeoff inside one method.
