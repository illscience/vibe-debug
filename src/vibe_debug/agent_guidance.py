from __future__ import annotations


AGENT_USAGE_GUIDANCE = """Use vibe-debug when a Python bug has runtime behavior that static reading does not fully explain.

Prefer live debugger state when:
- a test, script, or command reproduces the bug;
- the bug depends on branches, state, inputs, or object values;
- an exception stack is insufficient and local variables matter;
- you are about to guess what a variable contains.

Recommended workflow:
1. If a vibe-debug skill is available, use its CLI workflow first.
2. Otherwise, run `npx -y github:illscience/vibe-debug debug-python` from the shell.
3. If the MCP server is installed, `debug_python_repro` is the best first MCP tool.
4. Inspect stopped location, locals, and evaluations before editing code.

Evaluate only read-style expressions. Treat evaluation like running code inside the debuggee.
"""


PROJECT_DEBUGGING_GUIDANCE = """# Debugging Workflow

When a Python bug has a reproducible script, test, command, or request, prefer observing live runtime state before proposing a fix.

Use the `vibe-debug` skill or CLI when:
- the failure depends on branches, inputs, object state, or local variables;
- source reading suggests multiple possible causes;
- you are about to infer a variable value that can be observed directly.

Recommended workflow:
1. Use the `vibe-debug` skill if it is available in this project.
2. Run `npx -y github:illscience/vibe-debug debug-python <script.py> --break <file.py>:<line> --json`.
3. Inspect the stopped location, locals, and evaluations.
4. Use `--eval` only for read-style expressions; it can execute code in the debuggee.
5. If an MCP server named `vibe-debug` is installed, `debug_python_repro` is also acceptable.

When reporting a bug, include the runtime values you observed and distinguish them from source-code inference.
"""


def guidance_for_target(target: str) -> str:
    if target not in {"generic", "claude", "codex"}:
        raise ValueError(f"unknown guidance target: {target}")
    return PROJECT_DEBUGGING_GUIDANCE
