"""
ArXiv MCP Client with OpenRouter LLM Integration
This script connects to the running arxiv-mcp-server and uses OpenRouter as the LLM backbone
"""

import asyncio
import json
import os
from typing import Any
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv


class ArxivMCPClient:
    def __init__(self, openrouter_api_key: str, model: str = "openrouter/auto"):
        """
        Initialize the ArXiv MCP Client
        
        Args:
            openrouter_api_key: Your OpenRouter API key
            model: The model to use (defaults to openrouter/auto)
        """
        self.openrouter_api_key = openrouter_api_key
        self.model = model
        self.session = None
        self.http_client = httpx.AsyncClient()
        self.conversation_history = []

    async def connect(self):
        """Connect to the arxiv-mcp-server"""
        try:
            print("Connecting to arxiv-mcp-server...")
            self.server_params = StdioServerParameters(
                command="uv",
                args=["run", "arxiv-mcp-server"]
            )

            # Enter the stdio_client context manager properly
            self._stdio_cm = stdio_client(self.server_params)
            self.read_stream, self.write_stream = await self._stdio_cm.__aenter__()

            # Initialize session WITHOUT asyncio.wait_for — it breaks anyio's cancel scopes
            self._session_cm = ClientSession(self.read_stream, self.write_stream)
            self.session = await self._session_cm.__aenter__()
            await self.session.initialize()  # <-- no wait_for wrapper

            print("✓ Connected to arxiv-mcp-server")

            tools = await self.session.list_tools()
            print(f"✓ Available tools: {len(tools.tools)}")
            for tool in tools.tools:
                print(f"  &*() {tool.name}: {tool.description}")

        except Exception as e:
            print(f"✗ Failed to connect: {e}")
            raise

    async def call_openrouter(self, user_message: str) -> str:
        """Call OpenRouter API with MCP tool context"""
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Get available tools from MCP server
        tools_list = await self.session.list_tools()
        tools_json = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                }
            }
            for tool in tools_list.tools
        ]

        # Make request to OpenRouter
        response = await self.http_client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.openrouter_api_key}",
                
            },
            json={
                "model": self.model,
                "messages": self.conversation_history,
                "tools": tools_json,
                "tool_choice": "auto",
                "temperature": 0.7,
            }
        )

        result = response.json()
        
        if response.status_code != 200:
            print(f"✗ OpenRouter error: {result}")
            return f"Error: {result.get('error', {}).get('message', 'Unknown error')}"

        # Handle tool use
        choice = result["choices"][0]
        
        if choice["finish_reason"] == "tool_calls" and "tool_calls" in choice["message"]:
            print("\n🔧 Model wants to use tools:")
            tool_results = []
            
            for tool_call in choice["message"]["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                
                print(f"  Calling: {tool_name}")
                print(f"  Args: {json.dumps(tool_args, indent=2)}")
                
                # Execute tool through MCP
                try:
                    result = await self.session.call_tool(tool_name, tool_args)
                    tool_result = result.content[0].text if result.content else "No result"
                    tool_results.append({
                        "tool_name": tool_name,
                        "result": tool_result
                    })
                    print(f"  ✓ Result: {tool_result[:200]}...")
                except Exception as e:
                    print(f"  ✗ Error: {e}")
                    tool_results.append({
                        "tool_name": tool_name,
                        "result": f"Error: {str(e)}"
                    })
            
            # Add assistant response and tool results to history
            self.conversation_history.append(choice["message"])
            self.conversation_history.append({
                "role": "user",
                "content": f"Tool results: {json.dumps(tool_results)}"
            })
            
            # Get final response
            final_response = await self.http_client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                
                },
                json={
                    "model": self.model,
                    "messages": self.conversation_history,
                    "temperature": 0.7,
                }
            )
            
            final_result = final_response.json()
            assistant_message = final_result["choices"][0]["message"]["content"]
        else:
            assistant_message = choice["message"]["content"]
        
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })
        
        return assistant_message

    async def chat(self, user_message: str) -> str:
        """Send a message and get a response"""
        print(f"\n👤 You: {user_message}")
        response = await self.call_openrouter(user_message)
        print(f"\n🤖 Assistant: {response}\n")
        return response

    async def close(self):
        """Close the connection cleanly"""
        if hasattr(self, '_session_cm'):
            await self._session_cm.__aexit__(None, None, None)
        if hasattr(self, '_stdio_cm'):
            await self._stdio_cm.__aexit__(None, None, None)
        await self.http_client.aclose()


async def main():
    """Main function to test the client"""
    # Get API key from environment
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    # if not api_key:
    #     print("✗ OPENROUTER_API_KEY environment variable not set")
    #     print("  Set it with: set OPENROUTER_API_KEY=your_key_here")
    #     return
    
    client = ArxivMCPClient(api_key, model = "tencent/hy3-preview:free")
    
    try:
        await client.connect()
        
        # Test queries
        test_queries = [
            "Search for recent papers on large language models and summarize the top 3",
            #"Find papers about attention mechanisms from 2024",
            #"What are the latest trends in transformer architectures?"
        ]
        
        for query in test_queries:
            try:
                await client.chat(query)
                await asyncio.sleep(2)  # Rate limit
            except Exception as e:
                print(f"✗ Error processing query: {e}")
                break
                
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())