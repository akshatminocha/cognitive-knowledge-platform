import pymongo
from typing import List, Dict, Any
from langchain_core.documents import Document
from ..config import Config

class VectorStore:
    def __init__(self):
        self.client = pymongo.MongoClient(Config.MONGO_URI)
        self.db = self.client[Config.MONGO_DB_NAME]
        self.collection = self.db[Config.MONGO_COLLECTION_NAME]
        
        # Create vector index if not exists (Atlas Search specific, simulating local via generic index or just placeholder)
        # Note: Local Mongo doesn't support Atlas Vector Search out of the box without Atlas. 
        # We will use a basic collection for storage and standard query for now, 
        # or mock the vector search behavior if running locally.
        
    def add_documents(self, documents: List[Document], embeddings: List[List[float]]):
        """Stores documents and their embeddings."""
        data = []
        for doc, emb in zip(documents, embeddings):
            record = {
                "text": doc.page_content,
                "embedding": emb,
                "metadata": doc.metadata
            }
            data.append(record)
        
        if data:
            self.collection.insert_many(data)
            print(f"Inserted {len(data)} documents into MongoDB.")

    def similarity_search(self, query_embedding: List[float], k: int = 5) -> List[Dict[str, Any]]:
        """
        Performs a vector search. 
        NOTE: On local MongoDB Community, true vector search isn't native like Atlas.
        This is a placeholder that would normally use the $vectorSearch aggregation pipeline.
        For local demo, we might just return latest or random if we can't compute cosine sim in Mongo.
        """
        # Production (Atlas) Implementation:
        # pipeline = [
        #     {
        #         "$vectorSearch": {
        #             "index": "vector_index",
        #             "queryVector": query_embedding,
        #             "path": "embedding",
        #             "numCandidates": k * 10,
        #             "limit": k
        #         }
        #     }
        # ]
        # return list(self.collection.aggregate(pipeline))
        
        # Local Fallback (Just fetch recent for demo purposes since we don't have Atlas Local)
        # In a real local setup, we'd use Qdrant or Chroma, but requirement was Mongo.
        return list(self.collection.find().limit(k))

    def list_sources(self) -> List[str]:
        """
        Lists all unique source files ingested into the vector store.
        """
        try:
            return self.collection.distinct("metadata.source")
        except Exception as e:
            print(f"Error listing sources: {e}")
            return []
