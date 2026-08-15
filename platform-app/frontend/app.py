"""
CKP Streamlit Frontend — Interactive UI for the Cognitive Knowledge Platform.

Provides:
- Chat interface for querying the knowledge agent
- File upload for data ingestion
- Schema management panel
- System diagnostics dashboard
"""

from __future__ import annotations

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE = "http://localhost:8000/api/v2"
APP_TITLE = "Cognitive Knowledge Platform"


# ---------------------------------------------------------------------------
# API Client Helpers
# ---------------------------------------------------------------------------
def api_query(query: str, session_id: str | None = None, schema: str = "healthtech") -> dict:
    """Send a query to the CKP agent API."""
    try:
        resp = requests.post(
            f"{API_BASE}/query",
            json={
                "query": query,
                "session_id": session_id,
                "schema_name": schema,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e), "response": "Failed to connect to the backend."}


def api_ingest(file_bytes: bytes, filename: str, schema: str = "healthtech") -> dict:
    """Upload a file for ingestion."""
    try:
        resp = requests.post(
            f"{API_BASE}/ingest",
            files={"file": (filename, file_bytes)},
            params={"schema_name": schema},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def api_health() -> dict:
    """Check backend health."""
    try:
        resp = requests.get("http://localhost:8000/health", timeout=5)
        return resp.json()
    except requests.RequestException:
        return {"status": "unreachable"}


def api_schemas() -> list[str]:
    """List available schemas."""
    try:
        resp = requests.get(f"{API_BASE}/schemas", timeout=5)
        return resp.json().get("schemas", [])
    except requests.RequestException:
        return ["healthtech", "fintech", "edtech", "enterprise_ops"]


# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🧠 CKP")
    st.caption("Cognitive Knowledge Platform v2")

    st.divider()

    # Schema selector
    schemas = api_schemas()
    active_schema = st.selectbox("Active Schema", schemas, index=0)

    st.divider()

    # Navigation
    page = st.radio(
        "Navigate",
        ["💬 Chat", "📤 Ingest", "🔧 Diagnostics"],
        index=0,
    )

    st.divider()

    # Health indicator
    health = api_health()
    if health.get("status") == "healthy":
        st.success("Backend: Connected")
    else:
        st.error("Backend: Unreachable")

    st.caption(f"Schema: {active_schema}")


# ---------------------------------------------------------------------------
# Chat Page
# ---------------------------------------------------------------------------
if page == "💬 Chat":
    st.header("💬 Knowledge Agent")
    st.caption("Ask questions about your ingested data using natural language.")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = None

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "metadata" in message:
                with st.expander("Details"):
                    st.json(message["metadata"])

    # Chat input
    if prompt := st.chat_input("Ask a question..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get agent response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = api_query(
                    prompt,
                    session_id=st.session_state.session_id,
                    schema=active_schema,
                )

            response = result.get("response", result.get("error", "No response"))
            st.markdown(response)

            # Show metadata
            metadata = {
                k: v for k, v in result.items()
                if k not in ("response", "error")
            }
            if metadata:
                with st.expander("Response Details"):
                    st.json(metadata)

        # Store in history
        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "metadata": metadata,
        })
        st.session_state.session_id = result.get("session_id")

    # Clear chat button
    if st.session_state.messages:
        if st.button("Clear Chat"):
            st.session_state.messages = []
            st.session_state.session_id = None
            st.rerun()


# ---------------------------------------------------------------------------
# Ingest Page
# ---------------------------------------------------------------------------
elif page == "📤 Ingest":
    st.header("📤 Data Ingestion")
    st.caption("Upload files to build your knowledge graph.")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "Upload a file",
            type=["pdf", "txt", "md", "csv", "json", "docx"],
            help="Supported: PDF, TXT, Markdown, CSV, JSON, DOCX",
        )

        if uploaded_file is not None:
            st.info(f"📄 {uploaded_file.name} ({uploaded_file.size:,} bytes)")

            if st.button("Ingest File", type="primary"):
                with st.spinner(f"Ingesting {uploaded_file.name}..."):
                    result = api_ingest(
                        uploaded_file.getvalue(),
                        uploaded_file.name,
                        schema=active_schema,
                    )

                if "error" in result:
                    st.error(f"Ingestion failed: {result['error']}")
                else:
                    st.success("Ingestion complete!")
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Chunks", result.get("chunks_created", 0))
                    col_b.metric("Entities", result.get("entities_extracted", 0))
                    col_c.metric("Relationships", result.get("relationships_extracted", 0))

    with col2:
        st.subheader("Ingestion Settings")
        st.selectbox("Schema", schemas, index=schemas.index(active_schema))
        st.slider("Chunk Size (tokens)", 128, 1024, 512, step=64)
        st.slider("Overlap (tokens)", 0, 256, 64, step=16)


# ---------------------------------------------------------------------------
# Diagnostics Page
# ---------------------------------------------------------------------------
elif page == "🔧 Diagnostics":
    st.header("🔧 System Diagnostics")
    st.caption("Monitor platform health and configuration.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Platform")
        health = api_health()
        st.json(health)

    with col2:
        st.subheader("Active Schema")
        st.code(active_schema, language="text")
        st.caption("Schemas define the knowledge graph structure for each domain.")

    with col3:
        st.subheader("Available Schemas")
        for schema in schemas:
            st.code(schema, language="text")
