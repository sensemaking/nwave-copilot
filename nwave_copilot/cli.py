"""nwave-copilot CLI.

Commands:
  build-plugin  Build a native Copilot CLI plugin directory (preferred)
  install       Install nWave agents and skills directly to personal Copilot config
  uninstall     Remove nWave agents and skills from personal Copilot config
  init          Add nWave hook configs and prompt files to the current project
  deinit        Remove nWave hook configs and prompt files from the current project
  version       Show nwave-copilot version
"""

import json
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console

from nwave_copilot import __version__
from nwave_copilot._framework import (
    get_copilot_agents_dir,
    get_copilot_skills_dir,
    get_framework_source,
)
from nwave_copilot.converters.agent_converter import convert_agent
from nwave_copilot.converters.skill_namer import get_skill_dir_name
from nwave_copilot.plugins.agents_plugin import AgentsPlugin
from nwave_copilot.plugins.base import InitContext, InstallContext
from nwave_copilot.plugins.hooks_plugin import HooksPlugin
from nwave_copilot.plugins.prompts_plugin import PromptsPlugin
from nwave_copilot.plugins.skills_plugin import SkillsPlugin

app = typer.Typer(
    name="nwave-copilot",
    help="GitHub Copilot CLI plugin for the nWave software development framework.",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True, style="bold red")


class _Logger:
    """Thin logger that writes to Rich console."""

    def info(self, msg: str) -> None:
        console.print(msg)

    def error(self, msg: str) -> None:
        err_console.print(msg)


def _get_install_context(dry_run: bool) -> InstallContext:
    return InstallContext(
        agents_dir=get_copilot_agents_dir(),
        skills_dir=get_copilot_skills_dir(),
        framework_source=get_framework_source(),
        logger=_Logger(),
        dry_run=dry_run,
    )


def _get_init_context(dry_run: bool) -> InitContext:
    return InitContext(
        project_root=Path.cwd(),
        framework_source=get_framework_source(),
        logger=_Logger(),
        dry_run=dry_run,
    )


def _run_install_plugins(context: InstallContext, plugins: list) -> bool:
    """Run install on all plugins; return True if all succeeded."""
    all_ok = True
    for plugin in plugins:
        result = plugin.install(context)
        if not result.success:
            err_console.print(str(result))
            all_ok = False
    return all_ok


def _run_uninstall_plugins(context: InstallContext, plugins: list) -> bool:
    all_ok = True
    for plugin in plugins:
        result = plugin.uninstall(context)
        if not result.success:
            err_console.print(str(result))
            all_ok = False
    return all_ok


def _run_init_plugins(context: InitContext, plugins: list) -> bool:
    all_ok = True
    for plugin in plugins:
        result = plugin.init(context)
        if not result.success:
            err_console.print(str(result))
            all_ok = False
    return all_ok


def _run_deinit_plugins(context: InitContext, plugins: list) -> bool:
    all_ok = True
    for plugin in plugins:
        result = plugin.deinit(context)
        if not result.success:
            err_console.print(str(result))
            all_ok = False
    return all_ok


@app.command("build-plugin")
def build_plugin(
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for the plugin (default: packages/nwave-plugin/ next to source)",
    ),
    python_exe: str = typer.Option(
        sys.executable,
        "--python",
        help="Python executable path to embed in hooks.json (default: current interpreter)",
    ),
) -> None:
    """Build a native Copilot CLI plugin directory.

    Creates a properly structured plugin containing agents, skills, and hooks
    that can be installed with: copilot plugin install <output-dir>

    The generated plugin is the recommended distribution format for nWave.
    The DES Python package must still be installed separately for hooks to work:
        pip install nwave-copilot
    """
    source = get_framework_source()
    if output is None:
        # Default: packages/nwave-plugin/ inside the framework source root
        output = source / "packages" / "nwave-plugin"

    console.print(f"\n[bold green]Building nWave Copilot plugin[/bold green] → {output}\n")

    # ── Clean + create output dirs ───────────────────────────────────────────
    agents_out = output / "agents"
    skills_out = output / "skills"
    for d in [agents_out, skills_out]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    # ── Build agents ─────────────────────────────────────────────────────────
    console.print("  📦 Converting agents...")
    source_agents = sorted((source / "nWave" / "agents").glob("nw-*.md"))
    for agent_file in source_agents:
        converted = convert_agent(agent_file)
        (agents_out / converted.target_filename).write_text(converted.content, encoding="utf-8")
    console.print(f"  ✅ {len(source_agents)} agents written")

    # ── Build skills ──────────────────────────────────────────────────────────
    console.print("  📦 Converting skills...")
    skills_root = source / "nWave" / "skills"
    skill_count = 0
    for agent_dir in sorted(skills_root.iterdir()):
        if not agent_dir.is_dir():
            continue
        for skill_file in sorted(agent_dir.glob("*.md")):
            dir_name = get_skill_dir_name(agent_dir.name, skill_file)
            skill_dir = skills_out / dir_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill_file, skill_dir / "SKILL.md")
            skill_count += 1
    console.print(f"  ✅ {skill_count} skills written")

    # ── Write hooks.json ─────────────────────────────────────────────────────
    console.print("  📦 Writing hooks.json...")
    hook_cmd_bash = f"{python_exe} -m des.adapters.drivers.hooks.copilot_hook_adapter"
    hook_cmd_ps = f"& '{python_exe}' -m des.adapters.drivers.hooks.copilot_hook_adapter"
    hooks_config = {
        "version": 1,
        "hooks": {
            "preToolUse": [{"type": "command", "bash": hook_cmd_bash, "powershell": hook_cmd_ps}],
            "postToolUse": [{"type": "command", "bash": hook_cmd_bash, "powershell": hook_cmd_ps}],
            "subagentStop": [{"type": "command", "bash": hook_cmd_bash, "powershell": hook_cmd_ps}],
        },
    }
    (output / "hooks.json").write_text(json.dumps(hooks_config, indent=2), encoding="utf-8")
    console.print("  ✅ hooks.json written")

    # ── Write plugin.json ─────────────────────────────────────────────────────
    console.print("  📦 Writing plugin.json...")
    plugin_manifest = {
        "name": "nwave",
        "description": (
            "nWave: A six-wave AI-assisted software development methodology. "
            "22 specialist agents, 68+ skills, and DES enforcement hooks for TDD discipline."
        ),
        "version": __version__,
        "author": {"name": "nWave contributors"},
        "license": "MIT",
        "homepage": "https://github.com/nwave-dev/nwave",
        "keywords": ["nwave", "tdd", "agile", "methodology", "software-development"],
        "agents": "agents/",
        "skills": "skills/",
        "hooks": "hooks.json",
    }
    (output / "plugin.json").write_text(json.dumps(plugin_manifest, indent=2), encoding="utf-8")
    console.print("  ✅ plugin.json written")

    console.print(f"\n[bold green]✅ Plugin built successfully![/bold green]")
    console.print(f"\n[dim]To install the plugin:[/dim]")
    console.print(f"[bold]  copilot plugin install {output}[/bold]\n")
    console.print(f"[dim]Note: For DES hooks to work, also run:[/dim]")
    console.print(f"[dim]  pip install nwave-copilot[/dim]\n")


