from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from ..config import Config

class LLMClient:
    def __init__(self):
        # Use local embeddings (all-MiniLM-L6-v2) to avoid API 404/quota issues
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=Config.GOOGLE_API_KEY,
            temperature=0
        )

    def get_embedding(self, text: str):
        return self.embeddings.embed_query(text)
    
    def get_embeddings_batch(self, texts: list):
        return self.embeddings.embed_documents(texts)
