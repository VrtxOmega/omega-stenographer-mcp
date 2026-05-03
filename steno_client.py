"""Stenographer Client — Python helper for persistent-process MCP communication.

Usage:
    from steno_client import StenographerClient
    client = StenographerClient()
    client.ingest("user", "Fix the auth bug", session_id="debug-1")
    notes = client.get_brief()
    results = client.search("JWT OR auth")
    client.close()
"""

import subprocess
import json
import os
import sys
import signal
from pathlib import Path


class StenographerClient:
    """Persistent-process client for Omega Stenographer MCP server.

    Starts the server once as a subprocess and reuses it across calls.
    Avoids the 1-2s cold-start cost on every tool invocation.
    """

    def __init__(self, server_path=None):
        """Initialize the client and start the server subprocess.

        Args:
            server_path: Path to omega_stenographer_mcp_standalone.py.
                         Defaults to the same directory as this file.
        """
        if server_path is None:
            server_path = str(
                Path(__file__).parent / "omega_stenographer_mcp_standalone.py"
            )

        self.server_path = server_path
        self._call_id = 0
        self._proc = None
        self._start()

    def _start(self):
        """Start the MCP server subprocess (stdio transport)."""
        self._proc = subprocess.Popen(
            [sys.executable, self.server_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # Warm-up: send initialize
        self._send_raw({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "steno_client", "version": "1.0.0"}
            }
        })
        self._read_response()

    def _next_id(self):
        self._call_id += 1
        return self._call_id

    def _send_raw(self, message: dict):
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()

    def _read_response(self):
        line = self._proc.stdout.readline()
        if not line:
            raise ConnectionError("Server process closed stdout")
        return json.loads(line)

    def call(self, tool_name: str, arguments: dict) -> dict:
        """Call any stenographer tool by name.

        Args:
            tool_name: Name of the tool (e.g. 'stenographer_ingest_exchange')
            arguments: Tool arguments as a dict

        Returns:
            dict: The parsed tool result content
        """
        msg = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }
        self._send_raw(msg)
        response = self._read_response()

        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        content = response.get("result", {}).get("content", [])
        if content and len(content) > 0:
            text = content[0].get("text", "")
            # Try to parse JSON, fall back to raw text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"text": text}
        return {}

    # ── Convenience methods ──────────────────────────────────

    def ingest(self, role, content, session_id="default"):
        """Ingest a single conversation turn."""
        return self.call("stenographer_ingest_exchange", {
            "role": role,
            "content": content,
            "session_id": session_id
        })

    def get_brief(self):
        """Get the live running notes document."""
        return self.call("stenographer_get_brief", {})

    def compact_guard(self, query=""):
        """Get compressed briefing + top-K relevant briefs."""
        return self.call("stenographer_compact_guard", {"query": query})

    def mark_milestone(self, exchange_id, label):
        """Flag a critical decision for tier-A priority."""
        return self.call("stenographer_mark_milestone", {
            "exchange_id": exchange_id,
            "label": label
        })

    def search(self, query, limit=10):
        """FTS5 keyword search over all ingested exchanges."""
        return self.call("stenographer_query_history", {
            "query": query,
            "limit": limit
        })

    def close(self):
        """Gracefully shut down the server subprocess."""
        if self._proc:
            self._proc.stdin.close()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
            self._proc = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()
