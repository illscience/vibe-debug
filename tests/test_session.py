from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from vibe_debug.dap import DAPEvent
from vibe_debug.session import DebugSession


class FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._events: list[DAPEvent] = []

    def request(
        self,
        command: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.requests.append((command, arguments or {}))
        return {"breakpoints": arguments.get("breakpoints", []) if arguments else []}

    @property
    def events(self) -> list[DAPEvent]:
        return list(self._events)


class DebugSessionTests(unittest.TestCase):
    def test_set_breakpoints_sends_log_messages_to_dap(self) -> None:
        client = FakeClient()
        session = DebugSession(session_id="session-1", client=client)  # type: ignore[arg-type]

        session.set_breakpoints(
            file="sample.py",
            lines=[5, 9],
            cwd="/tmp/project",
            conditions=[None, "enabled"],
            hit_conditions=[None, "3"],
            log_messages=["x={x}", None],
        )

        self.assertEqual(client.requests[0][0], "setBreakpoints")
        arguments = client.requests[0][1]
        self.assertEqual(
            arguments["breakpoints"],
            [
                {"line": 5, "logMessage": "x={x}"},
                {"line": 9, "condition": "enabled", "hitCondition": "3"},
            ],
        )

    def test_drain_logpoints_returns_known_logpoint_output_events(self) -> None:
        client = FakeClient()
        session = DebugSession(session_id="session-1", client=client)  # type: ignore[arg-type]
        path = str((Path("/tmp/project") / "sample.py").resolve())
        session.logpoint_locations.add((path, 5))
        client._events.append(
            DAPEvent(
                event="output",
                body={
                    "category": "console",
                    "output": "x=42\n",
                    "source": {"path": path},
                    "line": 5,
                    "threadId": 1,
                },
                raw={},
            )
        )

        self.assertEqual(
            session.drain_logpoints(),
            [{"file": path, "line": 5, "message": "x=42", "thread_id": 1}],
        )
        self.assertEqual(session.drain_logpoints(), [])

    def test_drain_logpoints_matches_debugpy_output_with_empty_source(self) -> None:
        client = FakeClient()
        session = DebugSession(session_id="session-1", client=client)  # type: ignore[arg-type]
        path = str((Path("/tmp/project") / "sample.py").resolve())
        session.set_breakpoints(file="sample.py", lines=[5], cwd="/tmp/project", log_messages=["x={x}"])
        client._events.append(
            DAPEvent(
                event="output",
                body={"category": "stdout", "output": "x=42\n", "source": {}},
                raw={},
            )
        )

        self.assertEqual(session.drain_logpoints(), [{"file": path, "line": 5, "message": "x=42"}])

    def test_drain_logpoints_ignores_program_stdout_without_source(self) -> None:
        client = FakeClient()
        session = DebugSession(session_id="session-1", client=client)  # type: ignore[arg-type]
        session.set_breakpoints(file="sample.py", lines=[5], cwd="/tmp/project", log_messages=["value={value}"])
        client._events.append(
            DAPEvent(
                event="output",
                body={"category": "stdout", "output": "value=from print\n"},
                raw={},
            )
        )

        self.assertEqual(session.drain_logpoints(), [])


if __name__ == "__main__":
    unittest.main()
