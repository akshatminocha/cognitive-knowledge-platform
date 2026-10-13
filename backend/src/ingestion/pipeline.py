import os
from typing import List
from ..ingestion.loaders import DataIngestionFactory
from ..ingestion.chunking import IntelligentChunker
from ..storage.vector import VectorStore
from ..storage.graph import GraphStore
from ..utils.llm_client import LLMClient
from ..config import Config

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "../../../data")
UNSTRUCTURED_DIR = os.path.join(DATA_DIR, "unstructured")
STRUCTURED_DIR = os.path.join(DATA_DIR, "structured")

class IngestionPipeline:
    def __init__(self):
        self.chunker = IntelligentChunker()
        self.vector_store = VectorStore()
        self.graph_store = GraphStore()
        self.llm_client = LLMClient()
        
    def run(self):
        print("Starting Ingestion Pipeline...")
        self.ingest_unstructured()
        self.ingest_structured()
        print("Ingestion Complete.")

    def ingest_unstructured(self):
        print("Processing Unstructured Data...")
        if not os.path.exists(UNSTRUCTURED_DIR):
            print(f"Directory not found: {UNSTRUCTURED_DIR}")
            return

        for filename in os.listdir(UNSTRUCTURED_DIR):
            filepath = os.path.join(UNSTRUCTURED_DIR, filename)
            try:
                parser = DataIngestionFactory.get_parser(filepath)
                docs = parser(filepath)
                chunks = self.chunker.chunk_documents(docs)
                
                # Generate Embeddings
                texts = [c.page_content for c in chunks]
                embeddings = self.llm_client.get_embeddings_batch(texts)
                
                self.vector_store.add_documents(chunks, embeddings)
                print(f"Ingested {filename}: {len(chunks)} chunks.")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

    def ingest_structured(self):
        print("Processing Structured Data...")
        # Product Catalog (CSV) -> Graph
        products_path = os.path.join(STRUCTURED_DIR, "products.csv")
        if os.path.exists(products_path):
            try:
                parser = DataIngestionFactory.get_parser(products_path)
                products = parser(products_path)
                
                for product in products:
                    # Create Product Node
                    self.graph_store.add_entity("Product", {
                        "id": product.get("product_id"),
                        "name": product.get("name"),
                        "price": product.get("price"),
                        "description": product.get("description")
                    })
                    
                    # Create Category Node & Relationship
                    cat_name = product.get("category")
                    if cat_name:
                        self.graph_store.add_entity("Category", {"id": cat_name, "name": cat_name})
                        self.graph_store.add_relationship(
                            "Product", product.get("product_id"),
                            "Category", cat_name,
                            "BELONGS_TO"
                        )
                print(f"Ingested {len(products)} products into Graph.")
            except Exception as e:
                print(f"Error processing products.csv: {e}")

if __name__ == "__main__":
    pipeline = IngestionPipeline()
    pipeline.run()
