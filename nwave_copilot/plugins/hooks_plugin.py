"""Hooks init plugin: writes DES hook configs to .github/hooks/.

Called by `nwave-copilot init` (not `install`).

Generates three Copilot hook config files that wire DES enforcement into
the project's AI coding session:

  .github/hooks/nw-pre-tool-use.json    — blocks unvalidated agent dispatches
  .github/hooks/nw-post-tool-use.json   — injects continuation context
  .github/hooks/nw-subagent-stop.json   — validates TDD phase completion

Hook scripts invoke the globally-installed Python DES adapter:
  python -m des.adapters.drivers.hooks.copilot_hook_adapter <action>

The DES Python logic lives in the installed nwave-copilot package.
The config files must be project-scoped (.github/hooks/).
"""

import json
import sys
from pathlib import Path

from nwave_copilot.plugins.base import InitContext, InitPlugin, PluginResult

_HOOKS_SUBDIR = Path(".github") / "hooks"

# Use sys.executable so hooks run with the same Python that nwave-copilot uses.
# Written as a literal in the JSON since the hook runs in the project's shell.
_PYTHON = sys.executable


def _pre_tool_use_config() -> dict:
    """Copilot preToolUse hook config for DES Task validation."""
    return {
        "version": 1,
        "hooks": {
            "preToolUse": [
                {
                    "command": f"{_PYTHON} -m des.adapters.drivers.hooks.copilot_hook_adapter pre-tool-use",
                    "matcher": {
                        "toolName": "agent",
                    },
                }
            ]
        },
    }


def _post_tool_use_config() -> dict:
    """Copilot postToolUse hook config for DES orchestrator feedback."""
    return {
        "version": 1,
        "hooks": {
            "postToolUse": [
                {
                    "command": f"{_PYTHON} -m des.adapters.drivers.hooks.copilot_hook_adapter post-tool-use",
                    "matcher": {
                        "toolName": "agent",
                    },
                }
            ]
        },
    }


def _subagent_stop_config() -> dict:
    """Copilot subagentStop hook config for DES TDD phase validation."""
    return {
        "version": 1,
        "hooks": {
            "subagentStop": [
                {
                    "command": f"{_PYTHON} -m des.adapters.drivers.hooks.copilot_hook_adapter subagent-stop",
                }
            ]
        },
    }


_HOOK_FILES: list[tuple[str, dict]] = [
    ("nw-pre-tool-use.json", _pre_tool_use_config()),
    ("nw-post-tool-use.json", _post_tool_use_config()),
    ("nw-subagent-stop.json", _subagent_stop_config()),
]


class HooksPlugin(InitPlugin):
    """Writes Copilot hook config files to .github/hooks/.

    Wires the DES (Deterministic Execution System) enforcement hooks into
    the project. Requires `nwave-copilot install` to have been run first
    so that the DES Python package is importable.
    """

    def __init__(self) -> None:
        super().__init__(name="hooks", priority=5)

    def init(self, context: InitContext) -> PluginResult:
        try:
            context.logger.info("  🪝 Writing hook config files...")
            hooks_dir = context.project_root / _HOOKS_SUBDIR
            installed: list[Path] = []

            for filename, config in _HOOK_FILES:
                target = hooks_dir / filename
                if not context.dry_run:
                    hooks_dir.mkdir(parents=True, exist_ok=True)
                    target.write_text(
                        json.dumps(config, indent=2) + "\n", encoding="utf-8"
                    )
                installed.append(target)

            msg = f"Hook configs written ({len(installed)} files)"
            context.logger.info(f"  ✅ {msg}")
            return PluginResult(
                success=True,
                plugin_name=self.name,
                message=msg,
                installed_files=installed,
            )
        except Exception as e:
            context.logger.error(f"  ❌ Failed to write hook configs: {e}")
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message=f"Hooks init failed: {e!s}",
                errors=[str(e)],
            )

    def deinit(self, context: InitContext) -> PluginResult:
        try:
            context.logger.info("  🗑️  Removing hook config files...")
            hooks_dir = context.project_root / _HOOKS_SUBDIR
            removed = 0
            for hook_file in hooks_dir.glob("nw-*.json"):
                if not context.dry_run:
                    hook_file.unlink()
                removed += 1
            msg = f"Removed {removed} hook config files"
            context.logger.info(f"  ✅ {msg}")
            return PluginResult(success=True, plugin_name=self.name, message=msg)
        except Exception as e:
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message=f"Deinit failed: {e!s}",
                errors=[str(e)],
            )

    def verify(self, context: InitContext) -> PluginResult:
        hooks_dir = context.project_root / _HOOKS_SUBDIR
        files = list(hooks_dir.glob("nw-*.json"))
        if not files:
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message="No nw-*.json hook files found in .github/hooks/",
                errors=["No hook configs installed"],
            )
        return PluginResult(
            success=True,
            plugin_name=self.name,
            message=f"Verified {len(files)} hook config files",
        )
