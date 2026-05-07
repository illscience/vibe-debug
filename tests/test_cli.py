from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from mcp_debugger.cli import _format_claude_stream, main


def call_cli(args: list[str]) -> tuple[int, str]:
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = main(args)
    return code, stdout.getvalue()


class CLITests(unittest.TestCase):
    def test_demo_project_writes_claude_memory_and_bug(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, output = call_cli(["demo-project", directory, "--target", "claude"])

            self.assertEqual(code, 0)
            root = Path(directory)
            self.assertTrue((root / "CLAUDE.md").exists())
            self.assertTrue((root / "buggy_invoice.py").exists())
            self.assertIn("debug_python_repro", (root / "CLAUDE.md").read_text())
            self.assertIn("actual_total", (root / "buggy_invoice.py").read_text())
            payload = json.loads(output)
            self.assertEqual(payload["created"], ["CLAUDE.md", "buggy_invoice.py"])
            self.assertIn("claude -p", payload["next"][0])

    def test_init_agent_files_can_target_both_agents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, output = call_cli(["init-agent-files", "--directory", directory, "--target", "both"])

            self.assertEqual(code, 0)
            root = Path(directory)
            self.assertTrue((root / "CLAUDE.md").exists())
            self.assertTrue((root / "AGENTS.md").exists())
            payload = json.loads(output)
            self.assertEqual(len(payload["written"]), 2)

    def test_claude_install_snippet_uses_user_scope(self) -> None:
        code, output = call_cli(["install-snippet", "claude"])

        self.assertEqual(code, 0)
        self.assertIn("claude mcp add -s user mcp-debugger", output)
        self.assertIn("npx -y github:illscience/mcp-debugger", output)

    def test_codex_install_snippet_uses_npx(self) -> None:
        code, output = call_cli(["install-snippet", "codex"])

        self.assertEqual(code, 0)
        self.assertIn("codex mcp add mcp_debugger", output)
        self.assertIn("npx -y github:illscience/mcp-debugger", output)

    def test_claude_progress_formats_debugger_events(self) -> None:
        events = [
            {
                "type": "system",
                "subtype": "init",
                "cwd": "/tmp/demo",
                "mcp_servers": [{"name": "mcp-debugger", "status": "connected"}],
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "mcp__mcp-debugger__debug_python_repro",
                            "input": {"program": "/tmp/demo/buggy_invoice.py"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-1",
                            "content": json.dumps(
                                {
                                    "stopped": {
                                        "location": {
                                            "name": "invoice_total",
                                            "line": 13,
                                            "source": {"path": "/tmp/demo/buggy_invoice.py"},
                                        }
                                    },
                                    "snapshot": {
                                        "locals": [
                                            {"name": "subtotal", "value": "120.0"},
                                            {"name": "rate", "value": "0.15"},
                                            {"name": "total", "value": "119.85"},
                                        ]
                                    },
                                }
                            ),
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-2",
                            "name": "mcp__mcp-debugger__debug_evaluate",
                            "input": {"expression": "subtotal * (1 - rate)"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-2",
                            "content": json.dumps(
                                {
                                    "expression": "subtotal * (1 - rate)",
                                    "result": "102.0",
                                }
                            ),
                        }
                    ]
                },
            },
        ]
        input_stream = StringIO("\n".join(json.dumps(event) for event in events))
        output_stream = StringIO()

        self.assertEqual(_format_claude_stream(input_stream, output_stream), 0)
        output = output_stream.getvalue()
        self.assertIn("MCP: mcp-debugger connected", output)
        self.assertIn("Tool: mcp-debugger.debug_python_repro (buggy_invoice.py)", output)
        self.assertIn("Stopped: buggy_invoice.py:13 in invoice_total", output)
        self.assertIn("Locals: subtotal=120.0 rate=0.15 total=119.85", output)
        self.assertIn("Eval: subtotal * (1 - rate) -> 102.0", output)

    def test_claude_progress_treats_pending_mcp_as_starting_until_tool_use(self) -> None:
        events = [
            {
                "type": "system",
                "subtype": "init",
                "cwd": "/tmp/demo",
                "mcp_servers": [{"name": "mcp-debugger", "status": "pending"}],
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "mcp__mcp-debugger__debug_python_repro",
                            "input": {"program": "/tmp/demo/buggy_invoice.py"},
                        }
                    ]
                },
            },
        ]
        input_stream = StringIO("\n".join(json.dumps(event) for event in events))
        output_stream = StringIO()

        self.assertEqual(_format_claude_stream(input_stream, output_stream), 0)
        output = output_stream.getvalue()
        self.assertIn("MCP: mcp-debugger starting", output)
        self.assertIn("MCP: mcp-debugger active", output)
        self.assertNotIn("MCP: mcp-debugger pending", output)

    def test_claude_progress_suppresses_transient_retried_tool_error(self) -> None:
        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "mcp__mcp-debugger__debug_evaluate",
                            "input": {"expression": "subtotal * (1 - rate)"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-1",
                            "is_error": True,
                            "content": json.dumps({"error": "NameError: name 'subtotal' is not defined"}),
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-2",
                            "name": "mcp__mcp-debugger__debug_evaluate",
                            "input": {"expression": "subtotal * (1 - rate)", "frameId": 2},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-2",
                            "content": json.dumps({"expression": "subtotal * (1 - rate)", "result": "102.0"}),
                        }
                    ]
                },
            },
        ]
        input_stream = StringIO("\n".join(json.dumps(event) for event in events))
        output_stream = StringIO()

        self.assertEqual(_format_claude_stream(input_stream, output_stream), 0)
        output = output_stream.getvalue()
        self.assertNotIn("Tool error", output)
        self.assertIn("Eval: subtotal * (1 - rate) -> 102.0", output)


if __name__ == "__main__":
    unittest.main()
