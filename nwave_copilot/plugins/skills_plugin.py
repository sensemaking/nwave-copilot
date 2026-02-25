"""Skills installer plugin: installs nWave skills to ~/.copilot/skills/."""

import shutil
from pathlib import Path

from nwave_copilot.converters.skill_namer import get_skill_dir_name
from nwave_copilot.plugins.base import InstallContext, InstallPlugin, PluginResult


class SkillsPlugin(InstallPlugin):
    """Converts and installs nWave skills to the personal Copilot skills directory.

    Source:  nWave/skills/{agent-folder}/{skill-name}.md
    Target:  ~/.copilot/skills/nw-{skill-name}/SKILL.md
             (or ~/.copilot/skills/nw-{agent-folder}-{skill-name}/SKILL.md
              for skills with conflicting names across agent directories)

    Existing skill files already contain name: and description: frontmatter,
    which Copilot uses for auto-selection. No frontmatter conversion is needed.
    """

    _NW_SKILL_PREFIX = "nw-"

    def __init__(self) -> None:
        super().__init__(name="skills", priority=20)

    def _iter_source_skills(
        self, framework_source: Path
    ) -> list[tuple[str, Path]]:
        """Yield (agent_folder, skill_file) pairs from nWave/skills/."""
        skills_root = framework_source / "nWave" / "skills"
        results = []
        for agent_dir in sorted(skills_root.iterdir()):
            if not agent_dir.is_dir():
                continue
            for skill_file in sorted(agent_dir.glob("*.md")):
                results.append((agent_dir.name, skill_file))
        return results

    def install(self, context: InstallContext) -> PluginResult:
        try:
            context.logger.info("  📦 Installing skills...")
            skills = self._iter_source_skills(context.framework_source)

            if not skills:
                return PluginResult(
                    success=True,
                    plugin_name=self.name,
                    message="No skills directory found, skipping",
                )

            if not context.dry_run:
                # Remove previously installed nWave skills
                for stale in context.skills_dir.glob(f"{self._NW_SKILL_PREFIX}*/"):
                    shutil.rmtree(stale, ignore_errors=True)
                context.skills_dir.mkdir(parents=True, exist_ok=True)

            installed: list[Path] = []
            for agent_folder, skill_file in skills:
                dir_name = get_skill_dir_name(agent_folder, skill_file)
                target_dir = context.skills_dir / dir_name
                target_file = target_dir / "SKILL.md"

                if not context.dry_run:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(skill_file, target_file)
                installed.append(target_file)

            msg = f"Skills installed ({len(installed)} files)"
            context.logger.info(f"  ✅ {msg}")
            return PluginResult(
                success=True,
                plugin_name=self.name,
                message=msg,
                installed_files=installed,
            )
        except Exception as e:
            context.logger.error(f"  ❌ Failed to install skills: {e}")
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message=f"Skills installation failed: {e!s}",
                errors=[str(e)],
            )

    def uninstall(self, context: InstallContext) -> PluginResult:
        try:
            context.logger.info("  🗑️  Uninstalling skills...")
            removed = 0
            for skill_dir in context.skills_dir.glob(f"{self._NW_SKILL_PREFIX}*/"):
                if not context.dry_run:
                    shutil.rmtree(skill_dir, ignore_errors=True)
                removed += 1
            msg = f"Removed {removed} skill directories"
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
        skill_dirs = list(context.skills_dir.glob(f"{self._NW_SKILL_PREFIX}*/"))
        if not skill_dirs:
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message="No nw-* skill directories found",
                errors=["No skills installed"],
            )
        return PluginResult(
            success=True,
            plugin_name=self.name,
            message=f"Verified {len(skill_dirs)} skill directories",
        )
