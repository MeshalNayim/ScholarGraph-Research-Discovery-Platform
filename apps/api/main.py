from __future__ import annotations

from typing import Any, Optional

import psycopg
from fastapi import FastAPI
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from pipeline.settings import Settings


settings = Settings()
app = FastAPI(title="Scientific Paper KG API")


def pg_conn():
    return psycopg.connect(settings.postgres_dsn())


def neo4j_driver():
    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


def qdrant_client():
    return QdrantClient(url=settings.qdrant_url)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stats")
def stats() -> dict[str, Any]:
    """Dashboard statistics from all three stores."""
    # Postgres counts
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM papers")
        total_papers = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM authors")
        total_authors = cur.fetchone()[0]
        cur.execute(
            "SELECT count(DISTINCT venue) FROM papers WHERE venue IS NOT NULL AND venue != ''"
        )
        total_venues = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(n_citation),0) FROM papers")
        total_citations = cur.fetchone()[0]
        cur.execute(
            "SELECT venue, count(*) AS cnt FROM papers WHERE venue IS NOT NULL AND venue != '' "
            "GROUP BY venue ORDER BY cnt DESC LIMIT 10"
        )
        top_venues = [{"venue": r[0], "count": r[1]} for r in cur.fetchall()]
        cur.execute(
            "SELECT year, count(*) AS cnt FROM papers WHERE year IS NOT NULL "
            "GROUP BY year ORDER BY year"
        )
        papers_by_year = [{"year": r[0], "count": r[1]} for r in cur.fetchall()]

    # Neo4j counts
    driver = neo4j_driver()
    with driver.session() as s:
        neo4j_nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        neo4j_rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    driver.close()

    # Qdrant count
    qc = qdrant_client()
    col = qc.get_collection(settings.qdrant_collection)
    qdrant_vectors = col.points_count

    return {
        "postgres": {
            "papers": total_papers,
            "authors": total_authors,
            "venues": total_venues,
            "total_citations": total_citations,
            "top_venues": top_venues,
            "papers_by_year": papers_by_year,
        },
        "neo4j": {"nodes": neo4j_nodes, "relationships": neo4j_rels},
        "qdrant": {"vectors": qdrant_vectors},
    }


@app.get("/semantic_search")
def semantic_search(q: str, k: int = 10) -> dict[str, Any]:
    """
    Which papers are most semantically similar to a given research question?
    Uses Qdrant vector similarity search (cosine) over embedded title+abstract.
    """
    from fastembed import TextEmbedding

    embedder = TextEmbedding(model_name=settings.fastembed_model)
    vec = next(embedder.embed([q]))

    qc = qdrant_client()
    res = qc.query_points(
        collection_name=settings.qdrant_collection,
        query=vec.tolist(),
        limit=k,
        with_payload=True,
    )
    hits = res.points
    return {
        "query": q,
        "results": [
            {
                "paper_id": h.payload.get("paper_id") if h.payload else None,
                "score": h.score,
                "title": (h.payload or {}).get("title"),
                "year": (h.payload or {}).get("year"),
                "venue": (h.payload or {}).get("venue"),
            }
            for h in hits
        ],
        "store_justification": "Vector similarity search requires Qdrant; relational/graph stores do not natively support semantic nearest-neighbor retrieval.",
    }


@app.get("/top_collaborators")
def top_collaborators(limit: int = 20) -> dict[str, Any]:
    """
    Which authors collaborate most frequently?
    Uses Neo4j graph edges via shared papers to compute coauthor counts.
    """
    driver = neo4j_driver()
    query = """
    MATCH (a1:Author)-[:WROTE]->(p:Paper)<-[:WROTE]-(a2:Author)
    WHERE a1.authorName < a2.authorName
    WITH a1, a2, count(DISTINCT p) AS joint_papers
    ORDER BY joint_papers DESC
    RETURN a1.authorName AS author1, a2.authorName AS author2, joint_papers
    LIMIT $limit
    """
    with driver.session() as s:
        rows = [r.data() for r in s.run(query, limit=limit)]
    driver.close()
    return {
        "results": rows,
        "store_justification": "Co-authorship is inherently a graph pattern (shared neighbors). Neo4j expresses and executes this relationship query naturally.",
    }


