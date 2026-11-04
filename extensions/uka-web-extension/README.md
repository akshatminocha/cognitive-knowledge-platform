# UKA Knowledge Clipper & Inspector — Chrome Web Extension (Manifest V3)

The **UKA Browser Web Extension** enables instant, zero-loss clipping of web research, clinical papers, financial analyses, and enterprise documents into standardized **Universal Knowledge Artifacts (`.uka`)**.

It operates completely client-side in Google Chrome (and Chromium browsers) with **zero third-party dependencies**, utilizing native Web Streams (`CompressionStream`, `DecompressionStream`) and Web Cryptography API (`crypto.subtle`) for instant ZIP compression and SHA-256 integrity verification.

---

## Key Capabilities

1. **Intelligent Web Clipper**:
   - Strips boilerplate (navigation, footers, ads) and distills primary article content into structured Markdown.
   - Extracts structured tables and formats them into GitHub Flavored Markdown.
   - Identifies candidate domain entities (clinical terms, ICD codes, companies, tickers, people).
   - Generates Palantir-governed ontology schemas (`ontology/schema.yaml`) matching the active domain (`healthtech`, `fintech`, `general`).
   - Produces canonical `.uka` v0.1 archive bundles directly in the browser.

2. **1-Click Platform Sync**:
   - Direct multipart upload to CKP platform backend (`POST /api/v2/uka/import`).
   - Automatically rehydrates graph topology into Neo4j and vector chunks into Qdrant.

3. **In-Browser UKA Inspector (Side Panel)**:
   - Drag-and-drop any `.uka` or `.zip` file into the persistent Chrome Side Panel.
   - Verifies SHA-256 cryptographic signatures against `manifest.json`.
   - Explores component files (`context.md`, `schema.yaml`, `subgraph.json`, `chunks.json`).
   - Displays graph topology stats (nodes, edges) and vector chunk counts.

---

## Installation (Developer Mode)

1. Open Google Chrome (or Chromium-based browser like Brave or Microsoft Edge).
2. Navigate to `chrome://extensions/`.
3. In the top right corner, enable **Developer mode**.
4. Click **Load unpacked** in the top left.
5. Select the extension directory:
   ```
   cognitive-knowledge-platform/extensions/uka-web-extension
   ```
6. The **UKA Knowledge Clipper & Inspector** icon will appear in your browser toolbar!

---

## Extension Structure

```
extensions/uka-web-extension/
├── manifest.json              # Manifest V3 configuration & permissions
├── service-worker.js          # Background worker (context menu, downloads, side panel)
├── icons/                     # Crisp icons (16px, 48px, 128px)
├── content/
│   └── content-script.js      # DOM distiller, table parser, and entity extractor
├── lib/
│   ├── zip.js                 # Zero-dependency ZIP encoder/decoder (CompressionStream)
│   └── uka-packager.js        # UKA bundle synthesizer and SHA-256 inspector
├── popup/
│   ├── popup.html             # Compact toolbar popup
│   ├── popup.css              # Dark mode styling & glassmorphic accents
│   └── popup.js               # Quick clip & sync controller
├── sidepanel/
│   ├── sidepanel.html         # Full-featured Side Panel Studio & Inspector
│   ├── sidepanel.css          # Responsive drawer styling
│   └── sidepanel.js           # Multi-tab controller (Clipper, Inspector, Settings)
└── README.md                  # This documentation
```

---

## UKA Specification Compliance

Every bundle synthesized by this extension strictly conforms to the **UKA v0.1 Specification**:

| File in `.uka` | Description | Target Subsystem |
| :--- | :--- | :--- |
| `manifest.json` | Root metadata, modalities, domain, SHA-256 hashes | Core Platform / Catalog |
| `context.md` | Human-readable & zero-shot executive summary | Human & LLM Prompts |
| `ontology/schema.yaml` | Palantir-governed entity & relationship ontology | Ontology Gateway |
| `graph/subgraph.json` | Nodes and directed edges | Neo4j Knowledge Graph |
| `vectors/chunks.json` | Text chunks with source URL and metadata | Qdrant Vector Store |
| `media/index.json` | Extracted images and tabular media | Multimodal Ingestion |