@app.command()
def install(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes"),
) -> None:
    """Install nWave agents and skills to personal Copilot config.

    Agents → ~/.config/copilot/agents/
    Skills → ~/.copilot/skills/

    Run once. Agents and skills are available in all your projects.
    For DES hooks and prompt files, also run: nwave-copilot init
    """
    prefix = "[DRY RUN] " if dry_run else ""
    console.print(f"\n[bold green]{prefix}nwave-copilot install[/bold green] v{__version__}\n")

    plugins = [AgentsPlugin(), SkillsPlugin()]
    context = _get_install_context(dry_run)

    ok = _run_install_plugins(context, plugins)

    if ok:
        console.print("\n[bold green]✅ Installation complete![/bold green]")
        console.print(
            "\n[dim]To enable DES hooks and prompt files in a project:[/dim]"
        )
        console.print("[dim]  cd <your-project> && nwave-copilot init[/dim]\n")
    else:
        console.print("\n[bold red]❌ Installation completed with errors.[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def uninstall(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes"),
) -> None:
    """Remove nWave agents and skills from personal Copilot config."""
    prefix = "[DRY RUN] " if dry_run else ""
    console.print(f"\n[bold yellow]{prefix}nwave-copilot uninstall[/bold yellow]\n")

    plugins = [AgentsPlugin(), SkillsPlugin()]
    context = _get_install_context(dry_run)

    ok = _run_uninstall_plugins(context, plugins)

    if ok:
        console.print("\n[bold green]✅ Uninstall complete.[/bold green]")
    else:
        console.print("\n[bold red]❌ Uninstall completed with errors.[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def init(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes"),
) -> None:
    """Add nWave DES hooks and prompt files to the current project.

    Hook configs → .github/hooks/nw-*.json
    Prompt files → .github/prompts/nw-*.prompt.md

    Run from inside a git repository. Files can be committed so the whole
    team benefits. Requires `nwave-copilot install` to have been run first.
    """
    project_root = Path.cwd()
    prefix = "[DRY RUN] " if dry_run else ""
    console.print(
        f"\n[bold green]{prefix}nwave-copilot init[/bold green] in {project_root}\n"
    )

    plugins = [HooksPlugin(), PromptsPlugin()]
    context = _get_init_context(dry_run)

    ok = _run_init_plugins(context, plugins)

    if ok:
        console.print("\n[bold green]✅ Project init complete![/bold green]")
        console.print(
            "\n[dim]Tip: commit .github/hooks/ and .github/prompts/ "
            "so your team gets DES enforcement.[/dim]\n"
        )
    else:
        console.print("\n[bold red]❌ Init completed with errors.[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def deinit(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes"),
) -> None:
    """Remove nWave hook configs and prompt files from the current project."""
    project_root = Path.cwd()
    prefix = "[DRY RUN] " if dry_run else ""
    console.print(
        f"\n[bold yellow]{prefix}nwave-copilot deinit[/bold yellow] in {project_root}\n"
    )

    plugins = [HooksPlugin(), PromptsPlugin()]
    context = _get_init_context(dry_run)

    ok = _run_deinit_plugins(context, plugins)

    if ok:
        console.print("\n[bold green]✅ Deinit complete.[/bold green]")
    else:
        console.print("\n[bold red]❌ Deinit completed with errors.[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Show nwave-copilot version."""
    console.print(f"nwave-copilot {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