@app.get("/indirect_citers")
def indirect_citers(
    paper_id: str, max_hops: int = 3, limit: int = 20
) -> dict[str, Any]:
    """
    Suggest relevant papers that cite a given paper indirectly.
    Uses Neo4j path queries over the citation graph.
    """
    driver = neo4j_driver()
    query = f"""
    MATCH (target:Paper {{paperId: $paper_id}})
    MATCH path = (src:Paper)-[:CITES*1..{max_hops}]->(target)
    WITH src, min(length(path)) AS hops
    RETURN src.paperId AS paper_id, src.title AS title, hops
    ORDER BY hops ASC
    LIMIT $limit
    """
    with driver.session() as s:
        rows = [r.data() for r in s.run(query, paper_id=paper_id, limit=limit)]
    driver.close()
    return {
        "paper_id": paper_id,
        "results": rows,
        "store_justification": "Indirect citation recommendations require multi-hop traversal over citation edges, which is a core strength of graph databases.",
    }


@app.get("/author_clusters_by_venue")
def author_clusters_by_venue(venue: str, top_k: int = 5) -> dict[str, Any]:
    """
    Which author clusters dominate a research field?
    Approximate 'field' by venue string; compute communities on co-authorship graph
    restricted to papers in that venue using Neo4j Graph Data Science (Louvain).
    """
    driver = neo4j_driver()
    with driver.session() as s:
        exists = s.run(
            "CALL gds.graph.exists('venueGraph') YIELD exists RETURN exists"
        ).single()
        if exists and exists.get("exists"):
            s.run(
                "CALL gds.graph.drop('venueGraph') YIELD graphName RETURN graphName"
            ).consume()

        # Use Cypher aggregation projection (modern GDS syntax)
        s.run(
            """
            MATCH (a1:Author)-[:WROTE]->(p:Paper)<-[:WROTE]-(a2:Author)
            WHERE (p)-[:PUBLISHED_IN]->(:Venue {venueName: $venue})
              AND id(a1) < id(a2)
            WITH a1, a2, count(p) AS weight
            WITH gds.graph.project('venueGraph', a1, a2, {relationshipProperties: {weight: weight}}) AS g
            RETURN g.graphName AS graph, g.nodeCount AS nodes, g.relationshipCount AS rels
            """,
            venue=venue,
        ).consume()

        # Louvain community detection
        communities = list(
            s.run(
                """
                CALL gds.louvain.stream('venueGraph', {relationshipWeightProperty: 'weight'})
                YIELD nodeId, communityId
                RETURN communityId, count(*) AS size
                ORDER BY size DESC
                LIMIT $k
                """,
                k=top_k,
            )
        )
        top = [r.data() for r in communities]

        s.run(
            "CALL gds.graph.drop('venueGraph') YIELD graphName RETURN graphName"
        ).consume()
    driver.close()
    return {
        "venue": venue,
        "top_communities": top,
        "store_justification": "Communities/clusters are graph structure. Neo4j GDS provides community detection directly on the co-authorship graph.",
        "note": "Field is approximated by venue for the MVP; you can replace this with a richer field taxonomy later.",
    }


@app.get("/emerging_trends")
def emerging_trends(q: str, since_year: int = 2020, k: int = 20) -> dict[str, Any]:
    """
    Which papers are emerging trends based on semantic similarity?
    Uses Qdrant semantic search + year filter (payload) to focus on recent work.
    """
    from fastembed import TextEmbedding

    embedder = TextEmbedding(model_name=settings.fastembed_model)
    vec = next(embedder.embed([q]))
    qc = qdrant_client()

    res = qc.query_points(
        collection_name=settings.qdrant_collection,
        query=vec.tolist(),
        limit=k,
        with_payload=True,
        query_filter={
            "must": [
                {"key": "year", "range": {"gte": since_year}},
            ]
        },
    )
    hits = res.points
    return {
        "query": q,
        "since_year": since_year,
        "results": [
            {
                "paper_id": h.payload.get("paper_id") if h.payload else None,
                "score": h.score,
                "title": (h.payload or {}).get("title"),
                "year": (h.payload or {}).get("year"),
                "venue": (h.payload or {}).get("venue"),
            }
            for h in hits
        ],
        "store_justification": "Emerging-trend discovery needs semantic similarity (vector search) plus structured time filtering; Qdrant supports payload filtering with kNN.",
    }


