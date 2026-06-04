"""MCP tool server — exposes ToolRegistry tools via the MCP JSON-RPC protocol."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _openai_to_mcp_schema(openai_schema: dict) -> dict:
    """Convert OpenAI function-calling schema to MCP tool format."""
    fn = openai_schema.get("function", openai_schema)
    return {
        "name": fn.get("name", ""),
        "description": fn.get("description", ""),
        "inputSchema": fn.get("parameters", {"type": "object", "properties": {}}),
    }


@dataclass
class MCPServer:
    """MCP-compatible tool server backed by ToolRegistry."""

    tool_registry: Any  # ToolRegistry instance from tools.py
    server_name: str = "monster-resort-concierge"
    server_version: str = "1.0.0"

    def list_tools(self) -> List[dict]:
        """Return all registered tools in MCP format."""
        mcp_tools = []
        for tool in self.tool_registry.list():
            schema = tool.to_openai_schema()
            if schema:
                mcp_tools.append(_openai_to_mcp_schema(schema))
        return mcp_tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> dict:
        """Execute a tool by name and return structured MCP result."""
        request_id = str(uuid.uuid4())[:8]
        tool = self.tool_registry.get(name)

        if not tool:
            logger.warning(
                "mcp_unknown_tool",
                extra={"tool": name, "request_id": request_id},
            )
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                "isError": True,
            }

        t0 = time.perf_counter()
        try:
            result = await self.tool_registry.async_execute_with_timing(
                name, request_id=request_id, **arguments
            )
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)

            logger.info(
                "mcp_tool_call_ok",
                extra={
                    "tool": name,
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                },
            )

            # Return structured content — no double-serialization
            return {
                "content": [{"type": "json", "json": result}],
                "isError": False,
            }

        except Exception as exc:
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.error(
                "mcp_tool_call_failed",
                extra={
                    "tool": name,
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                    "error_type": type(exc).__name__,
                },
            )
            # Structured error — no raw exception message leaked to client
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Tool '{name}' failed. Request ID: {request_id}",
                    }
                ],
                "isError": True,
            }

    async def handle_jsonrpc(self, request: dict) -> dict:
        """Dispatch a single MCP JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": self.server_name,
                        "version": self.server_version,
                    },
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.list_tools()},
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = await self.call_tool(tool_name, arguments)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    def get_server_info(self) -> dict:
        """Return server metadata for discovery endpoints."""
        tools = self.list_tools()
        return {
            "name": self.server_name,
            "version": self.server_version,
            "protocol": "MCP",
            "protocolVersion": "2024-11-05",
            "tools": [t["name"] for t in tools],
            "tool_count": len(tools),
            "description": "Monster Game Resort Concierge tool server — "
            "book rooms, retrieve bookings, search resort amenities.",
        }
