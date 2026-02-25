"""Prompts init plugin: writes nWave prompt files to .github/prompts/."""

import re
import shutil
from pathlib import Path

import yaml

from nwave_copilot.plugins.base import InitContext, InitPlugin, PluginResult

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_PROMPTS_SUBDIR = Path(".github") / "prompts"


def _convert_prompt_file(source: Path, target: Path) -> None:
    """Convert a Claude Code slash-command file to a Copilot prompt file.

    Strips unsupported frontmatter fields (argument-hint) and renames the
    file with a nw- prefix and .prompt.md extension.
    """
    content = source.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(content)

    if match:
        try:
            fm = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        body = content[match.end():]

        # Keep only description; drop argument-hint (not supported)
        new_fm: dict[str, str] = {}
        if "description" in fm:
            new_fm["description"] = fm["description"]

        fm_lines = ["---"]
        if new_fm:
            fm_lines.append(
                yaml.dump(new_fm, default_flow_style=False).rstrip()
            )
        fm_lines.append("---")
        fm_lines.append("")
        new_content = "\n".join(fm_lines) + body
    else:
        new_content = content

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_content, encoding="utf-8")


class PromptsPlugin(InitPlugin):
    """Writes nWave prompt files into the project's .github/prompts/ directory.

    Source:  nWave/tasks/nw/*.md  (Claude Code slash commands)
    Target:  .github/prompts/nw-{name}.prompt.md

    Called by `nwave-copilot init` (not `install`).
    Prompt files are project-scoped and can be committed to the repo.
    """

    def __init__(self) -> None:
        super().__init__(name="prompts", priority=10)

    def init(self, context: InitContext) -> PluginResult:
        try:
            context.logger.info("  📄 Writing prompt files...")
            tasks_dir = context.framework_source / "nWave" / "tasks" / "nw"

            if not tasks_dir.exists():
                return PluginResult(
                    success=True,
                    plugin_name=self.name,
                    message="No tasks directory found, skipping",
                )

            prompts_dir = context.project_root / _PROMPTS_SUBDIR
            installed: list[Path] = []

            for source_file in sorted(tasks_dir.glob("*.md")):
                stem = source_file.stem  # e.g. "discover"
                target_name = f"nw-{stem}.prompt.md"
                target_path = prompts_dir / target_name

                if not context.dry_run:
                    _convert_prompt_file(source_file, target_path)
                installed.append(target_path)

            msg = f"Prompt files written ({len(installed)} files)"
            context.logger.info(f"  ✅ {msg}")
            return PluginResult(
                success=True,
                plugin_name=self.name,
                message=msg,
                installed_files=installed,
            )
        except Exception as e:
            context.logger.error(f"  ❌ Failed to write prompt files: {e}")
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message=f"Prompts init failed: {e!s}",
                errors=[str(e)],
            )

    def deinit(self, context: InitContext) -> PluginResult:
        try:
            context.logger.info("  🗑️  Removing prompt files...")
            prompts_dir = context.project_root / _PROMPTS_SUBDIR
            removed = 0
            for prompt_file in prompts_dir.glob("nw-*.prompt.md"):
                if not context.dry_run:
                    prompt_file.unlink()
                removed += 1
            msg = f"Removed {removed} prompt files"
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
        prompts_dir = context.project_root / _PROMPTS_SUBDIR
        files = list(prompts_dir.glob("nw-*.prompt.md"))
        if not files:
            return PluginResult(
                success=False,
                plugin_name=self.name,
                message="No nw-*.prompt.md files found",
                errors=["No prompt files installed"],
            )
        return PluginResult(
            success=True,
            plugin_name=self.name,
            message=f"Verified {len(files)} prompt files",
        )
