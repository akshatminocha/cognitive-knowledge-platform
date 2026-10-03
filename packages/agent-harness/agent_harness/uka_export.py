"""
Universal Knowledge Artifact (UKA) Exporter

Packages session context, memory, extracted knowledge, and multi-modal assets
into a portable, vendor-agnostic file format (.uka).
This solves "knowledge lock-in" by allowing a single context bundle to be 
passed to any LLM (OpenAI, Anthropic, Gemini, etc.) or moved between systems.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from datetime import datetime, timezone

from .context_engine import ContextEngine


class UKAExporter:
    """Exports session and knowledge data to a Universal Knowledge Artifact."""

    def __init__(self, context_engine: ContextEngine):
        self.context_engine = context_engine

    def export_to_json(self, session_id: str, output_path: Path) -> Path:
        """
        Export the session as a single .json UKA file.
        Useful for text-only context transfer.
        """
        session_data = self._gather_session_data(session_id)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)
            
        return output_path

    def export_to_bundle(self, session_id: str, output_path: Path) -> Path:
        """
        Export the session as a bundled .uka (ZIP) file.
        Supports multi-modal assets (images, audio) alongside text context.
        """
        session_data = self._gather_session_data(session_id)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as uka_zip:
            # 1. Write metadata and main context
            uka_zip.writestr(
                "manifest.json", 
                json.dumps(session_data["metadata"], indent=2)
            )
            
            # 2. Write chat history
            uka_zip.writestr(
                "chat_history.json",
                json.dumps(session_data["messages"], indent=2)
            )
            
            # 3. Write unified context as Markdown (easy for LLMs to read)
            markdown_context = self._generate_markdown_context(session_data)
            uka_zip.writestr("context.md", markdown_context)
            
            # Future: Loop through session_data["messages"] to extract base64 multi-modal
            # assets, save them to a /media folder in the zip, and replace references in markdown.

        return output_path

    def _gather_session_data(self, session_id: str) -> dict:
        """Gathers all relevant data for a session."""
        session = self.context_engine.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found.")

        # Serialize messages to dictionaries
        messages = [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
            }
            for msg in session.messages
        ]

        return {
            "metadata": {
                "version": "1.0.0",
                "export_date": datetime.now(timezone.utc).isoformat(),
                "session_id": session.id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "format": "Universal Knowledge Artifact (UKA)"
            },
            "summary": getattr(session, "summary", "No summary available."),
            "messages": messages,
            # Future: Inject Neo4j Graph context or Vector DB summaries here
            "extracted_knowledge": [] 
        }

    def _generate_markdown_context(self, session_data: dict) -> str:
        """Generates a human- and LLM-readable Markdown string of the context."""
        md = [
            f"# Universal Knowledge Artifact: {session_data['metadata']['session_id']}",
            f"**Exported:** {session_data['metadata']['export_date']}",
            f"**Version:** {session_data['metadata']['version']}",
            "",
            "## Summary",
            session_data["summary"],
            "",
            "## Conversation History"
        ]

        for msg in session_data["messages"]:
            role = str(msg["role"]).upper()
            md.append(f"### {role}")
            md.append(msg["content"])
            md.append("")

        return "\n".join(md)
