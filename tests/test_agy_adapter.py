"""Tests for the Antigravity CLI adapter (agy).

Validates MCP config, JSON hook registration, detection, and
config merge safety without network calls.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path


# -- Import tests --

def test_import_agy_adapter():
    from truememory.hooks.adapters.agy import AgyAdapter  # noqa: F401


def test_agy_in_registry():
    from truememory.hooks.registry import get_adapter
    adapter = get_adapter("agy")
    assert adapter is not None
    assert adapter.cli_id == "agy"


# -- Instantiation --

def test_agy_adapter_properties():
    from truememory.hooks.adapters.agy import AgyAdapter
    adapter = AgyAdapter()
    assert adapter.name == "Antigravity CLI"
    assert adapter.cli_id == "agy"
    assert isinstance(adapter.config_path, Path)
    assert adapter.config_path.name == "mcp_config.json"


def test_agy_implements_all_abstract_methods():
    from truememory.hooks.adapters.base import CLIAdapter
    from truememory.hooks.adapters.agy import AgyAdapter
    abstract_methods = {
        name for name, _ in inspect.getmembers(CLIAdapter)
        if getattr(getattr(CLIAdapter, name, None), "__isabstractmethod__", False)
    }
    adapter = AgyAdapter()
    for method_name in abstract_methods:
        assert hasattr(adapter, method_name), f"Missing: {method_name}"


# -- Detection --

def test_detect_false_no_dir(tmp_path, monkeypatch):
    from truememory.hooks.adapters import agy as agy_mod
    monkeypatch.setattr(agy_mod, "_AGY_DIR", tmp_path / "nonexistent")
    from truememory.hooks.adapters.agy import AgyAdapter
    adapter = AgyAdapter()
    monkeypatch.setattr("shutil.which", lambda x: None)
    assert not adapter.detect()


def test_detect_true_with_dir(tmp_path, monkeypatch):
    from truememory.hooks.adapters import agy as agy_mod
    agy_dir = tmp_path / "antigravity-cli"
    agy_dir.mkdir()
    monkeypatch.setattr(agy_mod, "_AGY_DIR", agy_dir)
    from truememory.hooks.adapters.agy import AgyAdapter
    adapter = AgyAdapter()
    assert adapter.detect()


# -- MCP config --

def test_install_mcp_creates_config(tmp_path, monkeypatch):
    from truememory.hooks.adapters import agy as agy_mod
    mcp_path = tmp_path / "mcp_config.json"
    monkeypatch.setattr(agy_mod, "_MCP_CONFIG_PATH", mcp_path)
    from truememory.hooks.adapters.agy import AgyAdapter
    adapter = AgyAdapter()
    adapter.install_mcp(python_path="/usr/bin/python3")

    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert "truememory" in data["mcpServers"]
    assert data["mcpServers"]["truememory"]["command"] == "/usr/bin/python3"
    assert data["mcpServers"]["truememory"]["args"] == ["-m", "truememory.mcp_server"]

