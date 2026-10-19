"""
Universal Knowledge Artifact (UKA) Core Package.

Open, vendor-agnostic container standard (.uka) for portable multimodal
conversational contexts, knowledge subgraphs, and vector embeddings.
"""

__version__ = "0.1.0"

from uka.models import (
    UKABundleData,
    UKADistilledMemory,
    UKAGraphEdge,
    UKAGraphNode,
    UKAManifest,
    UKAMediaAsset,
    UKAMediaIndex,
    UKAMessage,
    UKASubgraph,
    UKAVectorChunk,
)
from uka.bundle_writer import UKABundleWriter, compute_sha256
from uka.bundle_reader import UKABundleReader
from uka.importer import UKAImporter
from uka.adapters import (
    BaseAdapter,
    BaseHarvester,
    ClaudeWebAdapter,
    ClaudeWebHarvester,
    CursorAdapter,
    CursorHarvester,
    GenericMarkdownAdapter,
    GenericMarkdownHarvester,
)

__all__ = [
    "UKABundleData",
    "UKADistilledMemory",
    "UKAGraphEdge",
    "UKAGraphNode",
    "UKAManifest",
    "UKAMediaAsset",
    "UKAMediaIndex",
    "UKAMessage",
    "UKASubgraph",
    "UKAVectorChunk",
    "UKABundleWriter",
    "UKABundleReader",
    "UKAImporter",
    "compute_sha256",
    "BaseAdapter",
    "BaseHarvester",
    "ClaudeWebAdapter",
    "ClaudeWebHarvester",
    "CursorAdapter",
    "CursorHarvester",
    "GenericMarkdownAdapter",
    "GenericMarkdownHarvester",
]
