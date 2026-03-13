## Neo4j graph model (graph element)

### Node labels
- `:Paper` with properties `{paperId, title, year, abstract, n_citation}`
- `:Author` with property `{authorName}`
- `:Venue` with property `{venueName}`

### Relationship types
- `(:Author)-[:WROTE]->(:Paper)`
- `(:Paper)-[:PUBLISHED_IN]->(:Venue)`
- `(:Paper)-[:CITES]->(:Paper)`

### Constraints / indexes
- Unique constraints on `Paper.paperId`, `Author.authorName`, and `Venue.venueName`
- Index on `Paper.year`

### Ingestion source (current workflow)
- Neo4j is loaded directly from pre-generated CSV files under `data/raw/`:
	- `papers.csv`
	- `authors.csv`
	- `venues.csv`
	- `wrote.csv`
	- `paper_venue.csv`
	- `citations.csv`
- This load is performed by `load_graph_from_csv_files(...)` in `packages/pipeline/src/pipeline/neo4j_loader.py`.
- Use `python -m pipeline.cli ingest-selected --truncate --include-neo4j` to refresh the graph from these CSVs.

### Why Neo4j is required (mapped to competency questions)
- Indirect citation recommendations require multi-hop traversal over `:CITES` paths.
- Collaboration frequency and author networks are naturally expressed via shared `:WROTE` neighborhoods.
- "Clusters" and "bridges" are graph analytics problems (community detection / betweenness), handled via Neo4j GDS.
- `Venue` as a first-class node enables co-authorship community detection scoped to a publication venue via `[:PUBLISHED_IN]`.

