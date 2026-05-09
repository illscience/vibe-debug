from __future__ import annotations

import unittest
from typing import Any

from vibe_debug.mcp_server import MCPDebuggerServer


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def set_breakpoints(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ok": True}


class FakeManager:
    def __init__(self) -> None:
        self.session = FakeSession()

    def get(self, session_id: str) -> FakeSession:
        return self.session


class MCPServerTests(unittest.TestCase):
    def test_initialize_and_tool_list(self) -> None:
        server = MCPDebuggerServer()

        initialize = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        self.assertEqual(initialize["result"]["serverInfo"]["name"], "vibe-debug")

        listed = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertIn("debug_guidance", tools)
        self.assertIn("debug_python_repro", tools)
        self.assertIn("debug_launch", tools)
        self.assertIn("debug_set_breakpoints", tools)
        self.assertIn("debug_step", tools)
        self.assertIn("debug_variables", tools)

        set_breakpoints = next(tool for tool in listed["result"]["tools"] if tool["name"] == "debug_set_breakpoints")
        entries = set_breakpoints["inputSchema"]["properties"]["entries"]
        self.assertEqual(entries["items"]["properties"]["logMessage"]["type"], "string")

    def test_debug_set_breakpoints_accepts_logpoint_entries(self) -> None:
        server = MCPDebuggerServer()
        manager = FakeManager()
        server.manager = manager  # type: ignore[assignment]

        result = server._debug_set_breakpoints(
            {
                "sessionId": "session-1",
                "file": "sample.py",
                "entries": [{"line": 5, "logMessage": "x={x}"}],
            }
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            manager.session.calls,
            [
                {
                    "file": "sample.py",
                    "lines": [5],
                    "cwd": None,
                    "conditions": [None],
                    "hit_conditions": [None],
                    "log_messages": ["x={x}"],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
