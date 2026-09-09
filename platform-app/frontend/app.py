"""
CKP Streamlit Frontend — Interactive UI for the Cognitive Knowledge Platform.

Provides:
- Chat interface for querying the knowledge agent
- File upload for data ingestion
- Skills & Prompts library browser
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
# Custom CSS Styling (Glassmorphism, Animations, Fonts)
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

/* Removed all header-hiding CSS to ensure the sidebar toggle is completely untouched and visible */

::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: #0F1117;
}
::-webkit-scrollbar-thumb {
    background: #2D3240;
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: #7A52F4;
}

.stButton > button {
    border-radius: 8px !important;
    transition: all 0.3s ease !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
}
.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(122,82,244, 0.4) !important;
    border-color: #7A52F4 !important;
}

[data-testid="stSidebar"] {
    background: rgba(30, 33, 43, 0.7) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border-right: 1px solid rgba(255,255,255,0.05) !important;
}

/* Ensure the collapsed sidebar toggle button is always visible and clickable */
[data-testid="collapsedControl"] {
    display: block !important;
    z-index: 999999 !important;
    background: rgba(30, 33, 43, 0.8) !important;
    border-radius: 50% !important;
}
[data-testid="collapsedControl"]:hover {
    background: rgba(122,82,244, 0.5) !important;
}


/* Transform Sidebar Radio into a Premium Vertical Menu */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 8px;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
    background-color: transparent;
    padding: 12px 16px;
    border-radius: 8px;
    transition: all 0.2s ease;
    border: 1px solid transparent;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover {
    background-color: rgba(122,82,244, 0.1);
    border-color: rgba(122,82,244, 0.3);
    transform: translateX(4px);
}
/* Hide the ugly radio circle */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
    display: none;
}
/* Style the text inside the radio block */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] p {
    font-size: 1.05rem;
    font-weight: 500;
}


.stChatInputContainer {
    background: rgba(30, 33, 43, 0.6) !important;
    backdrop-filter: blur(10px) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
}

[data-testid="stExpander"] {
    background: rgba(30, 33, 43, 0.4) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(255,255,255,0.05) !important;
    transition: all 0.3s ease !important;
}
[data-testid="stExpander"]:hover {
    border-color: rgba(122,82,244, 0.5) !important;
    background: rgba(30, 33, 43, 0.7) !important;
}

[data-testid="stMetricValue"] {
    font-weight: 700 !important;
    background: -webkit-linear-gradient(45deg, #7A52F4, #00D2FF);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] {
    border-radius: 8px !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    transition: all 0.3s ease !important;
}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within {
    border-color: #7A52F4 !important;
    box-shadow: 0 0 0 1px #7A52F4 !important;
}

/* Gradient Header */
.gradient-text {
    background: -webkit-linear-gradient(45deg, #7A52F4, #00D2FF);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("<h1 class='gradient-text' style='text-align: center;'>🧠 CKP</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #a1a1aa;'>Cognitive Knowledge Platform v2</p>", unsafe_allow_html=True)

    st.divider()

    # Schema selector
    schemas = api_schemas()
    active_schema = st.selectbox("Active Schema", schemas, index=0)

    st.divider()

    # Navigation
    page = st.radio(
        "Navigate",
        ["💬 Chat", "📤 Ingest", "🧩 Skills & Prompts", "🔧 Diagnostics"],
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
    st.markdown("<h2 class='gradient-text'>💬 Knowledge Agent</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color: #a1a1aa; font-size: 1.1em;'>Ask questions about your ingested data using natural language.</p>", unsafe_allow_html=True)

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = None

    # Fetch available skills for the dropdown
    skills_data = api_list_skills()
    skill_options = ["auto"] + [s["name"] for s in skills_data]
    
    col1, col2 = st.columns([3, 1])
    with col2:
        active_skill = st.selectbox(
            "Agent Mode / Skill", 
            options=skill_options, 
            format_func=lambda x: "🤖 Auto-Select (Agentic)" if x == "auto" else f"⚡ {x}"
        )
    with col1:
        st.caption("Select a specific skill to force the agent's behavior, or let it auto-select based on the query.")

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
                    active_skill=active_skill,
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
    st.markdown("<h2 class='gradient-text'>📤 Data Ingestion</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color: #a1a1aa; font-size: 1.1em;'>Upload files to build your knowledge graph.</p>", unsafe_allow_html=True)

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
# Skills & Prompts Library Page
# ---------------------------------------------------------------------------
elif page == "🧩 Skills & Prompts":
    st.markdown("<h2 class='gradient-text'>🧩 Skills & Prompts Library</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color: #a1a1aa; font-size: 1.1em;'>Browse, inspect, and create reusable agent skills and prompt templates.</p>", unsafe_allow_html=True)

    skill_tab, prompt_tab = st.tabs(["🛠️ Skills Library", "📝 Prompt Templates"])

    # ----- Skills Tab -----
    with skill_tab:
        st.subheader("Agent Skills")
        st.markdown(
            "Skills are reusable, declarative packages of agent behavior. "
            "Each skill defines a system prompt, tool whitelist, guardrail "
            "overrides, and input/output contracts."
        )

        # Load skills from the local YAML library (offline-friendly)
        from pathlib import Path
        import yaml

        skills_dir = Path(__file__).resolve().parents[2] / "packages" / "agent-harness" / "agent_harness" / "skills" / "library"
        skill_files = sorted(skills_dir.glob("*.yaml")) if skills_dir.exists() else []

        if skill_files:
            # Skill selector
            skill_names = [f.stem for f in skill_files]
            selected_skill = st.selectbox("Select a skill", skill_names, index=0)

            # Load and display the selected skill
            skill_path = skills_dir / f"{selected_skill}.yaml"
            with open(skill_path) as f:
                skill_data = yaml.safe_load(f)

            # Header metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Domain", skill_data.get("domain", "general"))
            col2.metric("Version", skill_data.get("version", "1.0.0"))
            col3.metric("Tools", len(skill_data.get("tools", [])))
            col4.metric("Examples", len(skill_data.get("examples", [])))

            st.markdown(f"**Description:** {skill_data.get('description', '')}")

            # Details in expanders
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
        st.subheader("✨ Create a New Skill")
        st.caption("Describe what you want the agent to do, and the Skill Builder Agent will generate a skill YAML for you.")

        with st.form("create_skill_form"):
            skill_desc = st.text_area(
                "Skill Description",
                placeholder="e.g., I need a skill that analyzes drug interactions between multiple medications...",
                height=100,
            )
            skill_domain = st.selectbox("Target Domain", ["general", "healthtech", "fintech", "edtech", "enterprise_ops"])
            submitted = st.form_submit_button("Generate Skill", type="primary")

            if submitted and skill_desc:
                with st.spinner("Skill Builder Agent is generating your skill..."):
                    result = api_create_skill(skill_desc, skill_domain)
                if "error" in result:
                    st.error(f"Failed: {result['error']}")
                else:
                    st.success("Skill generated successfully!")
                    st.json(result)

    # ----- Prompt Templates Tab -----
    with prompt_tab:
        st.subheader("Prompt Templates")
        st.markdown(
            "Prompt templates are versioned, composable Jinja2 building blocks "
            "for system prompts. Instead of writing prompts from scratch, "
            "assemble them from a library of tested fragments."
        )

        # Load templates from the local YAML library
        templates_dir = Path(__file__).resolve().parents[2] / "packages" / "agent-harness" / "agent_harness" / "prompts" / "templates"
        template_files = sorted(templates_dir.glob("*.yaml")) if templates_dir.exists() else []

        if template_files:
            template_names = [f.stem for f in template_files]
            selected_template = st.selectbox("Select a template", template_names, index=0)

            # Load and display
            tmpl_path = templates_dir / f"{selected_template}.yaml"
            with open(tmpl_path) as f:
                tmpl_data = yaml.safe_load(f)

            # Header metrics
            col1, col2, col3 = st.columns(3)
            col1.metric("Version", tmpl_data.get("version", "1.0.0"))
            col2.metric("Variables", len(tmpl_data.get("variables", [])))
            col3.metric("Tags", ", ".join(tmpl_data.get("tags", [])))

            st.markdown(f"**Description:** {tmpl_data.get('description', '')}")

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
        st.subheader("✨ Create a New Prompt Template")
        st.caption("Describe what the prompt should do, and the Prompt Builder Agent will generate a Jinja2 template for you.")

        with st.form("create_prompt_form"):
            prompt_desc = st.text_area(
                "Template Description",
                placeholder="e.g., I need a prompt that makes the agent cite sources in APA format...",
                height=100,
            )
            submitted = st.form_submit_button("Generate Template", type="primary")

            if submitted and prompt_desc:
                with st.spinner("Prompt Builder Agent is generating your template..."):
                    result = api_create_prompt(prompt_desc)
                if "error" in result:
                    st.error(f"Failed: {result['error']}")
                else:
                    st.success("Prompt template generated successfully!")
                    st.json(result)


# ---------------------------------------------------------------------------
# Diagnostics Page
# ---------------------------------------------------------------------------
elif page == "🔧 Diagnostics":
    st.markdown("<h2 class='gradient-text'>🔧 System Diagnostics</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color: #a1a1aa; font-size: 1.1em;'>Monitor platform health and configuration.</p>", unsafe_allow_html=True)

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