@app.get("/bridge_authors")
def bridge_authors(limit: int = 20) -> dict[str, Any]:
    """
    Which authors act as bridges between research domains?
    Uses Neo4j GDS betweenness centrality on the co-authorship graph.
    """
    driver = neo4j_driver()
    with driver.session() as s:
        exists = s.run(
            "CALL gds.graph.exists('coauthorGraph') YIELD exists RETURN exists"
        ).single()
        if exists and exists.get("exists"):
            s.run(
                "CALL gds.graph.drop('coauthorGraph') YIELD graphName RETURN graphName"
            ).consume()

        # Use Cypher aggregation projection (modern GDS syntax)
        s.run(
            """
            MATCH (a1:Author)-[:WROTE]->(p:Paper)<-[:WROTE]-(a2:Author)
            WHERE id(a1) < id(a2)
            WITH a1, a2, count(p) AS weight
            WITH gds.graph.project('coauthorGraph', a1, a2, {relationshipProperties: {weight: weight}}) AS g
            RETURN g.graphName AS graph, g.nodeCount AS nodes, g.relationshipCount AS rels
            """
        ).consume()

        rows = [
            r.data()
            for r in s.run(
                """
                CALL gds.betweenness.stream('coauthorGraph', {relationshipWeightProperty: 'weight'})
                YIELD nodeId, score
                WITH gds.util.asNode(nodeId) AS a, score
                RETURN a.authorName AS author, score
                ORDER BY score DESC
                LIMIT $limit
                """,
                limit=limit,
            )
        ]
        s.run(
            "CALL gds.graph.drop('coauthorGraph') YIELD graphName RETURN graphName"
        ).consume()
    driver.close()
    return {
        "results": rows,
        "store_justification": "Bridge detection is a network-structure problem (betweenness). Graph analytics belong in Neo4j/GDS, not SQL or vector search.",
    }


@app.get("/citations_vs_similarity")
def citations_vs_similarity(q: str, k: int = 20) -> dict[str, Any]:
    """
    Relationship between paper citations and topic similarity.
    Uses Qdrant to retrieve similar papers, then Postgres for citation counts/statistics.
    """
    from fastembed import TextEmbedding

    embedder = TextEmbedding(model_name=settings.fastembed_model)
    vec = next(embedder.embed([q]))
    qc = qdrant_client()
    res = qc.query_points(
        collection_name=settings.qdrant_collection,
        query=vec.tolist(),
        limit=k,
        with_payload=True,
    )
    hits = res.points
    paper_ids = [
        h.payload.get("paper_id")
        for h in hits
        if h.payload and h.payload.get("paper_id")
    ]

    rows: list[dict[str, Any]] = []
    if paper_ids:
        with pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, n_citation, year, venue, title
                FROM papers
                WHERE id = ANY(%s::uuid[])
                """,
                (paper_ids,),
            )
            by_id = {
                r[0]: {"n_citation": r[1], "year": r[2], "venue": r[3], "title": r[4]}
                for r in cur.fetchall()
            }

        for h in hits:
            pid = (h.payload or {}).get("paper_id")
            if not pid:
                continue
            meta = by_id.get(pid, {})
            rows.append(
                {
                    "paper_id": pid,
                    "similarity_score": h.score,
                    "n_citation": meta.get("n_citation"),
                    "year": meta.get("year"),
                    "venue": meta.get("venue"),
                    "title": meta.get("title") or (h.payload or {}).get("title"),
                }
            )

    return {
        "query": q,
        "results": rows,
        "store_justification": "Similarity comes from vector search (Qdrant); citation counts and structured stats come from the relational store (Postgres).",
    }


@app.get("/cross_field_relevance")
def cross_field_relevance(
    source_venue: str, target_venue: str, q: str, k: int = 20
) -> dict[str, Any]:
    """
    Which papers in one field could be relevant to another based on content similarity?
    Uses Postgres to constrain candidate papers by venue, Qdrant for semantic search,
    then filters to target venue via payload.
    """
    from fastembed import TextEmbedding

    embedder = TextEmbedding(model_name=settings.fastembed_model)
    vec = next(embedder.embed([q]))

    qc = qdrant_client()
    res = qc.query_points(
        collection_name=settings.qdrant_collection,
        query=vec.tolist(),
        limit=k,
        with_payload=True,
        query_filter={
            "must": [
                {"key": "venue", "match": {"value": target_venue}},
            ]
        },
    )
    hits = res.points
    return {
        "source_venue": source_venue,
        "target_venue": target_venue,
        "query": q,
        "results": [
            {
                "paper_id": (h.payload or {}).get("paper_id"),
                "score": h.score,
                "title": (h.payload or {}).get("title"),
                "year": (h.payload or {}).get("year"),
                "venue": (h.payload or {}).get("venue"),
            }
            for h in hits
        ],
        "store_justification": "Cross-field relevance is content-based (vector search in Qdrant) while the concept of 'field' is represented as structured metadata (venue/category), typically stored in Postgres or payload filters.",
    }


@app.get("/central_but_undercited")
def central_but_undercited(limit: int = 20) -> dict[str, Any]:
    """
    Are there authors whose work is central in the network but under-cited?
    Uses Neo4j degree centrality + Postgres for aggregate citations per author.
    """
    driver = neo4j_driver()
    with driver.session() as s:
        rows = [
            r.data()
            for r in s.run(
                """
                MATCH (a:Author)-[:WROTE]->(:Paper)<-[:WROTE]-(b:Author)
                WHERE a <> b
                WITH a, count(DISTINCT b) AS coauthor_degree
                RETURN a.authorName AS author, coauthor_degree
                ORDER BY coauthor_degree DESC
                LIMIT $limit
                """,
                limit=limit * 5,
            )
        ]
    driver.close()

    # Enrich with citations from Postgres
    authors = [r["author"] for r in rows]
    citations_by_author: dict[str, int] = {}
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.name, COALESCE(SUM(p.n_citation), 0) AS total_citations
            FROM authors a
            JOIN paper_authors pa ON pa.author_id = a.author_id
            JOIN papers p ON p.id = pa.paper_id
            WHERE a.name = ANY(%s)
            GROUP BY a.name
            """,
            (authors,),
        )
        for name, total in cur.fetchall():
            citations_by_author[name] = int(total)

    combined = [
        {
            "author": r["author"],
            "coauthor_degree": r["coauthor_degree"],
            "total_citations": citations_by_author.get(r["author"], 0),
        }
        for r in rows
    ]
    combined.sort(key=lambda x: (-x["coauthor_degree"], x["total_citations"]))
    return {
        "results": combined[:limit],
        "store_justification": "Network centrality comes from graph structure (Neo4j), while citation totals are structured aggregates (Postgres). Combining them reveals central-but-undercited authors.",
    }


