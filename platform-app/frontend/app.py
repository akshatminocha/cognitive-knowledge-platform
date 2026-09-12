"""
CKP Streamlit Frontend — Premium UI for the Cognitive Knowledge Platform.

Provides:
- Chat interface for querying the knowledge agent
- File upload for data ingestion
- Skills & Prompts library browser
- System diagnostics dashboard
"""

from __future__ import annotations

import json
import requests
import streamlit as st
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE = "http://localhost:8000/api/v2"
APP_TITLE = "Cognitive Knowledge Platform"


# ---------------------------------------------------------------------------
# API Client Helpers
# ---------------------------------------------------------------------------
def api_query(query: str, session_id: str | None = None, schema: str = "healthtech", active_skill: str = "auto") -> dict:
    """Send a query to the CKP agent API."""
    try:
        resp = requests.post(
            f"{API_BASE}/query",
            json={
                "query": query,
                "session_id": session_id,
                "schema_name": schema,
                "active_skill": active_skill,
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


def api_list_skills() -> list[dict]:
    """List all available skills."""
    try:
        resp = requests.get(f"{API_BASE}/skills", timeout=5)
        return resp.json().get("skills", [])
    except requests.RequestException:
        return []


def api_list_prompts() -> list[dict]:
    """List all available prompt templates."""
    try:
        resp = requests.get(f"{API_BASE}/prompts", timeout=5)
        return resp.json().get("prompts", [])
    except requests.RequestException:
        return []


def api_create_skill(description: str, domain: str = "general") -> dict:
    """Create a new skill via the builder agent."""
    try:
        resp = requests.post(
            f"{API_BASE}/skills/create",
            json={"description": description, "domain": domain},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def api_create_prompt(description: str) -> dict:
    """Create a new prompt template via the builder agent."""
    try:
        resp = requests.post(
            f"{API_BASE}/prompts/create",
            json={"description": description},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def api_diagnostics() -> dict:
    """Fetch full diagnostics."""
    try:
        resp = requests.get(f"{API_BASE}/diagnostics", timeout=5)
        return resp.json()
    except requests.RequestException:
        return {}


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
# Premium CSS — Glassmorphism, Animations, Custom Components
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ===== BASE RESET ===== */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(122, 82, 244, 0.3); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(122, 82, 244, 0.6); }

/* ===== SIDEBAR ===== */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(10, 14, 26, 0.95) 0%, rgba(17, 24, 39, 0.95) 100%) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border-right: 1px solid rgba(122, 82, 244, 0.15) !important;
}

/* Collapsed sidebar toggle — always visible */
[data-testid="collapsedControl"] {
    display: block !important;
    z-index: 999999 !important;
    background: rgba(17, 24, 39, 0.9) !important;
    border: 1px solid rgba(122, 82, 244, 0.3) !important;
    border-radius: 8px !important;
    transition: all 0.3s ease !important;
}
[data-testid="collapsedControl"]:hover {
    background: rgba(122, 82, 244, 0.3) !important;
    border-color: rgba(122, 82, 244, 0.6) !important;
    transform: scale(1.05);
}

/* Navigation radio → pill buttons */
[data-testid="stSidebar"] [data-testid="stRadio"] > div { gap: 4px; }
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
    background: transparent;
    padding: 10px 16px;
    border-radius: 10px;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    border: 1px solid transparent;
    margin: 2px 0;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover {
    background: rgba(122, 82, 244, 0.12);
    border-color: rgba(122, 82, 244, 0.25);
    transform: translateX(4px);
}
/* Hide radio circle */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
    display: none;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] p {
    font-size: 0.95rem;
    font-weight: 500;
    letter-spacing: 0.01em;
}

/* ===== GLASSMORPHISM CARDS ===== */
.glass-card {
    background: rgba(17, 24, 39, 0.6);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 16px;
    padding: 24px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: fadeInUp 0.4s ease-out;
}
.glass-card:hover {
    border-color: rgba(122, 82, 244, 0.3);
    box-shadow: 0 8px 32px rgba(122, 82, 244, 0.1), inset 0 1px 0 rgba(255,255,255,0.05);
    transform: translateY(-2px);
}

