## Scientific Paper Knowledge Graph & Semantic Search

This project ingests the DBLP CSV dataset into:

- **Postgres** (relational): structured paper metadata, authors, and citation edges for filtering + analytics
- **Neo4j** (graph): authorship + citation graph for multi-hop queries (indirect citations, collaboration networks, bridges, clusters)
- **Qdrant** (vector): embeddings of `title + abstract` for semantic search and content-based similarity

It then exposes a small API and demo UI to answer the competency questions in `resources/Topic_Details.md`.

### Repository layout

- `infra/`: docker-compose + database initialization
- `packages/pipeline/`: ingestion + query client code (shared)
- `apps/api/`: FastAPI service (query router)
- `apps/web/`: Streamlit UI (demo)
- `docs/`: schema diagrams + report/slides materials
- `data/`: raw input dataset (provided)

### Quickstart

1) Bring up the stores (Postgres, Neo4j, Qdrant):

```bash
docker compose -f infra/docker-compose.yml up -d
```

2) Create a virtual environment and install deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e packages/pipeline
```

3) Copy env and fill in values as needed:

```bash
cp .env.example .env
```

4) Ingest a subset of the dataset (recommended for development):

```bash
python3 -m pipeline.cli --csv data/raw/dblp-v10.csv --limit 5000
```

If you want to **wipe and reload everything fresh** (all three stores), add `--truncate`:

```bash
python3 -m pipeline.cli --csv data/raw/dblp-v10.csv --limit 5000 --truncate
```

5) Run the API (terminal 1):

```bash
cd /Users/js/Downloads/DSC202_Project_V2
source .venv/bin/activate
uvicorn apps.api.main:app --reload --port 8000
```

6) Run the Streamlit UI (terminal 2):

```bash
cd /Users/js/Downloads/DSC202_Project_V2
source .venv/bin/activate
streamlit run apps/web/app.py
```

Once both are running, open the Streamlit URL (typically `http://localhost:8501`) in your browser and use the tabs to exercise the Qdrant, Neo4j, and Postgres-backed queries.

