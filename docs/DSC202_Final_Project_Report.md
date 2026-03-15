# DSC 202 Final Report: Scientific Paper Knowledge Graph & Semantic Search

**Team:** [Your names here]  
**Date:** [Submission date]

---

## Table of Contents

1. [Introduction](#introduction)
2. [The Data](#the-data)
3. [Postgres](#postgres)
4. [Neo4j](#neo4j)
5. [Qdrant](#qdrant)
6. [How They All Connect](#how-they-all-connect)
7. [Infrastructure Setup](#infrastructure-setup)
8. [Data Loading](#data-loading)
9. [Design Considerations](#design-considerations)
10. [Competency Questions and Use Cases](#competency-questions-and-use-cases)
11. [Limitations and Future Considerations](#limitations-and-future-considerations)

---

## Introduction

Literature review is hard. Researchers need to find existing solutions to a problem, keep up with recent work (e.g., the last five years), and understand how papers connect—who cites whom and who collaborates with whom. Keyword search only matches exact or lexical variants and misses papers that express the same ideas in different terms. No single database does everything: finding papers *by meaning*, filtering by year or venue, and exploring citation chains and author collaborations each demand different storage and query patterns.

Our tool, **Scientific Paper Knowledge Graph & Semantic Search**, addresses these needs by combining three data stores—PostgreSQL (relational), Neo4j (graph), and Qdrant (vector)—each chosen and justified for the questions it answers best. The application ingests a DBLP-derived CSV dataset into all three stores, then exposes an API and a Streamlit UI so users can run semantic search, explore collaboration networks, find indirect citations, and combine similarity with citation analytics.

**Github link:** [Your repository URL]  
Extra files for infrastructure setup, pipeline code, and demo instructions are in the repository.

---

## The Data

Our data comes from a **DBLP-derived CSV** (e.g., `matched_main.csv` or `dblp-v10.csv`). The main fields are:

| Field       | Description                          |
|------------|--------------------------------------|
| `id`       | Unique paper identifier (UUID)       |
| `title`    | Paper title                          |
| `abstract` | Abstract text (may be missing)       |
| `venue`    | Publication venue (conference/journal) |
| `year`     | Publication year                     |
| `n_citation` | Citation count (if available)     |
| `authors`  | List of author names (string-list)   |
| `references` | List of cited paper IDs (string-list) |

Authors and references are stored as string-lists and parsed (e.g., literal-eval style) during ingestion. The same paper `id` is used consistently across Postgres, Neo4j, and Qdrant so that results from one store can be joined or enriched with another.

Data quality notes: some rows have missing abstracts (we fall back to title-only for embeddings); author identity is name-based, so disambiguation is a known limitation.

---

## Postgres

### What is PostgreSQL (and Why a Relational Store)?

PostgreSQL is a **relational database**: data is stored in **tables** (rows and columns) with **primary keys**, **foreign keys**, and **indexes**. Queries are written in **SQL**, which is built for filtering (WHERE), joining tables (JOIN), and aggregating (GROUP BY, SUM, COUNT). This model excels when the questions are “which rows match these conditions?” or “what is the total/average/count per category?”—for example, “papers from 2020 onward,” “top venues by paper count,” or “total citations per author.” Relational databases have been optimized for decades for exactly these patterns; indexes on key columns make filters and joins fast even on large tables. In our project, we do *not* use Postgres for path traversal (that is Neo4j’s strength) or for similarity search (that is Qdrant’s). We use it as the **structured source of truth** for paper metadata, authorship links, citation edges, and any **aggregate** or **filter** we need when answering competency questions or enriching results from the other stores.

### Implementation in Our Project

We use Postgres to store the same core entities as in the other stores—papers, authors, and citations—in normalized relational form. The same paper `id` (UUID) is the primary key in `papers` and is used to join with Neo4j and Qdrant when we combine results.

**Tables (schema):**

- **papers** — `id` (UUID, PK), `title` (TEXT, NOT NULL), `abstract` (TEXT), `venue` (TEXT), `year` (INT), `n_citation` (INT, default 0). One row per paper; this is the main metadata table.
- **authors** — `author_id` (BIGSERIAL, PK), `name` (TEXT, UNIQUE). One row per distinct author name.
- **paper_authors** — `paper_id` (FK → papers), `author_id` (FK → authors), composite PRIMARY KEY. Many-to-many link for “who wrote which paper.”
- **citations** — `citing_paper_id` (FK → papers), `cited_paper_id` (no FK, to allow references to papers outside our ingested set), composite PRIMARY KEY. Directed citation edges.

The schema is created by `infra/postgres/init.sql` when the Postgres container starts; the pipeline uses **psycopg** to connect and run `ensure_postgres_schema`, then batch-inserts papers, authors, paper_authors, and citations from the DBLP-derived CSV. We also enable the **pg_trgm** extension for fuzzy text matching on author names.

**Indexes (why they matter):**

- `papers(year)`, `papers(venue)` — fast filtering by time and venue for analytics and “papers in this field/year.”
- `papers(n_citation DESC)` — quick “most cited” reporting and ordering.
- Trigram index on `authors(name)` — author lookup and autocomplete-friendly search.
- `paper_authors(author_id)` — fast “all papers by this author” joins.
- `citations(cited_paper_id)` — fast “who cites this paper?” (inbound citation) queries.

### Why Postgres Is Useful for Our Tool

Many competency questions need **structured filters** or **aggregates** that are natural in SQL:

- **Filter by year or venue** — “Papers from 2020 onward” or “papers from venue X” are simple WHERE clauses; indexes make them cheap.
- **Citation counts** — The `n_citation` column on papers, or SUM/aggregates over citations per author, are standard SQL. Neither Neo4j nor Qdrant is designed as the primary place for “sum citations per entity”; Postgres is.
- **Joining with other stores** — When Qdrant returns “top-k similar paper IDs,” we often need their titles, years, venues, and citation counts. Postgres is the right place to look up those attributes by `id` in one batched query. Similarly, when Neo4j returns “central authors,” we use Postgres to get each author’s total citation count (join authors → paper_authors → papers, GROUP BY author, SUM(n_citation)).
- **Source of truth** — Paper and author identities, and the citation graph as edge list, are stored here in a normalized form. That gives us a single place for “what papers do we have?” and “what are this paper’s metadata and citation count?”

Using only Neo4j or Qdrant for these would mean either duplicating all metadata in the graph/payload or doing awkward workarounds. Postgres keeps filters and aggregates simple and fast.

### Competency Questions Postgres Answers

Postgres is rarely the *only* store for a question, but it is **essential whenever we need structured metadata, filters, or aggregates**:

1. **What is the relationship between paper citations and topic similarity?** — Qdrant returns papers similar to a query; we then query Postgres for those paper IDs to get `n_citation`, `year`, `venue`, `title`. The “citation” part of the answer comes from Postgres; the “similarity” part from Qdrant.

2. **Are there authors whose work is central in the network but under-cited?** — Neo4j gives us “central” authors (e.g., by co-author degree); Postgres gives us total citations per author (JOIN authors, paper_authors, papers; GROUP BY author; SUM(n_citation)). We combine the two to rank central-but-undercited authors. The aggregate is a classic SQL operation.

3. **Cross-field relevance and similar flows** — Whenever we need to filter or rank by venue, year, or citation count, that metadata lives in Postgres (and may be mirrored in Qdrant payload for convenience). Postgres is the authoritative source for structured attributes and for any JOIN or GROUP BY over papers and authors.

In short: whenever the question involves **filtering by year/venue**, **citation counts or other aggregates**, or **enriching result sets with paper/author metadata**, Postgres is the right store. For path and relationship traversal we use Neo4j; for similarity by content we use Qdrant.

---

## Neo4j

### What is Neo4j?

Neo4j is a **graph database** that stores data as nodes (entities) and relationships (edges) between them, rather than in tables and rows. Queries are written in **Cypher**, a language designed for describing patterns in the graph—for example, “find all nodes connected to X by a path of length 2.” This model is a natural fit for any domain where *relationships* and *paths* matter: social networks, recommendation systems, dependency graphs, and, in our case, **citation networks** and **authorship networks**. Relational databases can represent the same edges in tables, but answering questions like “who collaborates with whom?” or “which papers cite this one indirectly?” often requires recursive or multi-join queries that are both complex to write and expensive at scale. A graph database is built for exactly these kinds of traversals.

### Implementation in Our Project

We use Neo4j to model the **citation graph** (papers citing papers) and the **authorship graph** (authors writing papers, papers published in venues). The same paper identifiers used in Postgres and Qdrant are used in Neo4j so we can join results across stores when needed.

**Node labels and properties:**

- **:Paper** — `paperId`, `title`, `year`, `abstract`, `n_citation`. Each paper is a single node; `paperId` matches the UUID in Postgres and Qdrant.
- **:Author** — `authorName`. Authors are identified by name (same limitation as elsewhere; disambiguation is future work).
- **:Venue** — `venueName`. Conferences and journals are first-class nodes so we can scope queries by publication venue (e.g., “co-authorship within this venue”).

**Relationship types:**

- `(:Author)-[:WROTE]->(:Paper)` — authorship; an author node is linked to every paper they wrote.
- `(:Paper)-[:PUBLISHED_IN]->(:Venue)` — each paper is linked to the venue where it was published.
- `(:Paper)-[:CITES]->(:Paper)` — directed citation; the citing paper points to the cited paper.

We enforce **unique constraints** on `Paper.paperId`, `Author.authorName`, and `Venue.venueName`, and maintain an index on `Paper.year` for time-based filters. The graph is loaded from pre-generated CSV files (`papers.csv`, `authors.csv`, `venues.csv`, `wrote.csv`, `paper_venue.csv`, `citations.csv`) in `data/raw/` via the pipeline command `ingest-selected --include-neo4j`, which calls `load_graph_from_csv_files` in `packages/pipeline/src/pipeline/neo4j_loader.py`. For development we also use the Neo4j **Graph Data Science (GDS)** plugin for algorithms such as community detection and betweenness centrality.

### Why Neo4j Is Useful for Our Tool

Many of our competency questions are *inherently about relationships and paths*:

- **Indirect citations** — “Which papers cite this one in 1–3 hops?” requires following `CITES` edges along paths; Cypher path patterns (e.g. `(src)-[:CITES*1..3]->(target)`) express this directly.
- **Collaboration** — “Which authors collaborate most?” means “which pairs of authors share the most papers?” That is a shared-neighbor pattern on `WROTE`: two authors are co-authors if they both wrote the same paper. In the graph this is a simple match on two authors and a common paper node.
- **Clusters and bridges** — “Which author clusters dominate a venue?” or “Who are bridge authors between domains?” are classic graph analytics: community detection and betweenness centrality. Neo4j GDS provides these algorithms on our graph without moving data to an external tool.

Using a relational database for the same questions would mean recursive CTEs or multiple self-joins, which are harder to write, maintain, and optimize. Neo4j keeps the mental model (“follow the links”) aligned with the query model.

### Competency Questions Neo4j Answers

Neo4j is the **primary or sole store** used for the following:

1. **Which authors collaborate most frequently?** — Co-authorship is a graph pattern (shared `WROTE` neighbors); we count distinct joint papers per author pair.
2. **Can we suggest papers that cite a given paper indirectly?** — Multi-hop path traversal on `CITES`; we return papers that cite the target in 1 to N hops.
3. **Which author clusters dominate a research field (venue)?** — We use the subgraph of authors and papers for a venue and run community detection (e.g., GDS) to find clusters.
4. **Which authors act as bridges between research domains?** — Graph metrics such as betweenness on the co-authorship or venue-linked graph identify authors who connect different communities.
5. **Central but under-cited authors** (combined with Postgres) — Neo4j provides “central” in the graph (e.g., degree or betweenness); Postgres provides citation-related stats to find those who are central but under-cited.

Neo4j is also used **together with Qdrant or Postgres** for cross-store questions (e.g., topics connected via co-authorship, where Qdrant finds similar papers and Neo4j reveals how those papers’ authors are connected). In short: whenever the question is about *who is connected to whom* or *how many steps between A and B*, Neo4j is the right store.

---

## Qdrant

### What is Qdrant?

Qdrant is a **vector database** (sometimes called an embedding store) built for **similarity search**. Instead of storing rows and columns or nodes and edges, it stores **vectors**—dense numerical representations of data, typically produced by an **embedding model** that maps text (or images) into a high-dimensional space. Similar content ends up close in that space; the database’s job is to quickly find the **k nearest neighbors** (kNN) to a given query vector. This enables **semantic search**: you can ask “papers like this” or “papers that match this research question” without relying on exact keyword matches. Relational and graph databases are not designed for this: they excel at exact lookups, filters, and relationship traversal, but they do not natively support “find the most similar items by meaning.” A dedicated vector store like Qdrant is built for exactly that, often with indexes (e.g., HNSW) that make kNN search fast even at scale.

### Implementation in Our Project

We use Qdrant to hold **embeddings of paper content** so we can answer “which papers are most similar to this query or to this paper?” The same paper identifier used in Postgres and Neo4j is used as the point ID in Qdrant, so we can join vector results with relational or graph data when needed.

**Collection:** `papers_vectors` (configurable via `QDRANT_COLLECTION` in settings).

**What we embed:** For each paper we concatenate `title + "\n" + abstract`. If the abstract is missing, we fall back to the title only. This gives the model enough context to capture the paper’s topic and content for similarity.

**Embedding model:** We use **BAAI/bge-small-en-v1.5** via the **fastembed** library. This runs locally and requires no API keys; it produces fixed-size vectors (e.g., 384 dimensions) and is well suited for English text. The pipeline creates the collection with **cosine** distance, which is a standard choice for normalized embeddings.

**Payload:** Each vector is stored with payload fields so we can filter and display results without a round-trip to Postgres: `paper_id`, `title`, `year`, `venue`. We can therefore do “top-k similar papers” and “top-k similar papers where year ≥ X” or “venue = Y” in a single Qdrant call.

The ingestion pipeline (Postgres + Neo4j + Qdrant) embeds each paper’s text in batches, then upserts the vectors and payload into Qdrant. At query time, the user’s free-text query (or a seed abstract) is embedded with the same model, and we call Qdrant’s search API to get the nearest vectors—optionally with payload filters for year or venue.

### Why Qdrant Is Useful for Our Tool

Many research questions are **about meaning**, not just keywords:

- **Semantic similarity** — “Which papers are most similar to my research question?” Keyword search would only match papers that contain the same words; semantic search finds papers that discuss the same ideas in different wording. That requires comparing *embeddings*, which only a vector store can do efficiently.
- **Cross-field relevance** — “Which papers in field A are relevant to a question from field B?” Again, this is content-based: we need “similar by meaning” and then filter or rank by venue/field. Qdrant handles the similarity; payload or Postgres can handle the field filter.
- **Emerging trends** — “What recent work is similar to this topic?” We need similarity (vector search) plus a time filter (e.g., year ≥ 2020). Qdrant supports payload filters on the same collection, so we can combine kNN with a year condition in one query.
- **Enriching with other stores** — Once we have similar paper IDs from Qdrant, we can look up citation counts in Postgres or author networks in Neo4j. Qdrant does not replace those stores; it answers the “by content” part so the others can answer “by structure” or “by graph.”

Without a vector store, we would be limited to keyword or metadata filters and could not support true semantic discovery.

### Competency Questions Qdrant Answers

Qdrant is the **primary or sole store** used for:

1. **Which papers are most semantically similar to a given research question?** — The user enters free text; we embed it and run kNN on `papers_vectors`. Results are ranked by similarity (e.g., cosine score). Only a vector database can do this natively.

2. **Which papers are emerging trends based on semantic similarity?** — Same semantic search, plus a payload filter (e.g., `year >= since_year`) so we return similar papers that are also recent. Qdrant supports filtering on payload in the same request as the vector query.

Qdrant is used **together with Postgres or Neo4j** for:

3. **What is the relationship between paper citations and topic similarity?** — Qdrant returns papers similar to a query; we then use Postgres to fetch citation counts (or other aggregates) for those paper IDs and combine the two. Similarity comes from Qdrant; citation stats from Postgres.

4. **Which papers in one field could be relevant to another based on content similarity?** — We use Qdrant for semantic search (e.g., with a query representative of one field) and filter or rank by venue (source/target field). Postgres or payload can provide the venue metadata; Qdrant provides the content-based ranking.

5. **Topics connected via co-authorship** — We use Qdrant to find papers similar to a topic (query); then Neo4j to see how the authors of those papers are connected in the co-authorship graph. Similarity is from Qdrant; connectivity is from Neo4j.

In short: whenever the question is “find papers **similar by content/meaning**” or “rank or filter by **semantic similarity**,” Qdrant is the right store. For filters and aggregates (year, venue, citation counts) or for relationship and path queries, we use Postgres and Neo4j alongside it.

---

## How They All Connect

All analysis and serving are done through a **FastAPI** backend and optional **Streamlit** UI. We use:

- **psycopg** (or psycopg2) for Postgres
- **neo4j** Python driver for Neo4j
- **qdrant-client** for Qdrant

The **ingestion pipeline** (`python -m pipeline.cli`) reads the same CSV/Parquet and writes to all three stores with **consistent paper IDs**. The API implements a small “query router”: each competency question is answered by one or more stores, and when needed, results are combined (e.g., similar papers from Qdrant enriched with citation counts from Postgres).

---

## Infrastructure Setup

All three databases run in **Docker**. The project provides `infra/docker-compose.yml` with:

- **postgres** (image: postgres:16) — port 55432:5432 (or 5432 if you set host port to 5432)
- **neo4j** (image: neo4j:5) — ports 7474 (browser), 7687 (bolt); includes Graph Data Science plugin
- **qdrant** (image: qdrant/qdrant:v1.12.4) — ports 6333, 6334

To start the entire stack:

```bash
docker compose -f infra/docker-compose.yml up -d
```

Ensure the three containers are running and healthy before running the ingestion pipeline or the API. If Postgres is exposed on port 55432 (as in the default compose), set `POSTGRES_PORT=55432` in your environment or `.env` when running the pipeline and API from the host.

---

## Data Loading

### Option 1: Full pipeline from DBLP CSV/Parquet

If you have the raw DBLP file (e.g., `dblp-v10.parquet` or CSV):

```bash
pip install -r requirements.txt
pip install -e packages/pipeline

python -m pipeline.cli ingest --csv data/raw/dblp-v10.parquet --limit 50000 --truncate
```

This will:

1. Ensure Postgres schema exists (from `infra/postgres/init.sql`), then truncate if `--truncate` is set.
2. Ensure Neo4j constraints, then clear the graph if truncating.
3. Drop and recreate the Qdrant collection if truncating.
4. Read papers in batches, and for each batch: upsert into Postgres (papers, authors, paper_authors, citations), upsert into Neo4j (nodes and relationships), and embed and upsert into Qdrant.

`--limit` caps the number of rows for development; omit it for a full load.

### Option 2: Filtered dataset (Postgres + Qdrant, optional Neo4j)

If you have a pre-filtered CSV (e.g., `matched_main.csv`) and pre-generated Neo4j CSVs in `data/raw/` (`papers.csv`, `authors.csv`, `venues.csv`, `wrote.csv`, `paper_venue.csv`, `citations.csv`):

```bash
# Load into Postgres + Qdrant only
python -m pipeline.cli ingest-selected --truncate

# Also load Neo4j from the CSV bundle
python -m pipeline.cli ingest-selected --truncate --include-neo4j
```

Credentials (Postgres, Neo4j, Qdrant) are configurable via environment variables or `packages/pipeline/src/pipeline/settings.py`; adjust if your Docker ports or passwords differ.

---

## Design Considerations

### Why three stores?

- **Postgres:** Structured filters and aggregates (year, venue, citation counts). No single other store is optimized for all of these in the same way.
- **Neo4j:** Path and relationship queries (indirect citations, co-authorship, communities, bridges). Doing this in SQL is possible but complex and slow at scale.
- **Qdrant:** Semantic similarity (kNN over embeddings). Relational and graph stores do not natively support vector search.

We do not use the stores “for the sake of it”; each is justified by the competency questions it serves.

### Embedding model choice

We use **BAAI/bge-small-en-v1.5** via the **fastembed** library: no API keys, runs locally, and produces good quality for English title+abstract similarity. The pipeline could be switched to another model (e.g., OpenAI embeddings) by changing the embedder in the pipeline and re-ingesting.

### Data redundancy

The same logical entities (papers, authors, citations) appear in more than one store. We accept this redundancy to keep queries simple and to avoid expensive cross-store joins for every request. Paper `id` is the common key for joining results (e.g., Qdrant hits → Postgres for citation stats).

---

## Competency Questions and Use Cases

Each question below maps to one or more API endpoints and explicitly uses at least one of the three stores. The API responses include a `store_justification` field where applicable.

### 1. Which papers are most semantically similar to a given research question?

- **How it works:** User enters a free-text query. The query is embedded with the same model used for ingestion; Qdrant returns the top-k nearest vectors (cosine similarity). Results include paper_id, title, year, venue from the payload.
- **Endpoint:** `GET /semantic_search?q=...&k=10`
- **Store:** Qdrant (vector similarity cannot be done in Postgres or Neo4j alone).

### 2. Which authors collaborate most frequently?

- **How it works:** Neo4j matches pairs of authors that share at least one paper (co-authorship). We count distinct joint papers and return the top pairs.
- **Endpoint:** `GET /top_collaborators?limit=20`
- **Store:** Neo4j (graph pattern: shared neighbors on WROTE edges).

### 3. Can we suggest papers that cite a given paper indirectly?

- **How it works:** User provides a paper ID. Neo4j finds papers that cite the target in 1 to N hops (path query on CITES). Results are ordered by hop distance.
- **Endpoint:** `GET /indirect_citers?paper_id=...&max_hops=3&limit=20`
- **Store:** Neo4j (multi-hop path traversal).

### 4. Which author clusters dominate a (venue) field?

- **How it works:** Using venue as a proxy for field, we run community detection (e.g., Neo4j GDS) on the co-authorship subgraph for that venue and return top clusters or representative authors.
- **Endpoint:** `GET /author_clusters_by_venue?venue=...&top_k=5`
- **Store:** Neo4j (graph analytics).

### 5. Which papers are emerging trends based on semantic similarity?

- **How it works:** We run semantic search (Qdrant) and filter by recent years using payload (e.g., year ≥ threshold) to surface recently published papers similar to a query.
- **Endpoint:** `GET /emerging_trends?q=...&min_year=...&k=10`
- **Store:** Qdrant (vector search + payload filter).

### 6. Which authors act as bridges between research domains?

- **How it works:** We use graph metrics (e.g., betweenness) on the co-authorship or venue-linked graph to identify authors who connect different communities.
- **Endpoint:** `GET /bridge_authors?limit=10`
- **Store:** Neo4j (graph algorithms).

### 7. What is the relationship between paper citations and topic similarity?

- **How it works:** Qdrant returns papers similar to a query; we then use Postgres to fetch citation counts (or citation-related aggregates) for those paper IDs and combine the results.
- **Endpoint:** `GET /citations_vs_similarity?q=...&k=10`
- **Stores:** Qdrant (similarity) + Postgres (citation stats).

### 8. Which papers in one field could be relevant to another by content?

- **How it works:** Semantic search in Qdrant with optional filters (e.g., venue or year) to find papers in one “field” that are similar to a query or seed paper from another.
- **Endpoint:** `GET /cross_field_relevance?q=...&...`
- **Store:** Qdrant (and optionally Postgres for metadata filters).

### 9. Central but under-cited authors

- **How it works:** We use Neo4j to find authors central in the collaboration graph (e.g., degree or betweenness) and Postgres to get citation-related stats; we then rank or filter for “central but under-cited.”
- **Endpoint:** `GET /central_but_undercited?limit=10`
- **Stores:** Neo4j + Postgres.

### 10. Topics connected via co-authorship

- **How it works:** We combine Qdrant (to define “topics” or similar papers) with Neo4j (co-authorship links) to show how topics or clusters are connected through shared authors.
- **Endpoint:** `GET /topics_connected_via_coauthorship` (or similar)
- **Stores:** Qdrant + Neo4j.

*(Exact endpoint names and parameters may vary; see `apps/api/main.py` and the OpenAPI docs at `/docs` when the API is running.)*

---

## Limitations and Future Considerations

- **Data scale:** We use a subset of DBLP for development and demo. Full-scale ingestion would require more robust batching, indexing, and possibly distributed embedding.
- **Author disambiguation:** Authors are identified by name strings. Same-name different authors are not disambiguated; a proper solution would need an author-id resolution layer or external ontology.
- **Field/topic taxonomy:** “Field” is approximated by venue. A richer taxonomy (e.g., topic labels or keywords) would improve “field”-based analytics and cross-field relevance.
- **Embedding model and language:** The current model is English-oriented. Multilingual or domain-specific models could improve relevance for other languages or subfields.
- **Maintenance:** Keeping the three stores in sync (e.g., incremental updates, deletes) would require a more elaborate pipeline and possibly event-driven updates.

Future work could include: automated ingestion from DBLP or other APIs, a richer field/topic taxonomy, author disambiguation, and production hardening (auth, rate limits, caching).

---

## Reproducibility Summary

1. **Start databases:** `docker compose -f infra/docker-compose.yml up -d`
2. **Install dependencies:** `pip install -r requirements.txt && pip install -e packages/pipeline`
3. **Prepare data:** Place DBLP CSV/Parquet in `data/raw/` (and Neo4j CSVs if using `ingest-selected --include-neo4j`). Configure paths in `pipeline.settings` if needed.
4. **Ingest:**  
   - Full: `python -m pipeline.cli ingest --csv data/raw/dblp-v10.parquet --limit 50000 --truncate`  
   - Filtered: `python -m pipeline.cli ingest-selected --truncate --include-neo4j`
5. **Run API:** `uvicorn apps.api.main:app --reload --port 8000`
6. **Run UI:** `streamlit run apps/web/app.py`  
   - API docs: http://localhost:8000/docs  
   - Streamlit: http://localhost:8501

---

*End of Report*