@app.get("/topics_connected_via_coauthorship")
def topics_connected_via_coauthorship(q: str, k: int = 30) -> dict[str, Any]:
    """
    Which topics are most connected via co-authorship networks?
    MVP: treat the user's query as a 'topic' representation; retrieve semantically similar papers (Qdrant),
    then use Neo4j to compute how interconnected their authors are (edges among those authors).
    """
    from fastembed import TextEmbedding

    embedder = TextEmbedding(model_name=settings.fastembed_model)
    vec = next(embedder.embed([q]))
    qc = qdrant_client()
    res = qc.query_points(
        collection_name=settings.qdrant_collection,
        query=vec.tolist(),
        limit=k,
        with_payload=True,
    )
    hits = res.points
    paper_ids = [
        h.payload.get("paper_id")
        for h in hits
        if h.payload and h.payload.get("paper_id")
    ]

    driver = neo4j_driver()
    with driver.session() as s:
        res = s.run(
            """
            MATCH (p:Paper)<-[:WROTE]-(a:Author)
            WHERE p.paperId IN $paper_ids
            WITH collect(DISTINCT a) AS authors
            UNWIND authors AS a1
            UNWIND authors AS a2
            WITH a1, a2 WHERE a1 <> a2
            MATCH (a1)-[:WROTE]->(:Paper)<-[:WROTE]-(a2)
            RETURN count(DISTINCT a1) AS author_count, count(*) AS coauth_links
            """,
            paper_ids=paper_ids,
        ).single()
    driver.close()

    return {
        "query_topic": q,
        "paper_sample_size": len(paper_ids),
        "author_count": res["author_count"] if res else 0,
        "coauth_links": res["coauth_links"] if res else 0,
        "store_justification": "Topic similarity is derived from embeddings (Qdrant), while connectivity is a co-authorship network property (Neo4j).",
        "note": "For a richer notion of 'topic', add topic labels via clustering or taxonomy and compute connectivity per topic label.",
    }
