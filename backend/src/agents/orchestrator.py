from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage
from .tools import AgentTools
from ..utils.llm_client import LLMClient

class KnowledgeAgent:
    def __init__(self):
        self.llm_client = LLMClient()
        self.tools_provider = AgentTools()
        self.tools = self.tools_provider.get_tools()
        
        # Define System Prompt
        system_prompt = """You are a Universal Knowledge Intelligence Assistant.
Your goal is to answer the user's question using ONLY the information retrieved from the provided tools.

1.  **Analyze the Request**: 
    *   **ALWAYS** use the 'SystemDetails' tool if the user asks about "files", "documents", "data sources", "purpose", "how is data stored", "system overview", or "what is in the database".
    *   Use 'VectorStore' for searching specific topics within the content.
    *   Use 'GraphStore' for searching relationships.
2.  **Retrieve Information**: Use the appropriate tool(s).
3.  **Synthesize Answer**:
    *   Answer based *strictly* on retrieved context.
    *   If information is missing, state it clearly.
    *   DO NOT hallucinate.
"""
        
        # Create LangGraph Agent
        # state_modifier allows injecting the system prompt
        self.agent_executor = create_react_agent(
            self.llm_client.llm, 
            self.tools,
            prompt=system_prompt
        )

    def ask(self, query: str):
        """
        Invokes the agent and processes the output to return a standardized format.
        """
        # LangGraph invocation
        response = self.agent_executor.invoke({"messages": [("user", query)]})
        
        # Extract Final Answer
        # The last message is usually the AI's final response
        final_message = response["messages"][-1]
        
        # FIX: Handle case where content is a list of blocks (Gemini/LangChain behavior)
        if isinstance(final_message.content, list):
            texts = []
            for block in final_message.content:
                if isinstance(block, str):
                    texts.append(block)
                elif isinstance(block, dict):
                    if 'text' in block:
                        texts.append(block['text'])
                elif hasattr(block, 'text'):
                    texts.append(block.text)
                else:
                    texts.append(str(block))
            output_text = " ".join(texts)
        else:
            output_text = final_message.content

        # Extract Tool Usage
        # Iterate through messages to find ToolMessages (results) or AIMessages with tool_calls
        tool_usage = []
        for msg in response["messages"]:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_usage.append(tool_call.get('name'))
        
        return {
            "output": output_text,
            "tool_usage": tool_usage
        }
