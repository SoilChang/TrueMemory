"""Abstract base class for CLI adapters.

Each supported CLI (Claude Code, Kimi, Hermes, OpenClaw) implements
this interface to handle its config format, hook registration, and
MCP server setup.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class CLIAdapter(ABC):
    """Base interface for CLI-specific TrueMemory integration."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable CLI name (e.g. 'Claude Code')."""

    @property
    @abstractmethod
    def cli_id(self) -> str:
        """Machine identifier (e.g. 'claude', 'kimi', 'hermes', 'openclaw')."""

    @property
    @abstractmethod
    def config_path(self) -> Path:
        """Path to the CLI's main config file."""

    @abstractmethod
    def detect(self) -> bool:
        """Return True if this CLI is installed on the system."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if TrueMemory is already wired into this CLI."""

    @abstractmethod
    def install_mcp(self, python_path: str | None = None) -> None:
        """Register the TrueMemory MCP server in the CLI's config."""

    @abstractmethod
    def install_hooks(
        self,
        python_path: str | None = None,
        user_id: str = "",
        db_path: str = "",
    ) -> None:
        """Register TrueMemory lifecycle hooks in the CLI's config."""

    @abstractmethod
    def uninstall(self) -> None:
        """Remove all TrueMemory entries from the CLI's config."""

    @abstractmethod
    def verify(self) -> bool:
        """Smoke-test the installation (config exists, paths resolve)."""

    @abstractmethod
    def get_system_prompt_path(self) -> Path | None:
        """Return the path to the CLI's system prompt file, or None."""

    @abstractmethod
    def get_system_prompt_content(self) -> str:
        """Return the TrueMemory system prompt content for this CLI."""

    def install_system_prompt(self) -> None:
        """Merge the TrueMemory system prompt instructions into the CLI's prompt file."""
        target_path = self.get_system_prompt_path()
        if not target_path:
            return
        prompt_content = self.get_system_prompt_content()
        if not prompt_content:
            return

        managed_block = (
            f"\n{_PROMPT_MARKER_START}\n"
            f"{prompt_content.strip()}\n"
            f"{_PROMPT_MARKER_END}\n"
        )

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"  [WARN] Cannot create {target_path.parent}: {e}")
            return

        # Read existing content if present
        existing = ""
        if target_path.exists():
            try:
                existing = target_path.read_text(encoding="utf-8")
            except OSError as e:
                print(f"  [WARN] Cannot read existing prompt file: {e}")
                return

        # Back up the existing file before mutating it
        if existing and target_path.exists():
            import time as _time
            backup_path = target_path.with_name(f"{target_path.name}.bak.{int(_time.time())}")
            try:
                backup_path.write_text(existing, encoding="utf-8")
            except OSError:
                pass  # Non-fatal

        # If a managed block already exists, replace it; otherwise append
        if _PROMPT_MARKER_START in existing and _PROMPT_MARKER_END in existing:
            before, _, rest = existing.partition(_PROMPT_MARKER_START)
            _, _, after = rest.partition(_PROMPT_MARKER_END)
            new_content = before.rstrip() + managed_block + after.lstrip()
        else:
            new_content = existing.rstrip() + "\n" + managed_block if existing else managed_block

        try:
            target_path.write_text(new_content, encoding="utf-8")
            print(f"  [OK] Merged truememory instructions into {target_path}")
        except OSError as e:
            print(f"  [WARN] Cannot write system prompt file: {e}")

    def uninstall_system_prompt(self) -> None:
        """Remove TrueMemory system prompt instructions from the CLI's prompt file."""
        target_path = self.get_system_prompt_path()
        if not target_path or not target_path.exists():
            return

        try:
            content = target_path.read_text(encoding="utf-8")
            if _PROMPT_MARKER_START in content and _PROMPT_MARKER_END in content:
                before, _, rest = content.partition(_PROMPT_MARKER_START)
                _, _, after = rest.partition(_PROMPT_MARKER_END)
                new_content = (before.rstrip() + "\n" + after.lstrip()).strip() + "\n"
                if new_content.strip() == "":
                    try:
                        target_path.unlink()
                        print(f"  Removed empty prompt file: {target_path}")
                    except OSError:
                        pass
                else:
                    target_path.write_text(new_content, encoding="utf-8")
                    print(f"  Removed truememory instructions from {target_path}")
        except OSError:
            pass


_PROMPT_MARKER_START = "<!-- BEGIN truememory-ingest managed section -->"
_PROMPT_MARKER_END = "<!-- END truememory-ingest managed section -->"


def get_generic_system_prompt() -> str:
    """Return the TrueMemory system prompt for non-Claude CLIs."""
    template = Path(__file__).parent.parent.parent / "ingest" / "CLAUDE_TEMPLATE.md"
    if template.exists():
        try:
            content = template.read_text(encoding="utf-8").strip()
            content = content.replace("Claude Code's built-in auto-memory", "The host CLI's built-in memory")
            content = content.replace("(`MEMORY.md` files under `~/.claude/projects/*/memory/`)", "")
            return content
        except OSError:
            pass
    return (
        "# TrueMemory — Persistent Memory\n\n"
        "You have access to TrueMemory MCP tools for persistent memory.\n"
        "- Use `truememory_store` to save user facts, preferences, and decisions.\n"
        "- Use `truememory_search` to recall stored memories before answering.\n"
        "- Search TrueMemory FIRST on any 'do you remember' question.\n"
    )

