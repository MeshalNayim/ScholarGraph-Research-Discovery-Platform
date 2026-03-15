from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st


API_BASE = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Research Discovery and Influence Analysis Tool", layout="wide")
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem;
        max-width: 1200px;
    }
    .hero {
        background: linear-gradient(120deg, #0f172a 0%, #1f2937 45%, #0b3b66 100%);
        border-radius: 16px;
        padding: 1.2rem 1.4rem;
        color: #e5f3ff;
        margin-bottom: 1rem;
        border: 1px solid rgba(148, 163, 184, 0.25);
    }
    .hero h2 {
        margin: 0;
        letter-spacing: 0.2px;
        font-size: 1.4rem;
    }
    .hero p {
        margin: 0.4rem 0 0 0;
        color: #c7dff5;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.25rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h2>Research Discovery and Influence Analysis Tool</h2>
      <p>Qdrant for semantic retrieval, Neo4j for graph reasoning, Postgres for structured analytics.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def _table(rows: list[dict[str, Any]], height: int = 360) -> None:
    if not rows:
        st.warning("No results returned.")
        return
    st.dataframe(rows, use_container_width=True, height=height)


def _call_api(path: str, params: dict | None = None) -> dict[str, Any] | None:
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.get(f"{API_BASE}{path}", params=params)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        st.error(f"API request failed for {path}: {e}")
        return None


# Topic scope: optional set of papers from semantic search; when set, filter/explore and some other tabs restrict to these papers.
if "topic_papers" not in st.session_state:
    st.session_state.topic_papers = None
if "topic_paper_ids" not in st.session_state:
    st.session_state.topic_paper_ids = None


def _scope_params() -> dict:
    """Query params to restrict results to the current topic scope (when set)."""
    ids = st.session_state.get("topic_paper_ids")
    if not ids:
        return {}
    # Cap at 500 to avoid huge URLs
    return {"paper_ids": ids[:500]}


with st.expander("Topic scope (optional)", expanded=True):
    st.caption("Set a research topic to restrict Filter & explore and related tabs to semantically similar papers.")
    topic_q = st.text_input(
        "Research topic / problem",
        value="",
        placeholder="e.g. graph neural networks for citation prediction",
        key="topic_query",
    )
    topic_k = st.slider("Number of papers to include in scope", 20, 200, 50, key="topic_k")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        if st.button("Set scope", key="set_scope"):
            if not topic_q.strip():
                st.warning("Enter a research topic.")
            else:
                data = _call_api("/semantic_search", {"q": topic_q.strip(), "k": topic_k})
                if data:
                    rows = data.get("results", [])
                    ids = [r["paper_id"] for r in rows if r.get("paper_id")]
                    st.session_state.topic_papers = rows
                    st.session_state.topic_paper_ids = ids
                    st.success(f"Scope set to {len(ids)} papers. Other tabs will filter to this set when you run queries.")
    with col_t2:
        if st.button("Clear scope", key="clear_scope"):
            st.session_state.topic_papers = None
            st.session_state.topic_paper_ids = None
            st.rerun()
    if st.session_state.topic_papers:
        st.markdown(f"**Scope: {len(st.session_state.topic_paper_ids)} papers** (from semantic search)")
        _table(st.session_state.topic_papers, height=220)


with st.expander("Current app logic and what each tab does", expanded=False):
    st.markdown(
        """
This app is a query router UI over three stores:

- `Qdrant`: semantic nearest-neighbor search on embedded title+abstract.
- `Neo4j`: relationship traversals and graph algorithms (GDS).
- `Postgres`: citation and metadata aggregation/filtering.

Tab guide:

- `Filter & explore`: Postgres-only structured queries (filtering, aggregation, joins, integrity, time, ranking).
- `Dashboard`: overview stats from all three databases.
- `Graph exploration`: co-authorship and indirect citation traversals.
- `Cross-store analytics`: combined vector + SQL + graph insights.
- `Graph analytics (GDS)`: Louvain communities and bridge-author centrality.
        """
    )


tab_dashboard, tab_filter, tab2, tab3, tab4 = st.tabs(
    [
        "Dashboard",
        "Filter & explore",
        "Graph exploration",
        "Cross-store analytics",
        "Graph analytics (GDS)",
    ]
)


def _show_justification(data: dict | None) -> None:
    if data and data.get("store_justification"):
        st.caption(data["store_justification"])


def _show_sql(data: dict | None) -> None:
    """Show SQL in a collapsed expander when the API returns it."""
    if data and data.get("sql"):
        with st.expander("Show SQL", expanded=False):
            st.code(data["sql"], language="sql")


with tab_filter:
    st.markdown("**Postgres-only** structured queries. Combine filters in **Basic filters** or run preset **Advanced analytics**.")
    tab_basic, tab_adv = st.tabs(["Basic filters", "Advanced analytics"])

    with tab_basic:
        st.markdown("Build a query over papers: year range, venue, author, citation range, sort. One Postgres query—no graph or vector.")
        col1, col2 = st.columns(2)
        with col1:
            year_min = st.number_input("Year min", value=2005, min_value=1900, max_value=2100, key="qb_ymin")
            year_max = st.number_input("Year max", value=2015, min_value=1900, max_value=2100, key="qb_ymax")
            min_cit = st.number_input("Min citations", value=0, min_value=0, key="qb_minc")
            max_cit = st.number_input("Max citations (0 = no limit)", value=0, min_value=0, key="qb_maxc")
        with col2:
            venue = st.text_input("Venue (partial match)", value="", placeholder="e.g. Neurocomputing", key="qb_venue")
            author = st.text_input("Author (optional)", value="", placeholder="e.g. Smith", key="qb_author")
            sort_by = st.selectbox(
                "Sort by",
                ["n_citation_desc", "year_desc", "year_asc", "title_asc"],
                format_func=lambda x: {"n_citation_desc": "Most cited first", "year_desc": "Newest first", "year_asc": "Oldest first", "title_asc": "Title A→Z"}[x],
                key="qb_sort",
            )
            limit = st.slider("Max results", 10, 200, 50, key="qb_limit")
        if st.button("Run query", key="qb_run"):
            params = {"year_min": year_min, "year_max": year_max, "min_citations": min_cit, "sort_by": sort_by, "limit": limit}
            if venue.strip():
                params["venue"] = venue.strip()
            if author.strip():
                params["author"] = author.strip()
            if max_cit > 0:
                params["max_citations"] = max_cit
            params = {**params, **_scope_params()}
            data = _call_api("/filter/papers_query", params)
            if data:
                _table(data.get("results", []))
                _show_justification(data)
                _show_sql(data)

    with tab_adv:
        st.markdown("Preset analytics and data-quality checks. Each card runs one or more Postgres queries.")
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("Publication trends & aggregates")
            if st.button("Run trends", key="adv_trends"):
                d1 = _call_api("/filter/papers_per_year", _scope_params())
                d2 = _call_api("/filter/avg_citations_per_year", _scope_params())
                if d1:
                    _table(d1.get("results", []))
                    _show_sql(d1)
                if d2:
                    _table(d2.get("results", []))
                    _show_sql(d2)

            st.subheader("Venue analytics")
            top_n_v = st.slider("Top N venues", 5, 30, 10, key="adv_topv")
            if st.button("Run venue analytics", key="adv_venues"):
                dv = _call_api("/filter/venues_by_paper_count", {"limit": top_n_v, **_scope_params()})
                if dv:
                    _table(dv.get("results", []))
                    _show_justification(dv)
                davg = _call_api("/filter/avg_citations_per_venue", {"limit": top_n_v, **_scope_params()})
                if davg:
                    _table(davg.get("results", []))
                    _show_justification(davg)

        with c2:
            st.subheader("Author analytics")
            if st.button("Run author analytics", key="adv_authors"):
                da = _call_api("/filter/authors_by_paper_count", {"limit": 30, **_scope_params()})
                if da:
                    _table(da.get("results", []))
                    _show_sql(da)
                dtc = _call_api("/filter/total_citations_per_author", {"limit": 30, **_scope_params()})
                if dtc:
                    _table(dtc.get("results", []))
                    _show_sql(dtc)

        st.subheader("Data quality & integrity")
        if st.button("Run data quality checks", key="adv_dq"):
            dup = _call_api("/filter/duplicate_paper_ids")
            miss = _call_api("/filter/papers_missing_venue", {"limit": 50})
            if dup:
                st.caption("Duplicate paper IDs (expect empty)")
                _table(dup.get("results", []))
            if miss:
                st.caption("Papers missing venue")
                _table(miss.get("results", []))
            orphan = _call_api("/filter/paper_authors_orphaned")
            fut = _call_api("/filter/papers_future_year", {"limit": 20})
            if orphan:
                st.caption("Orphaned paper_authors (expect empty)")
                _table(orphan.get("results", []))
            if fut:
                st.caption("Papers with future year")
                _table(fut.get("results", []))


with tab_dashboard:
    st.markdown("### At-a-glance statistics")
    st.caption("Overview of Postgres, Neo4j, and Qdrant." + (" **Scoped to topic.**" if st.session_state.get("topic_paper_ids") else ""))
    data = _call_api("/stats", _scope_params())
    if not data:
        st.info("Could not reach the API. Start it with: `uvicorn apps.api.main:app --reload --port 8000` (or set API_BASE if using another port).")
    else:
        try:
            pg = data.get("postgres", {})
            n4 = data.get("neo4j", {})
            qd = data.get("qdrant", {})

            # Single row of 7 equal metric cards, aligned
            m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
            m1.metric("Papers", f"{pg.get('papers', 0):,}")
            m2.metric("Authors", f"{pg.get('authors', 0):,}")
            m3.metric("Venues", f"{pg.get('venues', 0):,}")
            m4.metric("Total Citations", f"{pg.get('total_citations', 0):,}")
            m5.metric("Neo4j Nodes", f"{n4.get('nodes', 0):,}")
            m6.metric("Neo4j Relationships", f"{n4.get('relationships', 0):,}")
            m7.metric("Qdrant Vectors", f"{qd.get('vectors', 0):,}")

            import pandas as pd

            try:
                import altair as alt
            except ImportError:
                alt = None

            col_left, col_right = st.columns(2)
            with col_left:
                st.subheader("Top 10 Venues")
                venues = pg.get("top_venues", [])
                if venues:
                    df_v = pd.DataFrame(venues)
                    if alt is not None:
                        chart_v = (
                            alt.Chart(df_v)
                            .mark_bar(cornerRadius=4)
                            .encode(
                                x=alt.X("venue:N", sort="-y", title="Venue", axis=alt.Axis(labelLimit=120, labelFontSize=12, titleFontSize=13)),
                                y=alt.Y("count:Q", title="Papers", axis=alt.Axis(labelFontSize=12, titleFontSize=13)),
                                color=alt.Color("venue:N", scale=alt.Scale(scheme="tableau20"), legend=None),
                            )
                            .properties(height=420, width=500)
                            .configure_axis(labelFontSize=12, titleFontSize=13)
                        )
                        st.altair_chart(chart_v, use_container_width=True)
                    else:
                        st.bar_chart(df_v.set_index("venue")["count"])
                else:
                    st.caption("No venue data.")
            with col_right:
                st.subheader("Papers by Year")
                pby = pg.get("papers_by_year", [])
                if pby:
                    df_y = pd.DataFrame(pby)
                    if alt is not None:
                        chart_y = (
                            alt.Chart(df_y)
                            .mark_bar(cornerRadius=4)
                            .encode(
                                x=alt.X("year:O", title="Year", axis=alt.Axis(labelFontSize=12, titleFontSize=13)),
                                y=alt.Y("count:Q", title="Papers", axis=alt.Axis(labelFontSize=12, titleFontSize=13)),
                                color=alt.Color("year:O", scale=alt.Scale(scheme="plasma"), legend=None),
                            )
                            .properties(height=420, width=500)
                            .configure_axis(labelFontSize=12, titleFontSize=13)
                        )
                        st.altair_chart(chart_y, use_container_width=True)
                    else:
                        st.bar_chart(df_y.set_index("year")["count"])
                else:
                    st.caption("No year data.")
        except Exception as e:
            st.error(f"Dashboard error: {e}")

with tab2:
    st.caption("Explore graph paths and collaborations in Neo4j.")
    st.subheader("Top collaborators (co-authorship)")
    if st.button("Compute top collaborator pairs"):
        data = _call_api("/top_collaborators", {"limit": 20, **_scope_params()})
        if data:
            _table(data.get("results", []))
            st.info(data["store_justification"])

    st.divider()
    st.subheader("Indirect citers of a paper (citation paths)")
    topic_papers = st.session_state.get("topic_papers") or []
    if topic_papers:
        pick_idx = st.selectbox(
            "Pick a paper from topic scope",
            range(len(topic_papers)),
            format_func=lambda i: f"{(topic_papers[i].get('title') or topic_papers[i].get('paper_id', ''))[:55]}...",
            key="graph_pick_scope",
        )
        pid = topic_papers[pick_idx]["paper_id"]
        st.caption(f"Paper ID: `{pid}`")
    else:
        pid = st.text_input("Paper UUID", value="56cd3fdb-73ff-431e-8945-d673f9469f33")
    hops = st.slider("Max hops", 1, 5, 3)
    if st.button("Find indirect citers"):
        if not pid.strip():
            st.warning("Enter a paper UUID.")
        else:
            data = _call_api(
                "/indirect_citers",
                {"paper_id": pid.strip(), "max_hops": hops, "limit": 20},
            )
            if data:
                _table(data.get("results", []))
                st.info(data["store_justification"])

with tab3:
    st.caption("Blend vector similarity with relational and graph analytics.")
    st.subheader("Citations vs similarity")
    q2 = st.text_input("Topic query", value="deep learning")
    if st.button("Analyze citations vs similarity"):
        data = _call_api("/citations_vs_similarity", {"q": q2, "k": 20, **_scope_params()})
        if data:
            _table(data.get("results", []))
            st.info(data["store_justification"])

    st.divider()
    st.subheader("Emerging trends (recent papers similar to query)")
    since = st.number_input("Since year", value=2015, min_value=1950, max_value=2100)
    if st.button("Find emerging papers"):
        data = _call_api(
            "/emerging_trends", {"q": q2, "since_year": int(since), "k": 20}
        )
        if data:
            _table(data.get("results", []))
            st.info(data["store_justification"])

    st.divider()
    st.subheader("Cross-field relevance (by venue)")
    source_venue = st.text_input(
        "Source venue (label only, MVP)", value="Neurocomputing"
    )
    target_venue = st.text_input(
        "Target venue", value="international conference on computer vision"
    )
    if st.button("Find cross-field relevant papers"):
        data = _call_api(
            "/cross_field_relevance",
            {
                "source_venue": source_venue,
                "target_venue": target_venue,
                "q": q2,
                "k": 20,
            },
        )
        if data:
            _table(data.get("results", []))
            st.info(data["store_justification"])

    st.divider()
    st.subheader("Central but under-cited authors")
    if st.button("Find central-but-undercited"):
        data = _call_api("/central_but_undercited", {"limit": 20})
        if data:
            _table(data.get("results", []))
            st.info(data["store_justification"])

    st.divider()
    st.subheader("Topics connected via co-authorship")
    if st.button("Compute topic connectivity"):
        data = _call_api("/topics_connected_via_coauthorship", {"q": q2, "k": 30, **_scope_params()})
        if data:
            c1, c2, c3 = st.columns(3)
            c1.metric("Paper sample", data.get("paper_sample_size", 0))
            c2.metric("Authors in sample", data.get("author_count", 0))
            c3.metric("Co-authorship links", data.get("coauth_links", 0))
            st.info(data["store_justification"])
            st.caption(data.get("note", ""))

with tab4:
    st.caption("Run graph data science routines from Neo4j GDS.")
    st.subheader("Author clusters dominating a venue (Louvain)")
    venue = st.text_input("Venue (field proxy)", value="Neurocomputing")
    if st.button("Compute clusters"):
        data = _call_api("/author_clusters_by_venue", {"venue": venue, "top_k": 5})
        if data:
            _table(data.get("top_communities", []), height=260)
            st.info(data["store_justification"])
            st.caption(data.get("note", ""))

    st.divider()
    st.subheader("Bridge authors (betweenness centrality)")
    if st.button("Compute bridge authors"):
        data = _call_api("/bridge_authors", {"limit": 20})
        if data:
            _table(data.get("results", []))
        st.info(data["store_justification"])
