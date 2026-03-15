import json
import subprocess
import os
import asyncio
import httpx # type: ignore
from typing import Optional, Dict, List, Any

class MCPClient:
    """
    A lightweight, zero-dependency JSON-RPC client for Model Context Protocol (MCP).
    Compatible with Python 3.9+.
    """
    def __init__(self, command: str, args: list, env: Optional[Dict[str, str]] = None, label: str = "mcp_server"):
        self.command = command
        self.args = args
        self.env = env or {}
        self.label = label
        self.process: Any = None
        self._message_id = 0
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._tools_cache: List[Dict[str, Any]] = []
        self._is_initialized = False

    async def start(self):
        """Starts the MCP server process."""
        env = os.environ.copy()
        env.update(self.env)
        
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.command, *self.args,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                limit=1024 * 1024 * 5 # 5MB limit for large JSON schemas
            )
            # Start background reader
            asyncio.create_task(self._read_stdout())
            asyncio.create_task(self._read_stderr())
            
            await self._initialize()
            self._is_initialized = True
            
            # Fetch tools immediately after init
            await self.fetch_tools()
            
        except Exception as e:
            print(f"[MCP {self.label}] Failed to start: {e}")
            self.process = None

    async def stop(self):
        """Terminates the MCP server."""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self.process.kill()

    def _get_next_id(self):
        self._message_id += 1
        return self._message_id

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: # type: ignore
        if not self.process or self.process.returncode is not None:
            raise RuntimeError(f"MCP Server {self.label} is not running.")
            
        msg_id = str(self._get_next_id())
        message: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method
        }
        if params is not None:
            message["params"] = params
            
        future = asyncio.Future()
        self._pending_requests[msg_id] = future
        
        raw_msg = json.dumps(message) + "\n"
        if self.process and self.process.stdin:
            self.process.stdin.write(raw_msg.encode('utf-8'))
            await self.process.stdin.drain()
        
        try:
            # Wait with timeout
            response = await asyncio.wait_for(future, timeout=15.0)
            if "error" in response:
                raise RuntimeError(f"MCP RPC Error: {response['error']}")
            return response.get("result", {})
        finally:
            self._pending_requests.pop(msg_id, None)

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        if not self.process or self.process.returncode is not None:
            return
            
        message: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params is not None:
            message["params"] = params
            
        raw_msg = json.dumps(message) + "\n"
        if self.process and self.process.stdin:
            self.process.stdin.write(raw_msg.encode('utf-8'))
            await self.process.stdin.drain()

    async def _read_stdout(self):
        """Reads JSON-RPC messages from stdout line by line."""
        while self.process and self.process.returncode is None and self.process.stdout:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                
                try:
                    data = json.loads(line.decode('utf-8').strip())
                except json.JSONDecodeError:
                    continue # Ignore malformed lines (often debug logs)
                    
                msg_id = str(data.get("id"))
                if msg_id in self._pending_requests:
                    if not self._pending_requests[msg_id].done():
                        self._pending_requests[msg_id].set_result(data)
                        
            except Exception as e:
                print(f"[MCP {self.label}] Read error: {e}")
                break

    async def _read_stderr(self):
        """Reads stderr for debugging."""
        while self.process and self.process.returncode is None and self.process.stderr:
            line = await self.process.stderr.readline()
            if not line:
                break
            # print(f"[MCP {self.label} STDERR]", line.decode('utf-8').strip(), file=sys.stderr)

    async def _initialize(self):
        """Performs the MCP handshake."""
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "LocalLLMBot",
                "version": "1.0.0"
            }
        })
        await self._send_notification("notifications/initialized")
        return result

    async def fetch_tools(self) -> list:
        """Fetches available tools from the MCP server."""
        if not self._is_initialized:
            return []
            
        result = await self._send_request("tools/list")
        self._tools_cache = result.get("tools", [])
        return self._tools_cache

    async def call_tool(self, name: str, arguments: dict) -> list:
        """Calls a specific tool and returns the response content."""
        if not self._is_initialized:
            raise RuntimeError("MCP Client not initialized")
            
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        return result.get("content", [])

    def get_openai_tools_schema(self) -> list:
        """Converts cached MCP tools to OpenAI's tools array format."""
        openai_tools = []
        for tool in self._tools_cache:
            # MCP inputSchema is generally standard JSON Schema
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {})
                }
            })
        return openai_tools


