"""Antigravity CLI adapter — MCP config + JSON lifecycle hooks.

Antigravity CLI uses:
- ~/.gemini/config/mcp_config.json for MCP server registration
- ~/.gemini/config/hooks.json for lifecycle hook registration
- Same JSON stdin/stdout hook protocol as Claude Code
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from truememory.hooks.adapters.base import CLIAdapter

_GEMINI_DIR = Path.home() / ".gemini"
_AGY_DIR = _GEMINI_DIR / "antigravity-cli"
_CONFIG_DIR = _GEMINI_DIR / "config"
_MCP_CONFIG_PATH = _CONFIG_DIR / "mcp_config.json"
_HOOKS_CONFIG_PATH = _CONFIG_DIR / "hooks.json"

_HOOK_EVENTS = {
    "SessionStart": {
        "script": "session_start.py",
        "timeout": 10000,
    },
    "SessionEnd": {
        "script": "stop.py",
        "timeout": 5000,
    },
    "UserPromptSubmit": {
        "script": "user_prompt_submit.py",
        "timeout": 5000,
    },
    "PreCompress": {
        "script": "compact.py",
        "timeout": 5000,
    },
}

_TRUEMEMORY_MARKER = "truememory"

_SYSTEM_PROMPT_TEMPLATE = """\
# TrueMemory — Persistent Memory

TrueMemory is the **primary long-horizon memory** for this user. It persists facts, preferences, decisions, and corrections across sessions, projects, and machines.

When the `truememory` MCP server is connected, follow these rules:

## Auto-Recall (every session)
- At the START of each conversation, call `truememory_search` with a broad query about the user to load relevant memories before responding.
- Before making recommendations, check TrueMemory for stored preferences.
- When the user asks anything about past conversations or personal facts — search TrueMemory first.

## Auto-Store (during conversation)
- When the user shares a personal preference, store it immediately via `truememory_store`. Do not ask permission.
- When an important decision is made, store it.
- When the user corrects you, store the correction.
- Write each memory as a clear, atomic statement.
- Do NOT store full conversations, large code blocks, or transient debugging context.

