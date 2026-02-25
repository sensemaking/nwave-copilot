"""Agents installer plugin: installs nWave agents to ~/.config/copilot/agents/."""

import shutil
from pathlib import Path

from nwave_copilot.converters.agent_converter import convert_agent
from nwave_copilot.plugins.base import InstallContext, InstallPlugin, PluginResult


class AgentsPlugin(InstallPlugin):
    """Converts and installs nWave agents to the personal Copilot agents directory.

    Source:  nWave/agents/nw-*.md  (Claude Code format)
    Target:  ~/.config/copilot/agents/nw-*.agent.md  (Copilot format)

    Frontmatter is converted on-the-fly: tool aliases mapped, unsupported
    fields (model, maxTurns, skills) dropped.
    """

    def __init__(self) -> None:
        super().__init__(name="agents", priority=10)

    def install(self, context: InstallContext) -> PluginResult:
        try:
            context.logger.info("  📦 Installing agents...")
            source_dir = context.framework_source / "nWave" / "agents"

            if not source_dir.exists():
                return PluginResult(
                    success=True,
                    plugin_name=self.name,
                    message="No agents directory found, skipping",
                )

            target_dir = context.agents_dir
            source_files = sorted(source_dir.glob("nw-*.md"))

            if not context.dry_run:
                # Clean out old nWave agents but leave any user agents intact
                for stale in target_dir.glob("nw-*.agent.md"):
                    stale.unlink()
                target_dir.mkdir(parents=True, exist_ok=True)

            installed: list[Path] = []
            for source_file in source_files:
                converted = convert_agent(source_file)
                target_path = target_dir / converted.target_filename
                if not context.dry_run:
                    target_path.write_text(converted.content, encoding="utf-8")
                installed.append(target_path)

            msg = f"Agents installed ({len(installed)} files)"
            context.logger.info(f"  ✅ {msg}")
            return PluginResult(
                success=True,
                plugin_name=self.name,
                message=msg,
                installed_files=installed,
            )
        except Exception as e:
            context.logger.error(f"  ❌ Failed to install agents: {e}")
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message=f"Agents installation failed: {e!s}",
                errors=[str(e)],
            )

    def uninstall(self, context: InstallContext) -> PluginResult:
        try:
            context.logger.info("  🗑️  Uninstalling agents...")
            removed = []
            for agent_file in context.agents_dir.glob("nw-*.agent.md"):
                if not context.dry_run:
                    agent_file.unlink()
                removed.append(agent_file)
            msg = f"Removed {len(removed)} agent files"
            context.logger.info(f"  ✅ {msg}")
            return PluginResult(success=True, plugin_name=self.name, message=msg)
        except Exception as e:
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message=f"Uninstall failed: {e!s}",
                errors=[str(e)],
            )

    def verify(self, context: InstallContext) -> PluginResult:
        agent_files = list(context.agents_dir.glob("nw-*.agent.md"))
        if not agent_files:
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message="No nw-*.agent.md files found in agents directory",
                errors=["No agent files installed"],
            )
        return PluginResult(
            success=True,
            plugin_name=self.name,
            message=f"Verified {len(agent_files)} agent files",
        )
