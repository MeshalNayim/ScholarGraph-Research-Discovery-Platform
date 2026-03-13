## API service

Run locally (after bringing up Docker services and ingesting data):

```bash
python -m pipeline.cli ingest-selected --truncate --include-neo4j
uvicorn apps.api.main:app --reload --port 8000
```

Ingestion notes:

- Postgres and Qdrant are loaded from `data/raw/matched_main.csv`.
- Neo4j is loaded from the CSV bundle in `data/raw/` (`papers.csv`, `authors.csv`, `venues.csv`, `wrote.csv`, `paper_venue.csv`, `citations.csv`).

Endpoints correspond to the competency questions in `resources/Topic_Details.md` and include a `store_justification` field in responses.

