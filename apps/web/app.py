from __future__ import annotations

import os

import httpx
import streamlit as st


API_BASE = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Paper KG + Semantic Search", layout="wide")
st.title("Scientific Paper Knowledge Graph & Semantic Search")

st.caption(
    "Semantic search (Qdrant) + relationship exploration (Neo4j) + structured analytics (Postgres)."
)


def get(path: str, params: dict | None = None):
    with httpx.Client(timeout=60.0) as client:
        r = client.get(f"{API_BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()


tab1, tab2, tab3, tab4 = st.tabs(
    ["Semantic search", "Graph exploration", "Cross-store analytics", "Graph analytics (GDS)"]
)

with tab1:
    q = st.text_input("Research question / query", value="graph neural networks for citation prediction")
    k = st.slider("Top K", 5, 30, 10)
    if st.button("Search"):
        data = get("/semantic_search", {"q": q, "k": k})
        st.subheader("Results")
        st.write(data["results"])
        st.info(data["store_justification"])

with tab2:
    st.subheader("Top collaborators (co-authorship)")
    if st.button("Compute top collaborator pairs"):
        data = get("/top_collaborators", {"limit": 20})
        st.write(data["results"])
        st.info(data["store_justification"])

    st.divider()
    st.subheader("Indirect citers of a paper (citation paths)")
    pid = st.text_input("Paper UUID", value="")
    hops = st.slider("Max hops", 1, 5, 3)
    if st.button("Find indirect citers"):
        if not pid.strip():
            st.warning("Enter a paper UUID.")
        else:
            data = get("/indirect_citers", {"paper_id": pid.strip(), "max_hops": hops, "limit": 20})
            st.write(data["results"])
            st.info(data["store_justification"])

with tab3:
    st.subheader("Citations vs similarity")
    q2 = st.text_input("Topic query", value="entity resolution blocking techniques")
    if st.button("Analyze citations vs similarity"):
        data = get("/citations_vs_similarity", {"q": q2, "k": 20})
        st.write(data["results"])
        st.info(data["store_justification"])

    st.divider()
    st.subheader("Emerging trends (recent papers similar to query)")
    since = st.number_input("Since year", value=2020, min_value=1950, max_value=2100)
    if st.button("Find emerging papers"):
        data = get("/emerging_trends", {"q": q2, "since_year": int(since), "k": 20})
        st.write(data["results"])
        st.info(data["store_justification"])

    st.divider()
    st.subheader("Cross-field relevance (by venue)")
    source_venue = st.text_input("Source venue (label only, MVP)", value="Neurocomputing")
    target_venue = st.text_input("Target venue", value="international conference on computer vision")
    if st.button("Find cross-field relevant papers"):
        data = get(
            "/cross_field_relevance",
            {
                "source_venue": source_venue,
                "target_venue": target_venue,
                "q": q2,
                "k": 20,
            },
        )
        st.write(data["results"])
        st.info(data["store_justification"])

    st.divider()
    st.subheader("Central but under-cited authors")
    if st.button("Find central-but-undercited"):
        data = get("/central_but_undercited", {"limit": 20})
        st.write(data["results"])
        st.info(data["store_justification"])

    st.divider()
    st.subheader("Topics connected via co-authorship")
    if st.button("Compute topic connectivity"):
        data = get("/topics_connected_via_coauthorship", {"q": q2, "k": 30})
        st.write(
            {
                "author_count": data.get("author_count"),
                "coauth_links": data.get("coauth_links"),
                "paper_sample_size": data.get("paper_sample_size"),
            }
        )
        st.info(data["store_justification"])
        st.caption(data.get("note", ""))

with tab4:
    st.subheader("Author clusters dominating a venue (Louvain)")
    venue = st.text_input("Venue (field proxy)", value="Neurocomputing")
    if st.button("Compute clusters"):
        data = get("/author_clusters_by_venue", {"venue": venue, "top_k": 5})
        st.write(data["top_communities"])
        st.info(data["store_justification"])
        st.caption(data.get("note", ""))

    st.divider()
    st.subheader("Bridge authors (betweenness centrality)")
    if st.button("Compute bridge authors"):
        data = get("/bridge_authors", {"limit": 20})
        st.write(data["results"])
        st.info(data["store_justification"])