/* ===== ANIMATIONS ===== */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
@keyframes gradientShift {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes slideInRight {
    from { opacity: 0; transform: translateX(20px); }
    to { opacity: 1; transform: translateX(0); }
}

/* ===== GRADIENT TEXT ===== */
.gradient-text {
    background: linear-gradient(135deg, #7A52F4 0%, #00D2FF 50%, #7A52F4 100%);
    background-size: 200% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: gradientShift 4s ease infinite;
    font-weight: 800;
    letter-spacing: -0.02em;
}

.subtitle-text {
    color: #94A3B8;
    font-size: 1.05rem;
    font-weight: 400;
    line-height: 1.6;
}

/* ===== BUTTONS ===== */
.stButton > button {
    border-radius: 10px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    font-weight: 500 !important;
    letter-spacing: 0.01em !important;
}
.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(122, 82, 244, 0.35) !important;
    border-color: rgba(122, 82, 244, 0.5) !important;
}

/* Primary button gradient */
.stButton > button[kind="primary"],
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #7A52F4, #6236E0) !important;
    color: white !important;
    border: none !important;
}
.stFormSubmitButton > button:hover,
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #8B63FF, #7A52F4) !important;
    box-shadow: 0 6px 24px rgba(122, 82, 244, 0.4) !important;
}

/* ===== CHAT ===== */
.stChatInputContainer {
    background: rgba(17, 24, 39, 0.7) !important;
    backdrop-filter: blur(12px) !important;
    border-radius: 14px !important;
    border: 1px solid rgba(122, 82, 244, 0.2) !important;
    transition: all 0.3s ease !important;
}
.stChatInputContainer:focus-within {
    border-color: rgba(122, 82, 244, 0.5) !important;
    box-shadow: 0 0 0 2px rgba(122, 82, 244, 0.15) !important;
}

[data-testid="stChatMessage"] {
    animation: fadeInUp 0.3s ease-out;
    border-radius: 12px !important;
    padding: 12px 16px !important;
}

/* ===== EXPANDERS ===== */
[data-testid="stExpander"] {
    background: rgba(17, 24, 39, 0.5) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    transition: all 0.3s ease !important;
}
[data-testid="stExpander"]:hover {
    border-color: rgba(122, 82, 244, 0.3) !important;
    background: rgba(17, 24, 39, 0.7) !important;
}

/* ===== METRICS ===== */
[data-testid="stMetricValue"] {
    font-weight: 700 !important;
    background: linear-gradient(135deg, #7A52F4, #00D2FF);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 1.8rem !important;
}
[data-testid="stMetricLabel"] {
    color: #94A3B8 !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    font-size: 0.75rem !important;
}

/* ===== INPUTS ===== */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] {
    border-radius: 10px !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    transition: all 0.3s ease !important;
}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within {
    border-color: rgba(122, 82, 244, 0.5) !important;
    box-shadow: 0 0 0 2px rgba(122, 82, 244, 0.15) !important;
}

/* ===== TABS ===== */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    padding-bottom: 0;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 8px 20px;
    font-weight: 500;
    transition: all 0.2s ease;
}
.stTabs [data-baseweb="tab"]:hover {
    background: rgba(122, 82, 244, 0.1);
}

/* ===== FILE UPLOADER ===== */
[data-testid="stFileUploader"] {
    border-radius: 12px !important;
}
[data-testid="stFileUploader"] > div {
    border: 2px dashed rgba(122, 82, 244, 0.3) !important;
    border-radius: 12px !important;
    transition: all 0.3s ease !important;
    background: rgba(122, 82, 244, 0.03) !important;
}
[data-testid="stFileUploader"] > div:hover {
    border-color: rgba(122, 82, 244, 0.6) !important;
    background: rgba(122, 82, 244, 0.06) !important;
}

