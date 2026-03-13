from __future__ import annotations

import csv
from collections.abc import Iterable

from neo4j import GraphDatabase

from .dblp import DblpPaper


CONSTRAINTS_CYPHER = """
CREATE CONSTRAINT paper_paperId IF NOT EXISTS
FOR (p:Paper) REQUIRE p.paperId IS UNIQUE;

CREATE CONSTRAINT author_authorName IF NOT EXISTS
FOR (a:Author) REQUIRE a.authorName IS UNIQUE;

CREATE CONSTRAINT venue_venueName IF NOT EXISTS
FOR (v:Venue) REQUIRE v.venueName IS UNIQUE;
"""


def ensure_constraints(driver) -> None:
    with driver.session() as session:
        for stmt in [s.strip() for s in CONSTRAINTS_CYPHER.split(";") if s.strip()]:
            session.run(stmt)


def clear_graph(driver) -> None:
    """
    Remove all Paper/Author/Venue nodes and their relationships.
    Safe for this project-specific Neo4j instance.
    """
    with driver.session() as session:
        session.run("MATCH (:Author)-[r]-() DELETE r")
        session.run("MATCH (:Paper)-[r]-() DELETE r")
        session.run("MATCH (:Venue)-[r]-() DELETE r")
        session.run("MATCH (n:Author) DELETE n")
        session.run("MATCH (n:Paper) DELETE n")
        session.run("MATCH (n:Venue) DELETE n")


def upsert_graph(driver, papers: Iterable[DblpPaper]) -> None:
    with driver.session() as session:
        for p in papers:
            session.run(
                """
                MERGE (paper:Paper {paperId: $paperId})
                SET paper.title = $title,
                    paper.year = $year,
                    paper.abstract = $abstract,
                    paper.n_citation = $n_citation
                """,
                paperId=p.id,
                title=p.title,
                year=p.year,
                abstract=p.abstract,
                n_citation=p.n_citation,
            )

            if p.venue:
                session.run(
                    """
                    MERGE (v:Venue {venueName: $venueName})
                    WITH v
                    MATCH (paper:Paper {paperId: $paperId})
                    MERGE (paper)-[:PUBLISHED_IN]->(v)
                    """,
                    venueName=p.venue,
                    paperId=p.id,
                )

            for author in p.authors:
                session.run(
                    """
                    MERGE (a:Author {authorName: $authorName})
                    WITH a
                    MATCH (paper:Paper {paperId: $paperId})
                    MERGE (a)-[:WROTE]->(paper)
                    """,
                    authorName=author,
                    paperId=p.id,
                )

            for ref in p.references:
                session.run(
                    """
                    MERGE (src:Paper {paperId: $src})
                    MERGE (dst:Paper {paperId: $dst})
                    MERGE (src)-[:CITES]->(dst)
                    """,
                    src=p.id,
                    dst=ref,
                )


def _iter_csv_rows(path: str):
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k: (v or "").strip() for k, v in row.items()}


def _iter_batches(items, batch_size: int):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_graph_from_csv_files(
    driver,
    papers_csv: str,
    authors_csv: str,
    venues_csv: str,
    wrote_csv: str,
    paper_venue_csv: str,
    citations_csv: str,
    batch_size: int = 1000,
) -> None:
    """
    Load Neo4j nodes/relationships directly from pre-generated CSV files.
    Assumes CSV schemas produced by the user's Neo4j export/preprocessing step.
    """
    with driver.session() as session:
        for rows in _iter_batches(_iter_csv_rows(papers_csv), batch_size):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (p:Paper {paperId: row.paperId})
                SET p.title = row.title,
                    p.year = CASE WHEN row.year = '' THEN NULL ELSE toInteger(row.year) END,
                    p.n_citation = CASE WHEN row.n_citation = '' THEN 0 ELSE toInteger(row.n_citation) END,
                    p.abstract = row.abstract
                """,
                rows=rows,
            )

        for rows in _iter_batches(_iter_csv_rows(authors_csv), batch_size):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (a:Author {authorName: row.authorName})
                """,
                rows=rows,
            )

        for rows in _iter_batches(_iter_csv_rows(venues_csv), batch_size):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (v:Venue {venueName: row.venueName})
                """,
                rows=rows,
            )

        for rows in _iter_batches(_iter_csv_rows(wrote_csv), batch_size):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Author {authorName: row.authorName})
                MATCH (p:Paper {paperId: row.paperId})
                MERGE (a)-[:WROTE]->(p)
                """,
                rows=rows,
            )

        for rows in _iter_batches(_iter_csv_rows(paper_venue_csv), batch_size):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (p:Paper {paperId: row.paperId})
                MATCH (v:Venue {venueName: row.venueName})
                MERGE (p)-[:PUBLISHED_IN]->(v)
                """,
                rows=rows,
            )

        for rows in _iter_batches(_iter_csv_rows(citations_csv), batch_size):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (p1:Paper {paperId: row.citingPaperId})
                MATCH (p2:Paper {paperId: row.citedPaperId})
                MERGE (p1)-[:CITES]->(p2)
                """,
                rows=rows,
            )


def neo4j_driver(uri: str, user: str, password: str):
    return GraphDatabase.driver(uri, auth=(user, password))

