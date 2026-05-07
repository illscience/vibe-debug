# Debugging Workflow

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
