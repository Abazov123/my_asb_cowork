"""Persistent multi-turn Claude session via --print --resume."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import AsyncIterator

logger = logging.getLogger(__name__)


class ClaudeSession:
    """Multi-turn Claude session using --print --resume SESSION_ID.

    Each send() spawns a subprocess:
        claude --print --output-format stream-json --verbose
               --include-partial-messages --dangerously-skip-permissions
               --mcp-config ... [--resume SESSION_ID] -p "message"

    session_id is extracted from the `result` event and used in next turn.
    """

    def __init__(
        self,
        vault_path: Path,
        mcp_config_path: Path,
        todoist_api_key: str = "",
    ) -> None:
        self.vault_path = vault_path
        self.mcp_config_path = mcp_config_path
        self.todoist_api_key = todoist_api_key
        self._session_id: str | None = None
        self._stopped = False
        self._current_proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        """No-op: session starts lazily on first send()."""
        self._stopped = False

    async def send(self, prompt: str) -> AsyncIterator[dict]:
        """Send a message and yield stream-json events until turn ends."""
        if self._stopped:
            return

        cmd = [
            "claude", "--print",
            "--model", "claude-sonnet-4-6",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--dangerously-skip-permissions",
            "--mcp-config", str(self.mcp_config_path),
        ]
        if self._session_id:
            cmd.extend(["--resume", self._session_id])
        cmd.extend(["-p", prompt])

        env = os.environ.copy()
        if self.todoist_api_key:
            env["TODOIST_API_KEY"] = self.todoist_api_key

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                limit=1024 * 1024,  # 1MB to prevent ValueError on long lines
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.vault_path.parent),
                env=env,
            )
        except FileNotFoundError:
            logger.error("claude CLI not found")
            return

        self._current_proc = proc
        assert proc.stdout is not None

        try:
            async for raw_line in proc.stdout:
                if self._stopped:
                    break
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Non-JSON stdout: %.100s", line.decode(errors="replace"))
                    continue

                # Capture session_id from result event for next turn
                if event.get("type") == "result":
                    sid = event.get("session_id")
                    if sid:
                        self._session_id = sid
                        logger.info("Session ID: %s", sid)

                yield event
        finally:
            self._current_proc = None

        await proc.wait()
        if proc.returncode not in (0, None):
            stderr_out = b""
            if proc.stderr:
                stderr_out = await proc.stderr.read()
            logger.error(
                "claude exited %d: %s",
                proc.returncode,
                stderr_out.decode(errors="replace")[:300],
            )

    async def stop(self) -> None:
        """Mark session as stopped and kill any running subprocess."""
        self._stopped = True
        self._session_id = None
        proc = self._current_proc
        if proc is not None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    @property
    def is_alive(self) -> bool:
        return not self._stopped


# Global session registry (single-user bot, in-memory)
SESSIONS: dict[int, ClaudeSession] = {}
