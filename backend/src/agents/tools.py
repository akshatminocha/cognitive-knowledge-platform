from langchain_core.tools import Tool
from ..storage.vector import VectorStore
from ..storage.graph import GraphStore
from ..utils.llm_client import LLMClient

class AgentTools:
    def __init__(self):
        self.vector_store = VectorStore()
        self.graph_store = GraphStore()
        self.llm_client = LLMClient()

    def vector_search(self, query: str) -> str:
        """
        Useful for answering questions about policies, technical documentation, 
        and general knowledge from unstructured text.
        """
        try:
            embedding = self.llm_client.get_embedding(query)
            results = self.vector_store.similarity_search(embedding, k=3)
            
            if not results:
                return "No relevant documents found."
            
            formatted_results = "\n".join(
                [f"Chunk: {r.get('text', '')}\nMetadata: {r.get('metadata', '')}" for r in results]
            )
            return formatted_results
        except Exception as e:
            return f"Error during vector search: {str(e)}"

    def graph_search(self, query: str) -> str:
        """
        Useful for answering questions about relationships, such as:
        - Who works in which department?
        - Which products belong to which category?
        - What is the price of a product?
        """
        # In a real scenario, this would generate Cypher. 
        # For this demo, we can try to extract entities or run a generic search.
        # Let's assume we want to find Product details.
        
        try:
            # Simple keyword search fallback for demo if we don't have text-to-cypher
            # Or text-to-cypher using LLM
            prompt = f"Convert the following natural language query to a Cypher query for Neo4j. The graph has nodes: Product(id, name, price, description) and Category(id, name). Relationship: (Product)-[:BELONGS_TO]->(Category). Query: {query}. Return ONLY the Cypher query string."
            
            cypher_candidate = self.llm_client.llm.invoke(prompt).content.strip()
            # Safety cleanup (remove markdown code blocks if any)
            cypher_candidate = cypher_candidate.replace("```cypher", "").replace("```", "").strip()
            
            if not results:
                 return "No graph results found."
            return str(results)

        except Exception as e:
            return f"Error during graph search: {str(e)}"

    def system_details(self, query: str) -> str:
        """
        Useful for answering questions about the overall system, such as:
        - What files/documents/data sources are ingested?
        - What kind of data is stored and how?
        - Explain the architecture of the knowledge base.
        Always pass the string "all" as the query argument.
        """
        try:
            vector_files = self.vector_store.list_sources()
            graph_stats = self.graph_store.get_stats()
            
            report = []
            report.append("### Universal Knowledge Intelligence Platform Overview")
            report.append("The system is designed to handle heterogeneous data sources using a sophisticated **Dual Knowledge Representation Architecture**.")
            
            report.append("\n#### 1. Unstructured Data Layer (Vector Database)")
            report.append("- **Storage Mechanism**: MongoDB Document Store with embedded vectors.")
            report.append("- **Purpose**: Used for semantic similarity mapping. It ingests unstructured text (PDFs, Markdown, TXT), chunks it intelligently, embedding each chunk so the agent can find answers contextually.")
            if vector_files:
                report.append(f"- **Ingested Files**: {', '.join(vector_files)}")
            else:
                report.append("- **Ingested Files**: (None currently ingested)")
                
            report.append("\n#### 2. Structured Data Layer (Graph Database)")
            report.append("- **Storage Mechanism**: Neo4j Graph Database.")
            report.append("- **Purpose**: Used for ontological mapping and relationship reasoning. It ingests flat structured files (CSV, SQL schemas) and builds semantic maps mapping entities to each other.")
            report.append(f"- **Current Graph Scope**: {graph_stats.get('nodes', 0)} active nodes and {graph_stats.get('relationships', 0)} relationships defined.")
            
            report.append("\n**Conclusion**: This hybrid approach ensures Agentic AI systems can verify and validate grounded answers not just from flat text search, but across structured interconnected metadata.")
            return "\n".join(report)
        except Exception as e:
            return f"Error compiling system details: {str(e)}"

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="VectorStore",
                func=self.vector_search,
                description="Search for policies, documents, and unstructured text."
            ),
            Tool(
                name="GraphStore",
                func=self.graph_search,
                description="Search for structured relationships (products, categories, employees)."
            ),
            Tool(
                name="SystemDetails",
                func=self.system_details,
                description="Use this tool to explain the knowledge base generation process, what files are in the system, how data is stored, and its overall architecture. Input should be the string 'all'."
            )
        ]