/* ===== STATUS INDICATOR ===== */
.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 8px;
    animation: pulse 2s ease-in-out infinite;
}
.status-dot.online { background: #22C55E; box-shadow: 0 0 8px rgba(34, 197, 94, 0.4); }
.status-dot.offline { background: #EF4444; box-shadow: 0 0 8px rgba(239, 68, 68, 0.4); }

/* ===== WELCOME CARD ===== */
.welcome-card {
    background: linear-gradient(135deg, rgba(122, 82, 244, 0.08) 0%, rgba(0, 210, 255, 0.05) 100%);
    border: 1px solid rgba(122, 82, 244, 0.15);
    border-radius: 16px;
    padding: 32px;
    text-align: center;
    animation: fadeIn 0.6s ease-out;
}

/* ===== SKILL CARD ===== */
.skill-card {
    background: rgba(17, 24, 39, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    padding: 20px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: fadeInUp 0.4s ease-out;
}
.skill-card:hover {
    border-color: rgba(122, 82, 244, 0.3);
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}
.skill-tag {
    display: inline-block;
    background: rgba(122, 82, 244, 0.15);
    color: #A78BFA;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
    margin-right: 6px;
    margin-bottom: 6px;
}

/* ===== DIVIDER ===== */
hr {
    border: none;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    margin: 16px 0;
}

/* ===== SELECT BOX ===== */
[data-testid="stSelectbox"] label {
    font-weight: 500 !important;
    color: #94A3B8 !important;
    font-size: 0.85rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    # Logo & title
    st.markdown(
        """
        <div style="text-align: center; padding: 8px 0 4px;">
            <div style="font-size: 2.4rem; margin-bottom: 2px;">🧠</div>
            <h1 class="gradient-text" style="font-size: 1.6rem; margin: 0; line-height: 1.2;">CKP</h1>
            <p style="color: #64748B; font-size: 0.78rem; margin-top: 4px; letter-spacing: 0.08em; text-transform: uppercase;">
                Cognitive Knowledge Platform
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

    # Schema selector
    schemas = api_schemas()
    active_schema = st.selectbox("Schema", schemas, index=0, label_visibility="collapsed")
    st.caption(f"Active: **{active_schema}**")

    st.divider()

    # Navigation
    page = st.radio(
        "Navigate",
        ["💬  Chat", "📤  Ingest", "🧩  Library", "📊  Diagnostics"],
        index=0,
        label_visibility="collapsed",
    )

    st.divider()

    # Health indicator
    health = api_health()
    is_healthy = health.get("status") == "healthy"
    dot_class = "online" if is_healthy else "offline"
    status_text = "Connected" if is_healthy else "Unreachable"
    st.markdown(
        f"<div style='display:flex; align-items:center; padding: 4px 0;'>"
        f"<span class='status-dot {dot_class}'></span>"
        f"<span style='color: {'#22C55E' if is_healthy else '#EF4444'}; font-weight: 500; font-size: 0.85rem;'>"
        f"Backend: {status_text}</span></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='margin-top: 12px; padding: 8px 12px; background: rgba(122,82,244,0.06); "
        "border-radius: 8px; border: 1px solid rgba(122,82,244,0.1);'>"
        f"<p style='color: #64748B; font-size: 0.72rem; margin: 0; text-transform: uppercase; letter-spacing: 0.06em;'>Version</p>"
        f"<p style='color: #94A3B8; font-size: 0.85rem; margin: 2px 0 0; font-weight: 600;'>{health.get('version', '2.0.0')}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Chat Page
# ---------------------------------------------------------------------------
if page == "💬  Chat":
    st.markdown("<h2 class='gradient-text' style='font-size: 2rem; margin-bottom: 4px;'>Knowledge Agent</h2>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle-text'>Ask questions about your ingested data using natural language.</p>", unsafe_allow_html=True)

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = None

    # Skill selector bar
    skills_data = api_list_skills()
    skill_options = ["auto"] + [s["name"] for s in skills_data]

    col_info, col_skill, col_clear = st.columns([4, 2, 1])
    with col_skill:
        active_skill = st.selectbox(
            "Skill",
            options=skill_options,
            format_func=lambda x: "🤖 Auto-Select" if x == "auto" else f"⚡ {x}",
            label_visibility="collapsed",
        )
    with col_clear:
        if st.session_state.messages:
            if st.button("🗑️", help="Clear conversation"):
                st.session_state.messages = []
                st.session_state.session_id = None
                st.rerun()
    with col_info:
        mode_label = "Auto-routing" if active_skill == "auto" else active_skill
        st.markdown(
            f"<div style='display: flex; align-items: center; gap: 8px; padding: 8px 0;'>"
            f"<span style='background: rgba(122,82,244,0.12); color: #A78BFA; padding: 4px 12px; "
            f"border-radius: 20px; font-size: 0.78rem; font-weight: 500;'>Mode: {mode_label}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 4px'></div>", unsafe_allow_html=True)

    # Welcome screen when no messages
    if not st.session_state.messages:
        st.markdown(
            """
            <div class="welcome-card">
                <div style="font-size: 3rem; margin-bottom: 12px;">💬</div>
                <h3 style="color: #F1F5F9; font-weight: 700; margin-bottom: 8px;">Start a Conversation</h3>
                <p style="color: #94A3B8; font-size: 0.95rem; max-width: 500px; margin: 0 auto 20px;">
                    Ask questions about your knowledge base, generate reports, or explore your data graph.
                </p>
                <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                    <span class="skill-tag">💊 Clinical data</span>
                    <span class="skill-tag">📊 Reports</span>
                    <span class="skill-tag">🔍 Knowledge Q&A</span>
                    <span class="skill-tag">🕸️ Graph queries</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar="👤" if message["role"] == "user" else "🧠"):
            st.markdown(message["content"])
            if "metadata" in message and message["metadata"]:
                with st.expander("📋 Response Details", expanded=False):
                    meta = message["metadata"]
                    if meta:
                        mcol1, mcol2, mcol3 = st.columns(3)
                        mcol1.metric("Steps", meta.get("total_steps", "-"))
                        mcol2.metric("Latency", f"{meta.get('duration_ms', 0):.0f}ms")
                        mcol3.metric("Model", meta.get("model_used", "-"))

    # Chat input
    if prompt := st.chat_input("Ask a question about your knowledge base..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="🧠"):
            with st.spinner(""):
                # Show a skeleton-like placeholder
                placeholder = st.empty()
                placeholder.markdown(
                    "<div style='color: #64748B; animation: pulse 1.5s ease-in-out infinite;'>Thinking...</div>",
                    unsafe_allow_html=True,
                )
                result = api_query(
                    prompt,
                    session_id=st.session_state.session_id,
                    schema=active_schema,
                    active_skill=active_skill,
                )
                placeholder.empty()

            response = result.get("response", result.get("error", "No response"))
            st.markdown(response)

            metadata = {k: v for k, v in result.items() if k not in ("response", "error")}
            if metadata:
                with st.expander("📋 Response Details", expanded=False):
                    mcol1, mcol2, mcol3 = st.columns(3)
                    mcol1.metric("Steps", metadata.get("total_steps", "-"))
                    mcol2.metric("Latency", f"{metadata.get('duration_ms', 0):.0f}ms")
                    mcol3.metric("Model", metadata.get("model_used", "-"))

        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "metadata": metadata,
        })
        st.session_state.session_id = result.get("session_id")

    # Export button
    if st.session_state.messages:
        st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)
        col_export, _ = st.columns([1, 5])
        with col_export:
            export_data = json.dumps(st.session_state.messages, indent=2, default=str)
            st.download_button(
                "📥 Export Chat",
                data=export_data,
                file_name=f"ckp_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )


# ---------------------------------------------------------------------------
# Ingest Page
# ---------------------------------------------------------------------------
elif page == "📤  Ingest":
    st.markdown("<h2 class='gradient-text' style='font-size: 2rem; margin-bottom: 4px;'>Data Ingestion</h2>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle-text'>Upload files to build and expand your knowledge graph.</p>", unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown(
            """
            <div class="glass-card" style="text-align: center; padding: 40px 24px;">
                <div style="font-size: 2.5rem; margin-bottom: 12px;">📄</div>
                <p style="color: #94A3B8; font-size: 1rem; margin-bottom: 4px;">
                    Drag & drop or browse to upload
                </p>
                <p style="color: #64748B; font-size: 0.8rem;">
                    PDF · TXT · Markdown · CSV · JSON · DOCX
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        uploaded_file = st.file_uploader(
            "Upload a file",
            type=["pdf", "txt", "md", "csv", "json", "docx"],
            help="Supported: PDF, TXT, Markdown, CSV, JSON, DOCX",
            label_visibility="collapsed",
        )

        if uploaded_file is not None:
            st.markdown(
                f"<div class='glass-card' style='padding: 16px 20px; display: flex; align-items: center; gap: 12px;'>"
                f"<span style='font-size: 1.5rem;'>📎</span>"
                f"<div>"
                f"<p style='color: #F1F5F9; font-weight: 600; margin: 0;'>{uploaded_file.name}</p>"
                f"<p style='color: #64748B; font-size: 0.8rem; margin: 2px 0 0;'>{uploaded_file.size:,} bytes</p>"
                f"</div></div>",
                unsafe_allow_html=True,
            )

            if st.button("⚡ Ingest File", type="primary", use_container_width=True):
                with st.spinner(f"Processing {uploaded_file.name}..."):
                    result = api_ingest(
                        uploaded_file.getvalue(),
                        uploaded_file.name,
                        schema=active_schema,
                    )

                if "error" in result:
                    st.error(f"Ingestion failed: {result['error']}")
                else:
                    st.success("✅ Ingestion complete!")
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Chunks", result.get("chunks_created", 0))
                    col_b.metric("Entities", result.get("entities_extracted", 0))
                    col_c.metric("Relations", result.get("relationships_extracted", 0))

    with col2:
        st.markdown(
            "<div class='glass-card'>"
            "<h4 style='color: #F1F5F9; font-size: 0.9rem; margin: 0 0 12px; text-transform: uppercase; "
            "letter-spacing: 0.05em;'>⚙️ Settings</h4>",
            unsafe_allow_html=True,
        )
        st.selectbox("Schema", schemas, index=schemas.index(active_schema) if active_schema in schemas else 0)
        st.slider("Chunk Size", 128, 1024, 512, step=64, help="Tokens per chunk")
        st.slider("Overlap", 0, 256, 64, step=16, help="Token overlap between chunks")
        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Skills & Prompts Library Page
# ---------------------------------------------------------------------------
elif page == "🧩  Library":
    st.markdown("<h2 class='gradient-text' style='font-size: 2rem; margin-bottom: 4px;'>Skills & Prompts Library</h2>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle-text'>Browse, inspect, and create reusable agent skills and prompt templates.</p>", unsafe_allow_html=True)

    skill_tab, prompt_tab = st.tabs(["🛠️ Skills", "📝 Prompts"])

    # ----- Skills Tab -----
    with skill_tab:
        from pathlib import Path
        import yaml

        skills_dir = Path(__file__).resolve().parents[2] / "packages" / "agent-harness" / "agent_harness" / "skills" / "library"
        skill_files = sorted(skills_dir.glob("*.yaml")) if skills_dir.exists() else []

        if skill_files:
            # Display skills as cards
            cols = st.columns(3)
            for i, skill_file in enumerate(skill_files):
                with open(skill_file) as f:
                    skill_data = yaml.safe_load(f)

                with cols[i % 3]:
                    domain = skill_data.get("domain", "general")
                    tools = skill_data.get("tools", [])
                    examples = skill_data.get("examples", [])
                    desc = skill_data.get("description", "")
                    truncated_desc = desc[:120] + "..." if len(desc) > 120 else desc

                    st.markdown(
                        f"""
                        <div class="skill-card">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                                <h4 style="color: #F1F5F9; font-size: 1rem; margin: 0; font-weight: 600;">{skill_file.stem}</h4>
                                <span class="skill-tag">{domain}</span>
                            </div>
                            <p style="color: #94A3B8; font-size: 0.82rem; line-height: 1.5; margin-bottom: 12px;">
                                {truncated_desc}
                            </p>
                            <div style="display: flex; gap: 16px; color: #64748B; font-size: 0.75rem;">
                                <span>🔧 {len(tools)} tools</span>
                                <span>📄 {len(examples)} examples</span>
                                <span>v{skill_data.get('version', '1.0')}</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # Detailed view
            st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)
            st.divider()
            st.subheader("🔍 Skill Inspector")

            skill_names = [f.stem for f in skill_files]
            selected_skill = st.selectbox("Select a skill to inspect", skill_names, index=0)

            skill_path = skills_dir / f"{selected_skill}.yaml"
            with open(skill_path) as f:
                skill_data = yaml.safe_load(f)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Domain", skill_data.get("domain", "general"))
            col2.metric("Version", skill_data.get("version", "1.0.0"))
            col3.metric("Tools", len(skill_data.get("tools", [])))
            col4.metric("Examples", len(skill_data.get("examples", [])))

            st.markdown(f"**{skill_data.get('description', '')}**")

            with st.expander("📋 System Prompt"):
                st.code(skill_data.get("system_prompt", ""), language="text")

            with st.expander("🔧 Tools & Guardrails"):
                tcol1, tcol2 = st.columns(2)
                with tcol1:
                    st.markdown("**Allowed Tools:**")
                    for tool in skill_data.get("tools", []):
                        st.code(tool, language="text")
                with tcol2:
                    st.markdown("**Guardrails:**")
                    st.json(skill_data.get("guardrails", {}))

            with st.expander("📥 Input / 📤 Output Schema"):
                icol, ocol = st.columns(2)
                with icol:
                    st.markdown("**Input Schema:**")
                    for field in skill_data.get("input_schema", []):
                        req = "(required)" if field.get("required", True) else "(optional)"
                        st.markdown(f"- `{field['name']}` : {field.get('type', 'string')} {req}")
                with ocol:
                    st.markdown("**Output Schema:**")
                    for field in skill_data.get("output_schema", []):
                        st.markdown(f"- `{field['name']}` : {field.get('type', 'string')}")

            with st.expander("📄 Raw YAML"):
                st.code(open(skill_path).read(), language="yaml")
        else:
            st.info("No skills found in the library.")

        # Create new skill
        st.divider()
        st.markdown(
            "<h3 style='color: #F1F5F9; font-weight: 700;'>✨ Create a New Skill</h3>"
            "<p style='color: #94A3B8; font-size: 0.9rem;'>Describe what you want the agent to do, and the Skill Builder will generate a skill YAML.</p>",
            unsafe_allow_html=True,
        )

        with st.form("create_skill_form"):
            skill_desc = st.text_area(
                "Skill Description",
                placeholder="e.g., I need a skill that analyzes drug interactions between multiple medications...",
                height=100,
            )
            skill_domain = st.selectbox("Target Domain", ["general", "healthtech", "fintech", "edtech", "enterprise_ops"])
            submitted = st.form_submit_button("🚀 Generate Skill", type="primary")

            if submitted and skill_desc:
                with st.spinner("Skill Builder Agent is generating your skill..."):
                    result = api_create_skill(skill_desc, skill_domain)
                if "error" in result:
                    st.error(f"Failed: {result['error']}")
                else:
                    st.success("✅ Skill generated successfully!")
                    st.json(result)

    # ----- Prompt Templates Tab -----
    with prompt_tab:
        templates_dir = Path(__file__).resolve().parents[2] / "packages" / "agent-harness" / "agent_harness" / "prompts" / "templates"
        template_files = sorted(templates_dir.glob("*.yaml")) if templates_dir.exists() else []

        if template_files:
            # Display as cards
            cols = st.columns(3)
            for i, tmpl_file in enumerate(template_files):
                with open(tmpl_file) as f:
                    tmpl_data = yaml.safe_load(f)

                with cols[i % 3]:
                    tags = tmpl_data.get("tags", [])
                    tags_html = "".join(f"<span class='skill-tag'>{t}</span>" for t in tags[:3])
                    desc = tmpl_data.get("description", "")
                    truncated_desc = desc[:100] + "..." if len(desc) > 100 else desc

                    st.markdown(
                        f"""
                        <div class="skill-card">
                            <h4 style="color: #F1F5F9; font-size: 1rem; margin: 0 0 6px; font-weight: 600;">{tmpl_file.stem}</h4>
                            <p style="color: #94A3B8; font-size: 0.82rem; line-height: 1.5; margin-bottom: 10px;">
                                {truncated_desc}
                            </p>
                            <div style="margin-bottom: 8px;">{tags_html}</div>
                            <div style="color: #64748B; font-size: 0.75rem;">
                                📊 {len(tmpl_data.get('variables', []))} variables · v{tmpl_data.get('version', '1.0')}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # Detailed view
            st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)
            st.divider()
            st.subheader("🔍 Template Inspector")

            template_names = [f.stem for f in template_files]
            selected_template = st.selectbox("Select a template to inspect", template_names, index=0)

            tmpl_path = templates_dir / f"{selected_template}.yaml"
            with open(tmpl_path) as f:
                tmpl_data = yaml.safe_load(f)

            col1, col2, col3 = st.columns(3)
            col1.metric("Version", tmpl_data.get("version", "1.0.0"))
            col2.metric("Variables", len(tmpl_data.get("variables", [])))
            col3.metric("Tags", ", ".join(tmpl_data.get("tags", [])))

            st.markdown(f"**{tmpl_data.get('description', '')}**")

            with st.expander("📝 Jinja2 Template"):
                st.code(tmpl_data.get("template", ""), language="jinja2")

            with st.expander("📊 Variables"):
                for var in tmpl_data.get("variables", []):
                    req = "(required)" if var.get("required", True) else f"(optional, default: {var.get('default', 'None')})"
                    st.markdown(f"- **`{var['name']}`** : `{var.get('type', 'string')}` {req}")
                    if var.get("description"):
                        st.caption(f"  ↳ {var['description']}")

            with st.expander("📄 Raw YAML"):
                st.code(open(tmpl_path).read(), language="yaml")
        else:
            st.info("No prompt templates found in the library.")

        # Create new prompt template
        st.divider()
        st.markdown(
            "<h3 style='color: #F1F5F9; font-weight: 700;'>✨ Create a New Template</h3>"
            "<p style='color: #94A3B8; font-size: 0.9rem;'>Describe what the prompt should do, and the builder will generate a Jinja2 template.</p>",
            unsafe_allow_html=True,
        )

        with st.form("create_prompt_form"):
            prompt_desc = st.text_area(
                "Template Description",
                placeholder="e.g., I need a prompt that makes the agent cite sources in APA format...",
                height=100,
            )
            submitted = st.form_submit_button("🚀 Generate Template", type="primary")

            if submitted and prompt_desc:
                with st.spinner("Prompt Builder Agent is generating your template..."):
                    result = api_create_prompt(prompt_desc)
                if "error" in result:
                    st.error(f"Failed: {result['error']}")
                else:
                    st.success("✅ Prompt template generated!")
                    st.json(result)


# ---------------------------------------------------------------------------
# Diagnostics Page
# ---------------------------------------------------------------------------
elif page == "📊  Diagnostics":
    st.markdown("<h2 class='gradient-text' style='font-size: 2rem; margin-bottom: 4px;'>System Diagnostics</h2>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle-text'>Monitor platform health, configuration, and infrastructure status.</p>", unsafe_allow_html=True)

    # Top-level health metrics
    health = api_health()
    diag = api_diagnostics()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f"""
            <div class="glass-card" style="text-align: center;">
                <p style="color: #64748B; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;">Status</p>
                <div style="font-size: 2rem; margin-bottom: 4px;">{'🟢' if health.get('status') == 'healthy' else '🔴'}</div>
                <p style="color: #F1F5F9; font-weight: 600; font-size: 0.95rem;">
                    {'Healthy' if health.get('status') == 'healthy' else 'Down'}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="glass-card" style="text-align: center;">
                <p style="color: #64748B; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;">Version</p>
                <div style="font-size: 2rem; margin-bottom: 4px;">📦</div>
                <p style="color: #F1F5F9; font-weight: 600; font-size: 0.95rem;">
                    v{health.get('version', '2.0.0')}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="glass-card" style="text-align: center;">
                <p style="color: #64748B; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;">Active Schema</p>
                <div style="font-size: 2rem; margin-bottom: 4px;">🗂️</div>
                <p style="color: #F1F5F9; font-weight: 600; font-size: 0.95rem;">
                    {active_schema}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
            <div class="glass-card" style="text-align: center;">
                <p style="color: #64748B; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;">Schemas</p>
                <div style="font-size: 2rem; margin-bottom: 4px;">📋</div>
                <p style="color: #F1F5F9; font-weight: 600; font-size: 0.95rem;">
                    {len(schemas)} available
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)

    # Infrastructure details
    st.markdown("<h3 style='color: #F1F5F9; font-weight: 700; font-size: 1.2rem;'>🗄️ Infrastructure</h3>", unsafe_allow_html=True)

    infra_cols = st.columns(3)
    services = [
        ("Neo4j", "Graph Database", "http://localhost:7474", "bolt://localhost:7687"),
        ("Qdrant", "Vector Store", "http://localhost:6333/dashboard", "http://localhost:6333"),
        ("PostgreSQL", "Tabular Store", "—", "postgresql://localhost:5432"),
    ]
    for i, (name, desc, ui_url, conn_url) in enumerate(services):
        with infra_cols[i]:
            st.markdown(
                f"""
                <div class="glass-card">
                    <h4 style="color: #F1F5F9; font-size: 1rem; margin: 0 0 4px; font-weight: 600;">{name}</h4>
                    <p style="color: #94A3B8; font-size: 0.82rem; margin-bottom: 12px;">{desc}</p>
                    <div style="color: #64748B; font-size: 0.75rem;">
                        <p style="margin: 2px 0;">🌐 UI: <code style="color: #A78BFA;">{ui_url}</code></p>
                        <p style="margin: 2px 0;">🔌 Conn: <code style="color: #A78BFA;">{conn_url}</code></p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)

    # Available schemas
    st.markdown("<h3 style='color: #F1F5F9; font-weight: 700; font-size: 1.2rem;'>📋 Available Schemas</h3>", unsafe_allow_html=True)
    schema_cols = st.columns(len(schemas))
    schema_icons = {"healthtech": "💊", "fintech": "💰", "edtech": "🎓", "enterprise_ops": "🏢"}
    for i, schema in enumerate(schemas):
        with schema_cols[i]:
            icon = schema_icons.get(schema, "📄")
            is_active = schema == active_schema
            border_style = "border-color: rgba(122,82,244,0.5);" if is_active else ""
            st.markdown(
                f"""
                <div class="glass-card" style="text-align: center; {border_style}">
                    <div style="font-size: 1.8rem; margin-bottom: 6px;">{icon}</div>
                    <p style="color: #F1F5F9; font-weight: 600; font-size: 0.9rem; margin: 0;">{schema}</p>
                    {'<p style="color: #22C55E; font-size: 0.72rem; margin-top: 4px; font-weight: 500;">● ACTIVE</p>' if is_active else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Raw diagnostics
    st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)
    with st.expander("🔧 Raw Diagnostics Data"):
        st.json({"health": health, "diagnostics": diag})
