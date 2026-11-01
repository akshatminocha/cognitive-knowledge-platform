# UKA FastMCP Server (`ckp-uka-mcp-server`)

A high-performance **Model Context Protocol (MCP)** server built with **FastMCP** that connects portable **Universal Knowledge Artifact (`.uka`)** bundles directly to external AI platforms including **Claude Desktop**, **Claude Code**, **Cursor IDE**, and **Antigravity IDE**.

---

## 🛠️ Exposed MCP Tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `uka_inspect` | `bundle_path: str` | Validates SHA-256 cryptographic integrity, inspects manifest metadata, and lists internal archive files. |
| `uka_export_context` | `bundle_path: str` | Extracts the unified Layer 1 Markdown context (`context.md`) for zero-shot LLM prompt injection. |
| `uka_get_schema` | `bundle_path: str` | Extracts the domain ontology schema (`ontology/schema.yaml`) with Palantir-style entity types and rules. |
| `uka_search` | `bundle_path: str, query: str, limit: int = 5` | Full-text and keyword search across vector chunks, message transcripts, and multimodal index. |
| `uka_query_graph` | `bundle_path: str, node_label: str = None, name_filter: str = None` | Filters knowledge graph topology from `graph/subgraph.json` without requiring a live Neo4j instance. |
| `uka_list_entities` | `bundle_path: str` | Lists all entity nodes, labels, and properties stored in the bundle. |
| `uka_get_media` | `bundle_path: str, asset_id: str = None` | Retrieves precomputed multimodal transcripts, OCR text, and slide notes from `media/index.json`. |

---

## 🚀 Running the Server

### 1. STDIO Transport (Local Agents)

```bash
uv run uka-mcp --transport stdio
```

### 2. SSE Transport (Network / Remote Agents)

```bash
uv run uka-mcp --transport sse --host 0.0.0.0 --port 8008
```

---

## 🔌 Integration with External AI Platforms

### Claude Desktop Configuration
Add the server to your `claude_desktop_config.json` (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "uka-server": {
      "command": "uv",
      "args": [
        "run",
        "--package",
        "ckp-uka-mcp-server",
        "uka-mcp",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

### Cursor IDE Configuration
In Cursor Settings $\rightarrow$ Features $\rightarrow$ MCP Servers:
- **Name:** `uka-server`
- **Type:** `command`
- **Command:** `uv run --package ckp-uka-mcp-server uka-mcp --transport stdio`
