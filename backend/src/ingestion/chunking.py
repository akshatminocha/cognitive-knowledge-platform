from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

class IntelligentChunker:
    """Handles semantic and structure-aware chunking."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""]
        )

    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """Chunks a list of documents using recursive character splitting."""
        return self.text_splitter.split_documents(documents)

    def chunk_structured_data(self, data: List[dict], content_keys: List[str]) -> List[Document]:
        """
        Converts structured data rows into semantic documents.
        Each row becomes a document, with specified keys forming the content.
        """
        docs = []
        for row in data:
            content_parts = [f"{key}: {row.get(key, '')}" for key in content_keys if key in row]
            page_content = "\n".join(content_parts)
            metadata = {k: v for k, v in row.items() if k not in content_keys}
            docs.append(Document(page_content=page_content, metadata=metadata))
        return docs
