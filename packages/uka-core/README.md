# Universal Knowledge Artifact (`.uka`) — Core Engine & Lifecycle

The **Universal Knowledge Artifact (`.uka`)** is an open, portable, vendor-agnostic container standard designed to eliminate "context lock-in" across AI platforms. 

Modern AI ecosystems—including **Claude.ai (Web)**, **Claude Desktop**, **Cursor IDE**, **Antigravity IDE**, **ChatGPT**, and proprietary enterprise platforms—trap conversational knowledge, multimodal attachments, active entity subgraphs, and vector embeddings in siloed databases. 

The `.uka` standard establishes a self-describing, content-addressed bundle that packages:
1. **Conversational History & Distilled Infinite Memory**
2. **Deterministic Knowledge Graph Subgraphs (Neo4j Nodes, Edges, Properties)**
3. **Semantic Vector Chunks & Embeddings (Qdrant)**
4. **Palantir-Style Domain Ontology Schemas (YAML)**
5. **Multimodal Media with Pre-computed Transcripts, OCR, and Slide Summaries**

---

## 🔄 The Complete UKA Lifecycle

```mermaid
flowchart TD
    subgraph Sourcing["1. Extraction & Adaptation"]
        CKPSession["CKP Active Session<br/>(Neo4j + Qdrant + SQLite)"]
        ClaudeWeb["Claude.ai Web<br/>(Export Archive)"]
        Cursor["Cursor IDE<br/>(Workspace & Code Chat)"]
        GenericDocs["Markdown & Notes<br/>(Transcripts & Docs)"]
    end

    subgraph Packaging["2. Packaging & Serialization"]
        Writer["UKABundleWriter<br/>(SHA-256 Digest Catalog)"]
        UKAArchive["📦 my_session.uka<br/>(DEFLATE Zip Container)"]
    end

    subgraph DualLayer["3. Dual-Layer Artifact Architecture"]
        L1["Layer 1: Direct Read Tier<br/>manifest.json | context.md | schema.yaml"]
        L2["Layer 2: Machine Rehydration Tier<br/>subgraph.json | cypher_import.cql | chunks.json"]
        MM["Multimodal Tier<br/>raw_media/* + media/index.json"]
    end

    subgraph Serving["4. Serving & Consumption"]
        FastMCP["FastMCP Server<br/>(stdio / sse)"]
        PromptInj["Direct Context Injection<br/>(Claude Web / Cursor)"]
        Importer["UKAImporter<br/>(Database Rehydration)"]
    end

    subgraph Targets["5. Target Environments"]
        ExternalAgents["Claude Desktop / Cursor / Antigravity"]
        CleanDatabases["Neo4j Graph + Qdrant Vectors + SQLite"]
    end

    CKPSession -->|UKAExporter| Writer
    ClaudeWeb -->|ClaudeWebAdapter| Writer
    Cursor -->|CursorAdapter| Writer
    GenericDocs -->|GenericMarkdownAdapter| Writer

    Writer --> UKAArchive
    UKAArchive --> L1
    UKAArchive --> L2
    UKAArchive --> MM

    UKAArchive --> FastMCP
    UKAArchive --> PromptInj
    UKAArchive --> Importer

    FastMCP --> ExternalAgents
    Importer --> CleanDatabases
```

---

## 📁 Container Directory Structure

A `.uka` file is physically structured as a standard ZIP archive with DEFLATE compression:

```
my_session.uka
├── manifest.json              <-- [Root] Version, metadata, SHA-256 hashes, modality flags
├── context.md                 <-- [Layer 1: Direct Read] Human- & LLM-ready markdown distillation
├── ontology/
│   └── schema.yaml            <-- [Layer 1: Grounding] Palantir-style domain ontology & rules
├── conversations/
│   ├── transcript.json        <-- Full conversational turns with role and timestamps
│   └── distilled_memory.json  <-- Extracted entities, confirmed decisions, open questions
├── graph/
│   ├── subgraph.json          <-- [Layer 2: Rehydration] Graph nodes, relationships, properties
│   └── cypher_import.cql      <-- Executable Cypher script to restore Neo4j graph state
├── vectors/
│   ├── chunks.json            <-- Text chunks + document IDs + provenance metadata
│   └── embeddings.bin         <-- Compact IEEE 754 float32 binary embeddings (optional)
└── media/                     <-- [Multimodal Dual Representation]
    ├── index.json             <-- Pre-computed transcripts, OCR, slide summaries, diarization
    ├── sample_scan.png        <-- Content-addressed binary asset
    ├── protocol_deck.pptx     <-- Content-addressed binary asset
    └── intake_audio.wav       <-- Content-addressed binary asset
```

---

## 🚀 Quickstart & Usage

### 1. Programmatic Bundle Creation (`UKABundleWriter`)

