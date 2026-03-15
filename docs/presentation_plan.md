# Presentation plan: Scientific Paper Knowledge Graph & Semantic Search

**Total:** 15 minutes + 5 min Q&A  
**Goal:** Show what the tool does, why each store is needed, and how they fit together.

---

## Slide 1 — Title (≈20 s)

**Title:** Scientific Paper Knowledge Graph & Semantic Search  

**Subtitle (optional):** Explore research relationships, authorship networks, and semantic similarity  

**Footer:** DSC 202 Final Project | [Date] | [Team names]

- No bullets. Clean title slide.

---

## Slide 2 — The problem: literature review is hard (≈45 s)

**Title:** The problem  

**Bullets:**
- Researchers struggle with **literature review**
- Need to find **existing solutions** to a problem and **recent work** (e.g. last 5 years)
- **Keyword search** only matches words → misses papers that say the same thing in different terms
- Need to understand **how work connects**: who cites whom, who collaborates with whom

**Visual:** One image or simple diagram (e.g. “keyword search misses similar papers” or researcher overwhelmed by papers)

**Speaker note:** Set up that one tool can’t do everything.

---

## Slide 3 — Why citation & author graphs? (≈30 s)

**Title:** Why citation and author graphs?  

**Bullets:**
- **Citation graph:** “What papers cite this one *indirectly*?” = following links multiple steps → needs **graph traversal**
- **Author graph:** “Who collaborates most? Who bridges domains?” = **relationships** between people via papers → natural as a **graph**
- Relational tables can store edges but **path and community queries** are awkward and slow

**Speaker note:** This justifies Neo4j before we show the three stores.

---

## Slide 4 — What we need (one line) (≈15 s)

**Title:** What we need  

**Bullets (or one sentence):**
- Find papers **by meaning** (semantic similarity)
- **Filter** by year, venue, citations (structured data)
- **Explore** citation chains and author collaborations (graph)

**Speaker note:** “No single database does all three well → we use three.”

---

## Slide 5 — Our solution: three stores (≈45 s)

**Title:** Our solution  

**Content:** Three boxes or three bullets:

| Store    | Role in one line |
|----------|-------------------|
| **Postgres** | Structured data: filter by year/venue, analytics, citation counts |
| **Neo4j**    | Citation + author graph: indirect citations, collaborations, clusters, bridges |
| **Qdrant**   | Vector search: find papers similar to a question or to another paper |

**Speaker note:** “Each store is there for a reason; we’ll show which questions each answers.”

---

## Slide 6 — Competency questions we answer (≈30 s)

**Title:** Questions our tool answers  

**Bullets (pick 4–6 from Topic_Details.md):**
- Which papers are most **semantically similar** to a research question?
- Which authors **collaborate** most frequently?
- Can we suggest papers that cite a given paper **indirectly**?
- Which **author clusters** dominate a field? Who are **bridge** authors?
- What is the relationship between **citations and topic similarity**?
- Which papers in one field could be **relevant to another** by content?

**Speaker note:** “These drive our schema and demo; each question ties to at least one store.”

---

## Slide 7 — Section: The data (≈5 s)

**Title:** The data  

**Subtitle (optional):** DBLP CSV → three stores  

- Section header only. No bullets.

---

## Slide 8 — Data source: DBLP (≈30 s)

**Title:** Data source: DBLP CSV  

**Bullets:**
- **Input:** DBLP-derived CSV (e.g. `matched_main.csv` + Neo4j CSVs)
- **Fields:** paper id, title, abstract, venue, year, n_citation, authors, references
- **Parsing:** authors and references as lists; same IDs used across all three stores

**Speaker note:** Brief; details are in the report.

---

## Slide 9 — Postgres: what and why (≈30 s)

**Title:** Postgres — relational  

**Bullets:**
- **What:** Papers, authors, paper_authors, citations (tables + ERD)
- **Why:** Fast **filters** (year, venue), **aggregates** (citation counts, top venues), **joins** to enrich results from other stores

**Visual:** Postgres ERD from `docs/schemas.md` (export Mermaid as image or redraw).

---

## Slide 10 — Neo4j: what and why (≈30 s)

**Title:** Neo4j — graph  

**Bullets:**
- **What:** Nodes: Paper, Author, Venue. Edges: WROTE, CITES, PUBLISHED_IN
- **Why:** **Multi-hop** citation paths, **co-authorship** and collaboration frequency, **clusters** and **bridges** (e.g. GDS)

**Visual:** Neo4j graph diagram from `docs/schemas.md`.

---

## Slide 11 — Qdrant: what and why (≈30 s)

**Title:** Qdrant — vector  

