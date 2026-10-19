"""
Universal Knowledge Artifact (UKA) — Bundle Reader & Integrity Validator.

Provides selective, streaming random-access reading of .uka archives without
requiring full disk extraction, with SHA-256 cryptographic verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from pathlib import Path
from typing import Optional

from uka.models import (
    UKABundleData,
    UKAManifest,
    UKASubgraph,
    UKAVectorChunk,
    UKAMediaIndex,
    UKADistilledMemory,
    UKAMessage,
)

logger = logging.getLogger(__name__)


class UKABundleReader:
    """
    Random-access reader and validator for .uka container archives.
    """

    def __init__(self, file_path: str | Path) -> None:
        self.path = Path(file_path)
        if not self.path.exists():
            raise FileNotFoundError(f"UKA bundle not found: {self.path}")

    def list_files(self) -> list[str]:
        """List all filenames inside the archive."""
        with zipfile.ZipFile(self.path, "r") as zf:
            return zf.namelist()

    def read_manifest(self) -> UKAManifest:
        """Read and parse the root manifest.json."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "manifest.json" not in zf.namelist():
                raise ValueError("Corrupt UKA archive: missing root manifest.json")
            data = zf.read("manifest.json").decode("utf-8")
            return UKAManifest.model_validate_json(data)

    def read_context_markdown(self) -> str:
        """Read the human/LLM-ready context.md distillation."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "context.md" in zf.namelist():
                return zf.read("context.md").decode("utf-8")
            return ""

    def read_ontology(self) -> Optional[str]:
        """Read the domain ontology schema YAML if present."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "ontology/schema.yaml" in zf.namelist():
                return zf.read("ontology/schema.yaml").decode("utf-8")
            return None

    def read_schema_yaml(self) -> Optional[str]:
        """Alias for read_ontology."""
        return self.read_ontology()

    def read_messages(self) -> list[UKAMessage]:
        """Read conversation transcript turns."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "conversations/transcript.json" in zf.namelist():
                raw = zf.read("conversations/transcript.json").decode("utf-8")
                items = json.loads(raw)
                return [UKAMessage.model_validate(item) for item in items]
            return []

    def read_transcript(self) -> list[UKAMessage]:
        """Alias for read_messages."""
        return self.read_messages()

    def read_distilled_memory(self) -> Optional[UKADistilledMemory]:
        """Read distilled infinite memory state."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "conversations/distilled_memory.json" in zf.namelist():
                raw = zf.read("conversations/distilled_memory.json").decode("utf-8")
                return UKADistilledMemory.model_validate_json(raw)
            return None

    def read_subgraph(self) -> Optional[UKASubgraph]:
        """Read knowledge graph nodes and edges."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "graph/subgraph.json" in zf.namelist():
                raw = zf.read("graph/subgraph.json").decode("utf-8")
                return UKASubgraph.model_validate_json(raw)
            return None

    def read_cypher_import(self) -> Optional[str]:
        """Read executable Cypher restore statements."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "graph/cypher_import.cql" in zf.namelist():
                return zf.read("graph/cypher_import.cql").decode("utf-8")
            return None

    def read_vector_chunks(self) -> list[UKAVectorChunk]:
        """Read vector text chunks with provenance."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "vectors/chunks.json" in zf.namelist():
                raw = zf.read("vectors/chunks.json").decode("utf-8")
                items = json.loads(raw)
                return [UKAVectorChunk.model_validate(item) for item in items]
            return []

    def read_embeddings_bin(self) -> Optional[bytes]:
        """Read raw binary float32 embeddings."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "vectors/embeddings.bin" in zf.namelist():
                return zf.read("vectors/embeddings.bin")
            return None

    def read_media_index(self) -> Optional[UKAMediaIndex]:
        """Read multimodal media index with transcripts and OCR."""
        with zipfile.ZipFile(self.path, "r") as zf:
            if "media/index.json" in zf.namelist():
                raw = zf.read("media/index.json").decode("utf-8")
                return UKAMediaIndex.model_validate_json(raw)
            return None

    def get_media_bytes(self, filename: str) -> bytes:
        """Stream raw binary media asset bytes on demand."""
        target = f"media/{filename}" if not filename.startswith("media/") else filename
        with zipfile.ZipFile(self.path, "r") as zf:
            if target not in zf.namelist():
                raise FileNotFoundError(f"Media asset not found in bundle: {target}")
            return zf.read(target)

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """
        Cryptographically verify all files against SHA-256 hashes in manifest.
        Returns (is_valid, list_of_errors).
        """
        manifest = self.read_manifest()
        errors: list[str] = []

        with zipfile.ZipFile(self.path, "r") as zf:
            for rel_path, expected_hash in manifest.content_hashes.items():
                if rel_path not in zf.namelist():
                    errors.append(f"Missing declared file: {rel_path}")
                    continue

                actual_bytes = zf.read(rel_path)
                actual_hash = f"sha256:{hashlib.sha256(actual_bytes).hexdigest()}"
                if actual_hash != expected_hash:
                    errors.append(
                        f"Checksum mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}"
                    )

        return (len(errors) == 0, errors)

    def to_bundle_data(self) -> UKABundleData:
        """Extract and reconstruct full in-memory UKABundleData."""
        manifest = self.read_manifest()
        context_md = self.read_context_markdown()
        schema_yaml = self.read_ontology()
        messages = self.read_messages()
        distilled_memory = self.read_distilled_memory()
        subgraph = self.read_subgraph()
        chunks = self.read_vector_chunks()
        embeddings_bin = self.read_embeddings_bin()
        media_index = self.read_media_index()

        media_files: dict[str, bytes] = {}
        with zipfile.ZipFile(self.path, "r") as zf:
            for name in zf.namelist():
                if name.startswith("media/") and name != "media/index.json":
                    fname = name.replace("media/", "", 1)
                    media_files[fname] = zf.read(name)

        return UKABundleData(
            manifest=manifest,
            context_md=context_md,
            schema_yaml=schema_yaml,
            messages=messages,
            distilled_memory=distilled_memory,
            subgraph=subgraph,
            vector_chunks=chunks,
            media_index=media_index,
            media_files=media_files,
            embeddings_bin=embeddings_bin,
        )
