import os
import pandas as pd
from typing import List, Dict, Any
from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredMarkdownLoader
from langchain_core.documents import Document

class DocumentParser:
    """Handles parsing of unstructured documents (PDF, TXT, MD)."""
    
    @staticmethod
    def parse_pdf(filepath: str) -> List[Document]:
        loader = PyPDFLoader(filepath)
        return loader.load()

    @staticmethod
    def parse_text(filepath: str) -> List[Document]:
        loader = TextLoader(filepath)
        return loader.load()

    @staticmethod
    def parse_markdown(filepath: str) -> List[Document]:
        loader = UnstructuredMarkdownLoader(filepath)
        return loader.load()

class StructuredParser:
    """Handles parsing of structured data (CSV, Excel)."""
    
    @staticmethod
    def parse_csv(filepath: str) -> List[Dict[str, Any]]:
        df = pd.read_csv(filepath)
        return df.to_dict(orient='records')

    @staticmethod
    def parse_excel(filepath: str) -> List[Dict[str, Any]]:
        df = pd.read_excel(filepath)
        return df.to_dict(orient='records')

class DataIngestionFactory:
    """Factory to select the appropriate parser based on file extension."""
    
    @staticmethod
    def get_parser(filepath: str):
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.pdf':
            return DocumentParser.parse_pdf
        elif ext == '.txt':
            return DocumentParser.parse_text
        elif ext == '.md':
            return DocumentParser.parse_markdown
        elif ext == '.csv':
            return StructuredParser.parse_csv
        elif ext in ['.xls', '.xlsx']:
            return StructuredParser.parse_excel
        else:
            raise ValueError(f"Unsupported file type: {ext}")