**Bullets:**
- **What:** Collection `papers_vectors`: embed **title + abstract**, payload (paper_id, title, year, venue)
- **Why:** **Semantic similarity** (kNN) — “papers like this question/abstract”; neither Postgres nor Neo4j do this natively

**Visual:** Simple diagram: text → embed → vector → kNN search (from `docs/schemas.md`).

---

## Slide 12 — How it all connects (≈45 s)

**Title:** How it all connects  

**Visual:** One diagram: **CSV → pipeline → Postgres / Neo4j / Qdrant → API (FastAPI) → UI (Streamlit)**  

**Bullets (short):**
- One ingestion pipeline fills all three stores with consistent IDs
- API routes queries to the right store(s); UI calls the API

**Speaker note:** “Demo will show these working together.”

---

## Slide 13 — Section: Demo (≈5 s)

**Title:** Demo  

**Subtitle (optional):** Scripted flows  

- Section header. Then start demo.

---

## Slides 14–15 — Demo (5–6 min total)

**No new slides during demo.** Use the app (Streamlit) and optionally API docs.

**Suggested order (from demo_script.md):**
1. **Semantic search (Qdrant):** “Papers similar to a research question” — search box → results. Say: “This is Qdrant; only a vector store does this.”
2. **Collaborations (Neo4j):** “Authors who collaborate most” — show results. Say: “This is the author graph in Neo4j.”
3. **Indirect citations (Neo4j):** “Papers that cite this paper indirectly” — pick a paper → show paths. Say: “Multi-hop traversal in the citation graph.”
4. **Cross-store (Qdrant + Postgres):** “Citations vs similarity” — similar papers + citation counts. Say: “Qdrant for similarity, Postgres for citation stats.”

**Speaker note:** Keep to 5–6 min; if behind, skip or shorten one flow.

---

## Slide 16 — What we showed (demo recap) (≈20 s)

**Title:** What we showed  

**Bullets:**
- Semantic search → **Qdrant**
- Collaborations & indirect citations → **Neo4j**
- Citation counts & filters → **Postgres**
- Combined analysis → **Qdrant + Postgres** (and/or Neo4j)

**Speaker note:** Quick recap so store–question mapping is clear.

---

## Slide 17 — Putting it all together (≈30 s)

**Title:** Putting it all together  

**Bullets (numbered list):**
1. **Semantic search** (Qdrant) for “papers like this.”
2. **Citation and author graphs** (Neo4j) for indirect citations, collaborations, clusters.
3. **Structured data** (Postgres) for filters and analytics.
4. **Combined** queries when we need similarity + citations or metadata.

**Speaker note:** “Three stores, each justified by the questions we need to answer.”

---

## Slide 18 — Limitations & next steps (≈30 s)

**Title:** Limitations & next steps  

**Bullets:**
- Author name disambiguation (same name, different people)
- Field/topic taxonomy could be richer
- Scale: subset for dev; full dataset and indexing for production
- Embedding model and language (e.g. English-only)

**Speaker note:** One sentence each; “we’d improve these in a follow-up.”

---

## Slide 19 — Thank you / Q&A (≈15 s)

**Title:** Thank you  

**Bullets (optional):**
- Demo: [local or deployed URL]
- Repo: [GitHub link]
- Questions?

---

## Backup slides (for Q&A)

**Slide B1 — Store justification per question**  
Table: Competency question → Store(s) used (Postgres / Neo4j / Qdrant). Use if someone asks “why Neo4j for X?”

**Slide B2 — Schema reference**  
Same ERD + graph + Qdrant diagrams. Use if someone asks about schema details.

**Slide B3 — Pipeline / scaling**  
Brief note on ingestion (subset vs full, memory/time). Use if someone asks about scale or reproducibility.

---

## Time summary

| Section           | Slides   | Time    |
|------------------|----------|---------|
| Title            | 1        | 0:20    |
| Problem          | 2–4      | 1:30    |
| Solution + goals | 5–6      | 1:15    |
| Data             | 7–12     | 2:50    |
| Demo             | 13–15    | 5:30    |
| Recap + limitations + close | 16–19 | 1:35    |
| **Total**        | **19**   | **~15 min** |

Adjust by speaking faster/slower; demo is the main variable (keep 5–6 min).

---

## Checklist before presenting

- [ ] All three schema diagrams on slides (Postgres ERD, Neo4j graph, Qdrant)
- [ ] One “problem” image or diagram
- [ ] “How it all connects” pipeline diagram
- [ ] Demo pre-run: Docker up, data ingested, API + Streamlit working
- [ ] Backup slides for store justification and schemas
