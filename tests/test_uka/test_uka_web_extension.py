"""
Unit and Integration Tests for UKA Browser Web Extension (Manifest V3).

Verifies manifest structure, icon validity, native zero-dependency ZIP packaging,
cryptographic SHA-256 integrity verification, and interoperability with the UKA engine.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import unittest
import zipfile

EXTENSION_ROOT = Path("extensions/uka-web-extension")


class TestExtensionManifestAndAssets(unittest.TestCase):
    """Verifies Chrome Extension Manifest V3 configuration and assets."""

    def test_extension_directory_exists(self):
        assert EXTENSION_ROOT.is_dir(), f"Extension directory missing at {EXTENSION_ROOT}"

    def test_manifest_v3_structure(self):
        manifest_path = EXTENSION_ROOT / "manifest.json"
        assert manifest_path.is_file(), "manifest.json is missing"

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert manifest.get("manifest_version") == 3
        assert manifest.get("name") == "UKA Knowledge Clipper & Inspector"
        assert "version" in manifest

        # Permissions check
        permissions = set(manifest.get("permissions", []))
        expected_permissions = {"activeTab", "scripting", "storage", "sidePanel", "downloads"}
        assert expected_permissions.issubset(permissions), f"Missing permissions: {expected_permissions - permissions}"

        # Action & Side Panel check
        action = manifest.get("action", {})
        assert action.get("default_popup") == "popup/popup.html"
        assert "default_icon" in action

        side_panel = manifest.get("side_panel", {})
        assert side_panel.get("default_path") == "sidepanel/sidepanel.html"

        # Background worker check
        background = manifest.get("background", {})
        assert background.get("service_worker") == "service-worker.js"

    def test_required_files_presence(self):
        required_files = [
            "manifest.json",
            "service-worker.js",
            "content/content-script.js",
            "lib/zip.js",
            "lib/uka-packager.js",
            "popup/popup.html",
            "popup/popup.css",
            "popup/popup.js",
            "sidepanel/sidepanel.html",
            "sidepanel/sidepanel.css",
            "sidepanel/sidepanel.js",
            "icons/icon-16.png",
            "icons/icon-48.png",
            "icons/icon-128.png",
            "README.md",
        ]
        for rel_file in required_files:
            file_path = EXTENSION_ROOT / rel_file
            assert file_path.is_file(), f"Required extension file missing: {rel_file}"

    def test_png_icons_validity(self):
        icon_dimensions = {
            "icons/icon-16.png": (16, 16),
            "icons/icon-48.png": (48, 48),
            "icons/icon-128.png": (128, 128),
        }
        for rel_path, (exp_w, exp_h) in icon_dimensions.items():
            icon_file = EXTENSION_ROOT / rel_path
            data = icon_file.read_bytes()
            # PNG signature: 89 50 4E 47 0D 0A 1A 0A
            assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{rel_path} is not a valid PNG file"
            # IHDR width and height at bytes 16:24
            w, h = struct.unpack(">II", data[16:24])
            assert (w, h) == (exp_w, exp_h), f"{rel_path} dimensions ({w}x{h}) do not match ({exp_w}x{exp_h})"


class TestNodePackagerRoundtrip(unittest.TestCase):
    """Verifies that the client-side JavaScript packager produces valid, compliant .uka archives."""

    def setUp(self):
        """Runs Node.js script using native CompressionStream to package a test .uka archive."""
        with tempfile.NamedTemporaryFile(suffix=".uka", delete=False) as tmp:
            self.test_bundle_file = Path(tmp.name)

        node_script = f"""