## Background Processing
- Memories are also extracted automatically from conversations via background processing.
- The SessionEnd hook captures the full transcript and runs deep extraction after sessions end.
- You do NOT need to store everything manually — focus on in-conversation corrections and explicit preferences.
"""


class AgyAdapter(CLIAdapter):
    """Adapter for Antigravity CLI."""

    @property
    def name(self) -> str:
        return "Antigravity CLI"

    @property
    def cli_id(self) -> str:
        return "agy"

    @property
    def config_path(self) -> Path:
        return _MCP_CONFIG_PATH

    def detect(self) -> bool:
        return _AGY_DIR.is_dir() or shutil.which("agy") is not None or shutil.which("antigravity-cli") is not None

    def is_configured(self) -> bool:
        return self._has_mcp_entry() or self._has_hook_entries()

    def install_mcp(self, python_path: str | None = None) -> None:
        py = python_path or sys.executable
        mcp_config = self._read_mcp_config()

        servers = mcp_config.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            servers = {}
            mcp_config["mcpServers"] = servers

        servers["truememory"] = {
            "command": py,
            "args": ["-m", "truememory.mcp_server"],
        }

        self._write_mcp_config(mcp_config)

    def install_hooks(
        self,
        python_path: str | None = None,
        user_id: str = "",
        db_path: str = "",
    ) -> None:
        py = python_path or sys.executable
        hooks_dir = Path(__file__).parent.parent.parent / "ingest" / "hooks"

        hooks_config = self._read_hooks_config()
        tm_hooks = hooks_config.setdefault("truememory", {})
        if not isinstance(tm_hooks, dict):
            tm_hooks = {}
            hooks_config["truememory"] = tm_hooks

        for event, info in _HOOK_EVENTS.items():
            event_list = tm_hooks.setdefault(event, [])
            if not isinstance(event_list, list):
                event_list = []
                tm_hooks[event] = event_list

            if self._event_has_truememory(event_list):
                continue

            script_path = hooks_dir / info["script"]
            cmd = self._build_command(py, script_path, user_id, db_path)
            
            event_list.append({
                "matcher": "",
                "hooks": [{
                    "type": "command",
                    "command": cmd,
                    "timeout": info["timeout"],
                }]
            })

        self._write_hooks_config(hooks_config)

    def uninstall(self) -> None:
        # Uninstall MCP
        mcp_config = self._read_mcp_config()
        servers = mcp_config.get("mcpServers", {})
        if isinstance(servers, dict) and "truememory" in servers:
            del servers["truememory"]
            self._write_mcp_config(mcp_config)

        # Uninstall Hooks
        hooks_config = self._read_hooks_config()
        if isinstance(hooks_config, dict) and "truememory" in hooks_config:
            del hooks_config["truememory"]
            self._write_hooks_config(hooks_config)

    def verify(self) -> bool:
        return self._has_mcp_entry() and self._has_hook_entries()

    def get_system_prompt_path(self) -> Path | None:
        return _GEMINI_DIR / "GEMINI.md"

    def get_system_prompt_content(self) -> str:
        return _SYSTEM_PROMPT_TEMPLATE.strip()

    # -- Private helpers --

    @staticmethod
    def _build_command(
        python_path: str,
        script_path: Path,
        user_id: str = "",
        db_path: str = "",
    ) -> str:
        parts: list[str] = [python_path, str(script_path)]
        if user_id:
            parts.extend(["--user", user_id])
        if db_path:
            parts.extend(["--db", db_path])
        if sys.platform == "win32":
            import subprocess as _sp
            return _sp.list2cmdline(parts)
        return " ".join(shlex.quote(p) for p in parts)

    def _read_mcp_config(self) -> dict:
        for path in (_MCP_CONFIG_PATH, _AGY_DIR / "mcp_config.json"):
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return data
                except (json.JSONDecodeError, OSError):
                    pass
        return {}

    def _write_mcp_config(self, settings: dict) -> None:
        for path in (_MCP_CONFIG_PATH, _AGY_DIR / "mcp_config.json"):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
            except OSError:
                pass

    def _read_hooks_config(self) -> dict:
        for path in (_HOOKS_CONFIG_PATH, _AGY_DIR / "hooks.json"):
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return data
                except (json.JSONDecodeError, OSError):
                    pass
        return {}

    def _write_hooks_config(self, settings: dict) -> None:
        for path in (_HOOKS_CONFIG_PATH, _AGY_DIR / "hooks.json"):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
            except OSError:
                pass

    def _has_mcp_entry(self) -> bool:
        mcp_config = self._read_mcp_config()
        return "truememory" in mcp_config.get("mcpServers", {})

    def _has_hook_entries(self) -> bool:
        hooks_config = self._read_hooks_config()
        tm_hooks = hooks_config.get("truememory", {})
        if not isinstance(tm_hooks, dict):
            return False
        for entries in tm_hooks.values():
            if not isinstance(entries, list):
                continue
            if self._event_has_truememory(entries):
                return True
        return False

    @staticmethod
    def _event_has_truememory(entries: list) -> bool:
        return any(
            isinstance(h, dict)
            and (
                _TRUEMEMORY_MARKER in h.get("command", "").lower()
                or any(
                    isinstance(ih, dict)
                    and _TRUEMEMORY_MARKER in ih.get("command", "").lower()
                    for ih in h.get("hooks", [])
                )
            )
            for h in entries
        )

    def can_complete(self) -> bool:
        if shutil.which("agy") is None:
            return False
        return bool(os.environ.get("ANTIGRAVITY_SOURCE_METADATA") or os.environ.get("AGY_DIR"))

    def complete(self, config: LLMConfig, prompt: str, system: str = "") -> str:
        import subprocess
        import time
        from truememory.ingest.models import LLMError

        exe_path = shutil.which("agy")
        if not exe_path:
            raise LLMError(
                "`agy` CLI not found on PATH. Install the corresponding "
                "CLI or choose a different --provider."
            )

        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        cmd = [exe_path, "-p", full_prompt]
        if config.model:
            cmd.extend(["--model", config.model])

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["TRUEMEMORY_EXTRACTION"] = "1"

        # Wait if parent process is still running to avoid database/session locks
        parent_is_cli = bool(os.environ.get("ANTIGRAVITY_SOURCE_METADATA") or os.environ.get("AGY_DIR"))
        if parent_is_cli:
            try:
                ppid = os.getppid()
                start_wait = time.time()
                # Wait for parent PID to exit (up to 5 seconds)
                while ppid > 1 and (time.time() - start_wait < 5.0):
                    os.kill(ppid, 0)
                    time.sleep(0.2)
            except OSError:
                pass

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise LLMError("agy CLI timed out after 120s") from e
        except OSError as e:
            raise LLMError(f"agy CLI invocation failed: {e}") from e

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()[:500]
            raise LLMError(f"agy CLI exit {proc.returncode}: {stderr or 'no stderr'}")

        return proc.stdout.strip()