class MCPSSEClient(MCPClient):
    """
    An MCP Client that connects over HTTP POST for remote endpoints like Exa.
    Many remote MCPs just accept JSON-RPC via HTTP POST and return an SSE-formatted response.
    """
    def __init__(self, url: str, label: str = "mcp_server"):
        super().__init__("", [], {}, label)
        self.url = url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def start(self):
        try:
            self.process = True # Mock process to pass base class checks
            await self._initialize()
            self._is_initialized = True
            await self.fetch_tools()
        except Exception as e:
            print(f"[MCP HTTP {self.label}] Failed to start: {e}")
            self.process = None

    async def stop(self):
        await self.client.aclose()
        self.process = None

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        msg_id = str(self._get_next_id())
        message: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method
        }
        if params is not None:
            message["params"] = params
            
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json"
        }
        
        response = await self.client.post(self.url, json=message, headers=headers)
        response.raise_for_status()
        
        # Parse SSE response text
        for line in response.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
                try:
                    result = json.loads(data_str)
                    if "error" in result:
                        raise RuntimeError(f"MCP RPC Error: {result['error']}")
                    return result.get("result", {})
                except json.JSONDecodeError:
                    pass
        raise RuntimeError(f"Failed to parse MCP response: {response.text}")

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        message: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params is not None:
            message["params"] = params
            
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json"
        }
        await self.client.post(self.url, json=message, headers=headers)


class MCPManager:
    """Manages multiple MCP clients loaded from mcp.json."""
    def __init__(self, mcp_json_path: str):
        self.mcp_json_path = os.path.expanduser(mcp_json_path)
        self.clients: Dict[str, Any] = {} # label -> MCPClient
        
    async def load_and_start_all(self):
        """Reads mcp.json and starts all servers."""
        if not os.path.exists(self.mcp_json_path):
            print(f"No mcp.json found at {self.mcp_json_path}")
            return
            
        try:
            with open(self.mcp_json_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading mcp.json: {e}")
            return
            
        servers = data.get("mcpServers", {})
        for label, config in servers.items():
            command = config.get("command")
            args = config.get("args", [])
            env = config.get("env", {})
            url = config.get("url")
            
            if command:
                client = MCPClient(command=command, args=args, env=env, label=label)
                self.clients[label] = client
                await client.start()
                print(f"[MCPManager] Started stdio server '{label}' with {len(client._tools_cache)} tools.")
            elif url:
                client = MCPSSEClient(url=url, label=label)
                self.clients[label] = client
                await client.start()
                print(f"[MCPManager] Started SSE server '{label}' with {len(client._tools_cache)} tools.")

    async def stop_all(self):
        for client in self.clients.values():
            await client.stop()

    def get_all_openai_tools(self) -> list:
        """Aggregates all tools from all running MCP servers into a single OpenAI tools array."""
        all_tools = []
        for client in self.clients.values():
            all_tools.extend(client.get_openai_tools_schema())
        return all_tools

    async def execute_tool_call(self, name: str, arguments: dict):
        """Finds the server that owns the tool and executes it."""
        # Find which client has this tool
        target_client = None
        for client in self.clients.values():
            for tool in client._tools_cache:
                if tool.get("name") == name:
                    target_client = client
                    break
            if target_client:
                break
                
        if not target_client:
            return f"Error: Tool '{name}' not found in any running MCP server."
            
        try:
            content = await target_client.call_tool(name, arguments) # type: ignore
            # Content is usually an array of objects: [{"type": "text", "text": "..."}]
            text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
            return "\\n".join(text_parts)
        except Exception as e:
            return f"Error executing tool '{name}': {e}"

# Global instance initialization hook
mcp_manager = None
async def init_mcp(mcp_json_path="~/.lmstudio/mcp.json"):
    global mcp_manager
    mcp_manager = MCPManager(mcp_json_path)
    await mcp_manager.load_and_start_all()
    return mcp_manager