import('{EXTENSION_ROOT.resolve() / "lib" / "uka-packager.js"}').then(async (m) => {{
  const fs = await import('fs');
  const result = await m.packageWebPageToUka({{
    url: 'https://clinicaltrials.gov/study/NCT02684786',
    title: 'Pembrolizumab Plus Chemotherapy in Metastatic NSCLC',
    content: 'Keynote-189: randomized double-blind phase 3 clinical trial evaluating pembrolizumab with pemetrexed and platinum chemotherapy for non-small cell lung cancer.',
    entities: [
      {{ name: 'Pembrolizumab', label: 'Medication', occurrences: 12 }},
      {{ name: 'NSCLC', label: 'Disease', occurrences: 8 }},
      {{ name: 'Pemetrexed', label: 'Medication', occurrences: 6 }}
    ],
    images: [
      {{ src: 'https://example.com/figure1.jpg', alt: 'Kaplan-Meier overall survival curve', width: 800, height: 600 }}
    ],
    tables: [
      '| Endpoint | Pembrolizumab + Chemo | Placebo + Chemo | HR |\\n|---|---|---|---|\\n| Median OS | 22.0 mos | 10.7 mos | 0.56 |'
    ],
    schemaDomain: 'healthtech'
  }});
  fs.writeFileSync('{self.test_bundle_file}', Buffer.from(result.buffer));
  const inspection = await m.inspectUkaBundle(result.buffer.buffer);
  process.stdout.write(JSON.stringify(inspection));
}}).catch(err => {{
  console.error(err);
  process.exit(1);
}});
"""
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Node packaging failed:\nStdout: {proc.stdout}\nStderr: {proc.stderr}")

        inspection = json.loads(proc.stdout)
        self.assertTrue(inspection["integrityPassed"])
        self.assertEqual(inspection["totalFiles"], 6)

    def tearDown(self):
        if self.test_bundle_file.exists():
            self.test_bundle_file.unlink()

    def test_python_zipfile_integrity_and_decompression(self):
        """Python standard library zipfile must unpack and verify every entry."""
        self.assertTrue(zipfile.is_zipfile(self.test_bundle_file))

        with zipfile.ZipFile(self.test_bundle_file, "r") as zf:
            names = set(zf.namelist())
            expected_names = {
                "manifest.json",
                "context.md",
                "ontology/schema.yaml",
                "graph/subgraph.json",
                "vectors/chunks.json",
                "media/index.json",
            }
            self.assertTrue(expected_names.issubset(names), f"Missing archive members: {expected_names - names}")

            # 1. Parse manifest.json
            manifest_raw = zf.read("manifest.json").decode("utf-8")
            manifest = json.loads(manifest_raw)
            self.assertEqual(manifest["uka_version"], "0.1.0")
            self.assertTrue(manifest["artifact_id"].startswith("uka_"))
            self.assertEqual(manifest["domain"], "healthtech")
            self.assertIn("text", manifest["modalities"])

            # 2. Verify all cryptographic SHA-256 hashes
            content_hashes = manifest["content_hashes"]
            self.assertEqual(len(content_hashes), 5)

            for file_path, exp_hash in content_hashes.items():
                self.assertIn(file_path, names, f"Declared file {file_path} not found in zip")
                file_bytes = zf.read(file_path)
                actual_hash = f"sha256:{hashlib.sha256(file_bytes).hexdigest()}"
                self.assertEqual(actual_hash, exp_hash, f"SHA-256 checksum mismatch for {file_path}")

            # 3. Verify Graph Subgraph
            subgraph_raw = zf.read("graph/subgraph.json").decode("utf-8")
            subgraph = json.loads(subgraph_raw)
            nodes = subgraph.get("nodes", [])
            edges = subgraph.get("edges", [])
            self.assertGreaterEqual(len(nodes), 4)  # Root WebPage + 3 entities
            self.assertGreaterEqual(len(edges), 3)  # 3 MENTIONS relationships

            node_labels = [n.get("labels", []) for n in nodes]
            flat_labels = [l for sub in node_labels for l in sub]
            self.assertIn("WebPage", flat_labels)
            self.assertIn("Medication", flat_labels)
            self.assertIn("Disease", flat_labels)

            # 4. Verify Vector Chunks
            chunks_raw = zf.read("vectors/chunks.json").decode("utf-8")
            chunks = json.loads(chunks_raw)
            self.assertGreaterEqual(len(chunks), 1)
            self.assertIn("text", chunks[0])
            self.assertIn("chunk_id", chunks[0])
            self.assertEqual(chunks[0]["document_id"], manifest["artifact_id"])

            # 5. Verify Context Markdown
            context_md = zf.read("context.md").decode("utf-8")
            self.assertIn("# Pembrolizumab Plus Chemotherapy in Metastatic NSCLC", context_md)
            self.assertIn("Source URL:", context_md)
            self.assertTrue("Kaplan-Meier overall survival curve" in context_md or "Median OS" in context_md)

    def test_tamper_detection(self):
        """Simulate tampering inside the ZIP archive and verify it fails cryptographic verification."""
        with zipfile.ZipFile(self.test_bundle_file, "r") as zf:
            file_contents = {name: zf.read(name) for name in zf.namelist()}

        # Tamper with context.md
        file_contents["context.md"] = b"# TAMPERED MALICIOUS CONTENT"

        with tempfile.NamedTemporaryFile(suffix=".uka", delete=False) as tampered_tmp:
            tampered_path = Path(tampered_tmp.name)

        with zipfile.ZipFile(tampered_path, "w", compression=zipfile.ZIP_DEFLATED) as zf_out:
            for name, content in file_contents.items():
                zf_out.writestr(name, content)

        # Inspect tampered file via Node inspector
        node_script = f"""
import('{EXTENSION_ROOT.resolve() / "lib" / "uka-packager.js"}').then(async (m) => {{
  const fs = await import('fs');
  const buffer = fs.readFileSync('{tampered_path}');
  const inspection = await m.inspectUkaBundle(buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength));
  process.stdout.write(JSON.stringify(inspection));
}}).catch(err => {{
  console.error(err);
  process.exit(1);
}});
"""
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        inspection = json.loads(proc.stdout)

        self.assertFalse(inspection["integrityPassed"])
        tampered_entries = [r for r in inspection["verificationResults"] if r["path"] == "context.md"]
        self.assertEqual(len(tampered_entries), 1)
        self.assertEqual(tampered_entries[0]["status"], "TAMPERED")
        self.assertFalse(tampered_entries[0]["valid"])

        # Cleanup
        if tampered_path.exists():
            tampered_path.unlink()