```python
from uka.bundle_writer import UKABundleWriter
from uka.models import (
    UKABundleData,
    UKAManifest,
    UKAMessage,
    UKAGraphNode,
    UKAGraphEdge,
    UKASubgraph,
    UKAVectorChunk,
)

# Build manifest
manifest = UKAManifest(
    artifact_id="uka_cardio_101",
    title="Cardiology Clinical Review",
    description="Lisinopril contraindication assessment and trial findings.",
    modalities=["text", "graph", "vector"],
)

# Messages & Knowledge
messages = [
    UKAMessage(role="user", content="What are the contraindications for Lisinopril?"),
    UKAMessage(role="assistant", content="Lisinopril is contraindicated in patients with a history of angioedema."),
]

nodes = [
    UKAGraphNode(id="med_001", labels=["Medication"], properties={"name": "Lisinopril"}),
    UKAGraphNode(id="cond_002", labels=["Condition"], properties={"name": "Angioedema"}),
]
edges = [
    UKAGraphEdge(id="rel_01", type="CONTRAINDICATED_IN", source="med_001", target="cond_002"),
]

bundle_data = UKABundleData(
    manifest=manifest,
    context_md="# Cardiology Clinical Review\nLisinopril is contraindicated in angioedema.",
    messages=messages,
    subgraph=UKASubgraph(nodes=nodes, edges=edges),
)

writer = UKABundleWriter()
out_path = writer.write(bundle_data, "cardiology.uka")
print(f"Created bundle: {out_path}")
```

---

### 2. Random-Access Reading & Cryptographic Verification (`UKABundleReader`)

```python
from uka.bundle_reader import UKABundleReader

reader = UKABundleReader("cardiology.uka")

# Cryptographic SHA-256 tamper verification
is_valid, errors = reader.verify_integrity()
if not is_valid:
    raise ValueError(f"Bundle corrupted: {errors}")

# Read metadata without unpacking to disk
manifest = reader.read_manifest()
print(f"Artifact: {manifest.title} ({manifest.artifact_id})")

# Direct markdown context for LLM prompt injection
context_md = reader.read_context_markdown()

# Read graph nodes without requiring Neo4j
subgraph = reader.read_subgraph()
for node in subgraph.nodes:
    print(f"Node: {node.labels} -> {node.properties}")
```

---

### 3. Bidirectional Database Rehydration (`UKAImporter`)

```python
from uka.importer import UKAImporter
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

neo4j_driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
qdrant_client = QdrantClient(url="http://localhost:6333")

importer = UKAImporter(
    neo4j_driver=neo4j_driver,
    qdrant_client=qdrant_client,
    media_storage_dir="data/media",
)

result = importer.import_bundle("cardiology.uka", verify_integrity=True)
print(f"Nodes restored: {result['nodes_restored']}")
print(f"Edges restored: {result['edges_restored']}")
print(f"Vectors restored: {result['vectors_restored']}")
```

---

### 4. Ecosystem Adapters
 
#### Ingesting Claude.ai Export Archives (`ClaudeWebAdapter`)
```python
from uka.adapters import ClaudeWebAdapter

adapter = ClaudeWebAdapter()
bundle_path = adapter.adapt(
    source="path/to/claude_export/conversations.json",
    output_path="claude_session.uka",
    session_id="optional-specific-uuid",
)
```

#### Ingesting Cursor IDE Workspace Chats (`CursorAdapter`)
```python
from uka.adapters import CursorAdapter

adapter = CursorAdapter()
bundle_path = adapter.adapt(
    source="path/to/cursor_chat.md",
    output_path="cursor_session.uka",
    title="Feature Implementation Session",
)
```

#### Ingesting Markdown Documents & Meeting Notes (`GenericMarkdownAdapter`)
```python
from uka.adapters import GenericMarkdownAdapter

adapter = GenericMarkdownAdapter()
bundle_path = adapter.adapt(
    source="path/to/research_notes.md",
    output_path="research_notes.uka",
)
```

---

### 5. Running the UKA FastMCP Server

Connect `.uka` bundles directly to Claude Desktop, Cursor, or external agents over the Model Context Protocol:

```bash
# STDIO transport (for Claude Desktop / Cursor configuration)
uv run uka-mcp --transport stdio

# SSE transport (for network-accessible agents)
uv run uka-mcp --transport sse --port 8008
```

#### Claude Desktop Configuration (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "uka": {
      "command": "uv",
      "args": ["run", "--package", "ckp-uka-mcp-server", "uka-mcp", "--transport", "stdio"]
    }
  }
}
```

---

## 🌐 Platform REST API Endpoints

- **Export Active Session**:
  `GET /api/v2/sessions/{session_id}/export/uka`  
  Returns: `application/x-uka+zip` binary stream attachment.

- **Import External Bundle**:
  `POST /api/v2/uka/import`  
  Form-data: `file: <binary .uka archive>`  
  Returns:
  ```json
  {
    "status": "success",
    "session_id": "uka_cardio_101",
    "nodes_restored": 28,
    "edges_restored": 34,
    "vectors_restored": 42,
    "messages_restored": 14,
    "media_files_saved": 3
  }
  ```
