"""Base classes for the nwave-copilot plugin system.

Mirrors the pattern from scripts/install/plugins/base.py but targets
GitHub Copilot CLI paths and supports both install and init contexts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PluginResult:
    """Result of a plugin install/uninstall/verify operation."""

    success: bool
    plugin_name: str
    message: str = ""
    errors: list[str] = field(default_factory=list)
    installed_files: list[Path] = field(default_factory=list)

    def __str__(self) -> str:
        if self.success:
            return f"✓ {self.plugin_name}: {self.message}"
        return f"✗ {self.plugin_name}: {self.message}"


@dataclass
class InstallContext:
    """Shared context for personal install (nwave-copilot install)."""

    agents_dir: Path          # ~/.config/copilot/agents/
    skills_dir: Path          # ~/.copilot/skills/
    framework_source: Path    # root containing nWave/agents, nWave/skills, etc.
    logger: Any
    dry_run: bool = False


@dataclass
class InitContext:
    """Shared context for project init (nwave-copilot init)."""

    project_root: Path        # current working directory (git repo root)
    framework_source: Path    # root containing nWave/tasks/nw etc.
    logger: Any
    dry_run: bool = False


class InstallPlugin(ABC):
    """Base class for personal install plugins (agents, skills)."""

    def __init__(self, name: str, priority: int = 100):
        self.name = name
        self.priority = priority

    @abstractmethod
    def install(self, context: InstallContext) -> PluginResult:
        """Install this plugin's components."""

    @abstractmethod
    def uninstall(self, context: InstallContext) -> PluginResult:
        """Remove this plugin's components."""

    @abstractmethod
    def verify(self, context: InstallContext) -> PluginResult:
        """Verify installation was successful."""


class InitPlugin(ABC):
    """Base class for project init plugins (hooks, prompt files)."""

    def __init__(self, name: str, priority: int = 100):
        self.name = name
        self.priority = priority

    @abstractmethod
    def init(self, context: InitContext) -> PluginResult:
        """Write project-level files."""

    @abstractmethod
    def deinit(self, context: InitContext) -> PluginResult:
        """Remove project-level files."""

    @abstractmethod
    def verify(self, context: InitContext) -> PluginResult:
        """Verify init was successful."""
