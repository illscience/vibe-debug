from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .agent_guidance import AGENT_USAGE_GUIDANCE, guidance_for_target


NPX_PACKAGE_SPEC = "github:illscience/mcp-debugger"


DEMO_BUG = """def lookup_discount_rate(customer_tier):
    rates = {
        "standard": 0.0,
        "silver": 0.10,
        "gold": 0.15,
    }
    return rates[customer_tier]


def invoice_total(subtotal, customer_tier):
    rate = lookup_discount_rate(customer_tier)
    total = subtotal - rate
    return round(total, 2)


def main():
    subtotal = 120.0
    customer_tier = "gold"
    expected_total = 102.0
    actual_total = invoice_total(subtotal, customer_tier)
    print(f"{customer_tier=} {subtotal=} {expected_total=} {actual_total=}")


if __name__ == "__main__":
    main()
"""


def _mcp_command() -> list[str]:
    command_json = os.environ.get("MCP_DEBUGGER_SERVER_COMMAND_JSON")
    if command_json:
        try:
            command = json.loads(command_json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid MCP_DEBUGGER_SERVER_COMMAND_JSON: {exc}") from exc
        if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
            raise SystemExit("MCP_DEBUGGER_SERVER_COMMAND_JSON must be a JSON array of strings.")
        return command

    command = shutil.which("mcp-debugger-server")
    if command:
        return [command]
    for directory in (Path(sys.prefix) / "bin", Path(sys.executable).parent):
        sibling = directory / "mcp-debugger-server"
        if sibling.exists():
            return [str(sibling)]
    return ["mcp-debugger-server"]


def _doctor() -> int:
    checks: list[dict[str, object]] = []

    try:
        import debugpy  # noqa: F401

        checks.append({"name": "debugpy import", "ok": True})
    except Exception as exc:
        checks.append({"name": "debugpy import", "ok": False, "error": str(exc)})

    command = _mcp_command()
    try:
        process = subprocess.run(
            command,
            input='\n'.join(
                [
                    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}',
                    '{"jsonrpc":"2.0","method":"exit","params":{}}',
                    "",
                ]
            ),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        ok = process.returncode == 0 and '"name":"mcp-debugger"' in process.stdout
        checks.append(
            {
                "name": "MCP initialize",
                "ok": ok,
                "command": command,
                "stdout": process.stdout.strip(),
                "stderr": process.stderr.strip(),
            }
        )
    except Exception as exc:
        checks.append({"name": "MCP initialize", "ok": False, "command": command, "error": str(exc)})

    report = {
        "name": "mcp-debugger",
        "version": __version__,
        "python": sys.executable,
        "checks": checks,
        "ok": all(bool(check["ok"]) for check in checks),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def _print_install(target: str) -> int:
    if target == "codex":
        print(f"codex mcp add mcp_debugger -- npx -y {NPX_PACKAGE_SPEC}")
    elif target == "claude":
        print(f"claude mcp add -s user mcp-debugger -- npx -y {NPX_PACKAGE_SPEC}")
    else:
        print(
            json.dumps(
                {
                    "mcpServers": {
                        "mcp-debugger": {
                            "command": "npx",
                            "args": ["-y", NPX_PACKAGE_SPEC],
                            "env": {},
                        }
                    }
                },
                indent=2,
            )
        )
    return 0


def _targets(value: str) -> list[str]:
    if value == "both":
        return ["claude", "codex"]
    return [value]


def _agent_filename(target: str) -> str:
    if target == "claude":
        return "CLAUDE.md"
    if target == "codex":
        return "AGENTS.md"
    raise ValueError(f"unknown target: {target}")


def _write_file(path: Path, contents: str, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists. Re-run with --force to overwrite it.")
    path.write_text(contents, encoding="utf-8")


def _init_agent_files(target: str, directory: str, force: bool) -> int:
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for item in _targets(target):
        path = root / _agent_filename(item)
        _write_file(path, guidance_for_target(item), force=force)
        written.append(str(path))

    print(json.dumps({"written": written}, indent=2))
    return 0


def _demo_prompt(target: str) -> str:
    if target == "claude":
        return 'claude -p "There is a bug in buggy_invoice.py. Figure out what is wrong and propose the fix. Do not edit files."'
    if target == "codex":
        return 'codex exec "There is a bug in buggy_invoice.py. Figure out what is wrong and propose the fix. Do not edit files."'
    return 'Ask your coding agent: There is a bug in buggy_invoice.py. Figure out what is wrong and propose the fix. Do not edit files.'


def _demo_project(target: str, directory: str, force: bool) -> int:
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    _write_file(root / "buggy_invoice.py", DEMO_BUG, force=force)

    for item in _targets(target):
        _write_file(root / _agent_filename(item), guidance_for_target(item), force=force)

    prompts = [_demo_prompt(item) for item in _targets(target)]
    print(
        json.dumps(
            {
                "project": str(root),
                "created": sorted(path.name for path in root.iterdir() if path.is_file()),
                "next": prompts,
            },
            indent=2,
        )
    )
    return 0


def _load_json_maybe(value: object) -> object | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _debugger_tool_name(name: str) -> str:
    prefix = "mcp__mcp-debugger__"
    if name.startswith(prefix):
        return f"mcp-debugger.{name.removeprefix(prefix)}"
    return name


def _basename(path: object) -> str:
    if not isinstance(path, str) or not path:
        return ""
    return Path(path).name


def _format_tool_use(name: str, tool_input: object) -> str:
    if not isinstance(tool_input, dict):
        return f"Tool: {_debugger_tool_name(name)}"

    if name.endswith("__debug_python_repro"):
        program = _basename(tool_input.get("program"))
        if program:
            return f"Tool: {_debugger_tool_name(name)} ({program})"
    if name.endswith("__debug_evaluate"):
        expression = tool_input.get("expression")
        if isinstance(expression, str):
            return f"Tool: {_debugger_tool_name(name)} ({expression})"
    if name.endswith("__debug_stop"):
        return f"Tool: {_debugger_tool_name(name)}"
    if name == "Read":
        file_path = _basename(tool_input.get("file_path"))
        if file_path:
            return f"Tool: Read ({file_path})"
    if name == "Bash":
        description = tool_input.get("description")
        if isinstance(description, str) and description:
            return f"Tool: Bash ({description})"
    if name == "ToolSearch":
        return "Tool: ToolSearch"
    return f"Tool: {_debugger_tool_name(name)}"


def _format_locals(locals_: object) -> str | None:
    if not isinstance(locals_, list):
        return None
    values: list[str] = []
    for item in locals_:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and isinstance(value, str):
            values.append(f"{name}={value}")
    if not values:
        return None
    return "Locals: " + " ".join(values)


def _format_debugger_result(payload: object, tool_name: str | None) -> list[str]:
    data = _load_json_maybe(payload)
    if not isinstance(data, dict):
        return []

    lines: list[str] = []
    stopped = data.get("stopped")
    if isinstance(stopped, dict):
        location = stopped.get("location")
        if isinstance(location, dict):
            source = location.get("source")
            file_name = ""
            if isinstance(source, dict):
                file_name = _basename(source.get("path"))
            name = location.get("name")
            line = location.get("line")
            if isinstance(name, str) and isinstance(line, int):
                prefix = f"{file_name}:" if file_name else ""
                lines.append(f"Stopped: {prefix}{line} in {name}")

    snapshot = data.get("snapshot")
    if isinstance(snapshot, dict):
        locals_line = _format_locals(snapshot.get("locals"))
        if locals_line:
            lines.append(locals_line)

    expression = data.get("expression")
    result = data.get("result")
    if isinstance(expression, str) and isinstance(result, str):
        lines.append(f"Eval: {expression} -> {result}")

    state = data.get("state")
    if tool_name and tool_name.endswith("__debug_stop") and isinstance(state, str):
        lines.append(f"Debug session: {state}")

    error = data.get("error")
    if isinstance(error, str):
        lines.append(f"Tool error: {error}")

    return lines


def _message_content_items(event: dict[str, object]) -> list[dict[str, object]]:
    message = event.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict)]


def _format_claude_stream(input_stream, output_stream) -> int:
    tool_names: dict[str, str] = {}
    pending_tool_errors: dict[str, list[str]] = {}
    mcp_debugger_status: str | None = None
    mcp_debugger_active_printed = False

    def flush_tool_errors(tool_name: str | None = None) -> None:
        names = [tool_name] if tool_name else list(pending_tool_errors)
        for name in names:
            if not name:
                continue
            errors = pending_tool_errors.pop(name, [])
            for error in errors:
                print(error, file=output_stream, flush=True)

    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(line, file=output_stream, flush=True)
            continue
        if not isinstance(event, dict):
            continue

        event_type = event.get("type")
        if event_type == "system" and event.get("subtype") == "init":
            cwd = event.get("cwd")
            if isinstance(cwd, str):
                print(f"Working directory: {cwd}", file=output_stream, flush=True)
            mcp_servers = event.get("mcp_servers")
            if isinstance(mcp_servers, list):
                for server in mcp_servers:
                    if not isinstance(server, dict) or server.get("name") != "mcp-debugger":
                        continue
                    status = server.get("status")
                    if isinstance(status, str):
                        mcp_debugger_status = status
                        display_status = "starting" if status == "pending" else status
                    else:
                        display_status = "unknown"
                    print(f"MCP: mcp-debugger {display_status}", file=output_stream, flush=True)
            continue

        if event_type == "assistant":
            for item in _message_content_items(event):
                content_type = item.get("type")
                if content_type == "text":
                    flush_tool_errors()
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        print(text.strip(), file=output_stream, flush=True)
                elif content_type == "tool_use":
                    tool_id = item.get("id")
                    name = item.get("name")
                    if isinstance(tool_id, str) and isinstance(name, str):
                        tool_names[tool_id] = name
                    if isinstance(name, str):
                        if (
                            name.startswith("mcp__mcp-debugger__")
                            and mcp_debugger_status != "connected"
                            and not mcp_debugger_active_printed
                        ):
                            print("MCP: mcp-debugger active", file=output_stream, flush=True)
                            mcp_debugger_active_printed = True
                        print(_format_tool_use(name, item.get("input")), file=output_stream, flush=True)
            continue

        if event_type == "user":
            for item in _message_content_items(event):
                if item.get("type") != "tool_result":
                    continue
                tool_id = item.get("tool_use_id")
                tool_name = tool_names.get(tool_id) if isinstance(tool_id, str) else None
                if item.get("is_error"):
                    error_lines = [f"Tool error from {_debugger_tool_name(tool_name or 'unknown')}"]
                    for formatted in _format_debugger_result(item.get("content"), tool_name):
                        error_lines.append(formatted)
                    pending_tool_errors.setdefault(tool_name or "unknown", []).extend(error_lines)
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    flush_tool_errors(tool_name)
                    if tool_name == "ToolSearch":
                        print("Debugger tools loaded", file=output_stream, flush=True)
                    continue
                formatted_lines = _format_debugger_result(content, tool_name)
                if formatted_lines:
                    pending_tool_errors.pop(tool_name or "unknown", None)
                for formatted in formatted_lines:
                    print(formatted, file=output_stream, flush=True)
            continue

        if event_type == "result":
            flush_tool_errors()
            subtype = event.get("subtype")
            duration_ms = event.get("duration_ms")
            turns = event.get("num_turns")
            summary: list[str] = [f"Done: {subtype}"] if isinstance(subtype, str) else ["Done"]
            if isinstance(turns, int):
                summary.append(f"{turns} turns")
            if isinstance(duration_ms, int):
                summary.append(f"{duration_ms / 1000:.1f}s")
            print(" | ".join(summary), file=output_stream, flush=True)

    flush_tool_errors()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Utilities for the mcp-debugger MCP server.")
    parser.add_argument("--version", action="version", version=f"mcp-debugger {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Verify debugpy and the MCP server entry point.")
    instructions = subparsers.add_parser("agent-instructions", help="Print recommended agent guidance.")
    instructions.add_argument("--target", choices=["generic", "claude", "codex"], default="generic")
    install = subparsers.add_parser("install-snippet", help="Print an MCP install command or config snippet.")
    install.add_argument("target", choices=["codex", "claude", "json"], help="Snippet target.")
    init_files = subparsers.add_parser("init-agent-files", help="Write CLAUDE.md and/or AGENTS.md guidance.")
    init_files.add_argument("--target", choices=["claude", "codex", "both"], default="both")
    init_files.add_argument("--directory", default=".")
    init_files.add_argument("--force", action="store_true")
    demo = subparsers.add_parser("demo-project", help="Create a tiny prompt-based debugger demo project.")
    demo.add_argument("directory", nargs="?", default=".")
    demo.add_argument("--target", choices=["claude", "codex", "both"], default="claude")
    demo.add_argument("--force", action="store_true")
    subparsers.add_parser("claude-progress", help="Format Claude Code stream-json output for humans.")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return _doctor()
    if args.command == "agent-instructions":
        if args.target == "generic":
            print(AGENT_USAGE_GUIDANCE)
        else:
            print(guidance_for_target(args.target))
        return 0
    if args.command == "install-snippet":
        return _print_install(args.target)
    if args.command == "init-agent-files":
        return _init_agent_files(args.target, args.directory, args.force)
    if args.command == "demo-project":
        return _demo_project(args.target, args.directory, args.force)
    if args.command == "claude-progress":
        return _format_claude_stream(sys.stdin, sys.stdout)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
