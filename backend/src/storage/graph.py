from neo4j import GraphDatabase
from typing import List, Dict, Any
from ..config import Config

class GraphStore:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            Config.NEO4J_URI, 
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
        )

    def close(self):
        self.driver.close()

    def add_entity(self, label: str, properties: Dict[str, Any]):
        """Adds a node to the graph."""
        query = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
        # Ensure 'id' exists in props or generate one
        if 'id' not in properties:
             # Basic fallback if id not provided, use name or something unique
             properties['id'] = properties.get('name', str(hash(str(properties))))
             
        with self.driver.session() as session:
            session.run(query, id=properties['id'], props=properties)

    def add_relationship(self, source_label: str, source_id: str, 
                         target_label: str, target_id: str, 
                         relation_type: str, properties: Dict[str, Any] = {}):
        """Adds a relationship between two nodes."""
        query = f"""
        MATCH (a:{source_label} {{id: $source_id}})
        MATCH (b:{target_label} {{id: $target_id}})
        MERGE (a)-[r:{relation_type}]->(b)
        SET r += $props
        """
        with self.driver.session() as session:
            session.run(query, source_id=source_id, target_id=target_id, props=properties)

    def query_graph(self, cypher_query: str, parameters: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            result = session.run(cypher_query, parameters)
            return [record.data() for record in result]

    def get_stats(self) -> Dict[str, Any]:
        """Returns basic statistics about the graph."""
        try:
            nodes_query = "MATCH (n) RETURN count(n) as count"
            rels_query = "MATCH ()-[r]->() RETURN count(r) as count"
            
            with self.driver.session() as session:
                nodes_res = session.run(nodes_query).single()
                rels_res = session.run(rels_query).single()
                
                return {
                    "nodes": nodes_res["count"] if nodes_res else 0,
                    "relationships": rels_res["count"] if rels_res else 0
                }
        except Exception as e:
            print(f"Error getting graph stats: {e}")
            return {"nodes": 0, "relationships": 0}
