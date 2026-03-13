from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Dataset
    dblp_csv_path: str = "data/raw/dblp-v10.csv"
    dblp_parquet_path: str = "data/raw/dblp-v10.parquet"
    dblp_filtered_csv_path: str = "data/raw/matched_main.csv"

    # Neo4j pre-generated CSV imports
    neo4j_papers_csv_path: str = "data/raw/papers.csv"
    neo4j_authors_csv_path: str = "data/raw/authors.csv"
    neo4j_venues_csv_path: str = "data/raw/venues.csv"
    neo4j_wrote_csv_path: str = "data/raw/wrote.csv"
    neo4j_paper_venue_csv_path: str = "data/raw/paper_venue.csv"
    neo4j_citations_csv_path: str = "data/raw/citations.csv"

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "papers"
    postgres_user: str = "papers"
    postgres_password: str = "papers"

    # Neo4j
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "papers_vectors"

    # Embeddings
    embedding_provider: str = "fastembed"
    fastembed_model: str = "BAAI/bge-small-en-v1.5"

    def postgres_dsn(self) -> str:
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"dbname={self.postgres_db} user={self.postgres_user} password={self.postgres_password}"
        )


settings = Settings()

